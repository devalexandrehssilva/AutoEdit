import os
import threading
import requests
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES DE AMBIENTE (RAILWAY) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Dica: Cole o conteúdo do seu cookies.txt na variável YOUTUBE_COOKIES_CONTENT no Railway
COOKIES_CONTENT = os.environ.get("YOUTUBE_COOKIES_CONTENT")
COOKIES_FILE_NAME = "youtube_cookies.txt"

def send_telegram_video(chat_id, video_path, caption="🎬 Seu vídeo está pronto!"):
    """Envia o arquivo final para o Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': chat_id, 'caption': caption}
            requests.post(url, files=files, data=data)
    except Exception as e:
        print(f"Erro no envio: {e}")

def process_video_task(video_url, segments, chat_id):
    """Tarefa de processamento: Baixa, Corta e Envia"""
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    temp_cookies = os.path.join(tempfile.gettempdir(), f"cookies_{chat_id}.txt")
    
    try:
        # 1. Gerenciamento de Cookies (Prioriza Variável de Ambiente, depois Arquivo)
        if COOKIES_CONTENT:
            with open(temp_cookies, "w", encoding="utf-8") as f:
                f.write(COOKIES_CONTENT)
            actual_cookies = temp_cookies
        else:
            actual_cookies = COOKIES_FILE_NAME

        # 2. Download físico do vídeo (Garante que o MoviePy não dê 'Not Found')
        # Configuração ultra-compatível
        # Configuração de download robusta
        ydl_opts = {
            'cookiefile': actual_cookies,
            # Tenta baixar o melhor vídeo e áudio e unir em mp4, 
            # ou baixa o melhor arquivo único disponível se falhar.
            'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b',
            'outtmpl': input_file,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            # Garante que o yt-dlp use o ffmpeg instalado no sistema para a fusão
            'prefer_ffmpeg': True,
        }
        
        print(f"📥 Baixando vídeo: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 3. Edição com MoviePy
        print("✂️ Iniciando cortes...")
        video = VideoFileClip(input_file)
        clips = [video.subclip(start, end) for start, end in segments]
        final_video = concatenate_videoclips(clips)
        
        # 4. Renderização (Preset ultrafast para evitar timeout no Railway)
        final_video.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=f"audio_{chat_id}.m4a",
            remove_temp=True,
            preset="ultrafast",
            threads=4
        )
        
        video.close()
        final_video.close()
        
        # 5. Envio
        print("📤 Enviando para o Telegram...")
        send_telegram_video(chat_id, output_file)
        
    except Exception as e:
        error_msg = f"❌ Erro no processamento: {str(e)}"
        print(error_msg)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': error_msg})
    finally:
        # Limpeza total
        for f in [input_file, output_file, temp_cookies]:
            if os.path.exists(f):
                os.remove(f)

@app.route('/')
def health():
    return "Servidor AutoEdit Online", 200

@app.route('/edit', methods=['POST'])
def handle_edit():
    """Rota principal chamada pelo Make.com"""
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments')
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Dados incompletos"}), 400

    # Inicia a thread para liberar o Make.com imediatamente
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "processando"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
