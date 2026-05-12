import os
import threading
import requests
import yt_dlp
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
COOKIES_FILE = "youtube_cookies.txt"

def send_video_to_telegram(chat_id, video_path, caption="🎬 Seu clipe está pronto!"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, files=files, data=data)
            return response.status_code == 200
    except Exception as e:
        print(f"Erro no envio para o Telegram: {e}")
        return False

def process_video_task(video_url, segments, chat_id):
    """Baixa, corta e envia o vídeo"""
    input_file = f"input_{chat_id}.mp4"
    output_file = f"output_{chat_id}.mp4"
    
    try:
        print(f"Iniciando download do YouTube: {video_url}")
        
        # 1. Configuração do yt-dlp para download físico usando seus cookies
        ydl_opts = {
            'cookiefile': COOKIES_FILE,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': input_file, # Define o nome do arquivo baixado
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 2. Processamento com MoviePy (usando o arquivo local)
        print("Iniciando edição dos cortes...")
        video = VideoFileClip(input_file)
        
        clips = []
        for start, end in segments:
            clip = video.subclip(start, end)
            clips.append(clip)
        
        final_video = concatenate_videoclips(clips)
        
        # 3. Renderização otimizada para o Railway
        final_video.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=f"temp_audio_{chat_id}.m4a",
            remove_temp=True,
            preset="ultrafast", # Rapidez é prioridade aqui
            threads=4
        )
        
        # Fecha os arquivos para liberar memória RAM
        video.close()
        final_video.close()
        
        # 4. Envio para o Telegram
        print("Enviando vídeo para o usuário...")
        send_video_to_telegram(chat_id, output_file)
        
    except Exception as e:
        error_msg = f"❌ Erro técnico: {str(e)}"
        print(error_msg)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': error_msg})
    
    finally:
        # 5. Limpeza total de arquivos para não estourar o disco do Railway
        for f in [input_file, output_file]:
            if os.path.exists(f):
                os.remove(f)
        print("Limpeza de arquivos temporários concluída.")

@app.route('/')
def health():
    return "Editor de Vídeos IA - Ativo", 200

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments')
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Parâmetros ausentes"}), 400

    # Dispara a thread para o Make.com não receber Timeout 504
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "accepted", "message": "Processando seu vídeo..."}), 202

if __name__ == "__main__":
    # O Railway define a porta automaticamente
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
