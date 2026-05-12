import os
import threading
import requests
import yt_dlp
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
# O Token deve estar nas Variáveis de Ambiente do Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
COOKIES_FILE = "youtube_cookies.txt"

def send_video_to_telegram(chat_id, video_path, caption="✅ Seu vídeo está pronto!"):
    """Envia o arquivo final para o Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, files=files, data=data)
            return response.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar para Telegram: {e}")
        return False

def get_direct_url(url):
    """Extrai a URL real do vídeo usando cookies para evitar bloqueio de bot"""
    if "youtube.com" in url or "youtu.be" in url:
        ydl_opts = {
            'cookiefile': COOKIES_FILE,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info['url']
    
    # Ajuste para links diretos do Dropbox
    if "dropbox.com" in url:
        return url.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropboxusercontent.com")
        
    return url

def process_video_task(video_url, segments, chat_id):
    """Tarefa pesada executada em Thread separada"""
    output_filename = f"edit_{chat_id}.mp4"
    
    try:
        print(f"Iniciando processamento para chat {chat_id}...")
        
        # 1. Pega a URL direta (com cookies)
        direct_url = get_direct_url(video_url)
        
        # 2. Carrega o vídeo via stream
        video = VideoFileClip(direct_url)
        
        # 3. Realiza os cortes conforme os segmentos enviados pelo Make
        clips = []
        for start, end in segments:
            clip = video.subclip(start, end)
            clips.append(clip)
        
        # 4. Une os pedaços
        final_video = concatenate_videoclips(clips)
        
        # 5. Renderiza (usando presets velozes para economizar CPU no Railway)
        final_video.write_videofile(
            output_filename,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=f"temp_audio_{chat_id}.m4a",
            remove_temp=True,
            preset="ultrafast",
            threads=4
        )
        
        # Limpeza de memória do MoviePy
        video.close()
        final_video.close()
        
        # 6. Envia o resultado de volta para você
        send_video_to_telegram(chat_id, output_filename)
        
    except Exception as e:
        error_msg = f"❌ Erro no processamento: {str(e)}"
        print(error_msg)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': error_msg})
    finally:
        # 7. Remove o arquivo local para não ocupar espaço no servidor
        if os.path.exists(output_filename):
            os.remove(output_filename)

@app.route('/')
def health():
    return "Servidor de Edição IA Online", 200

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments')
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Parâmetros incompletos"}), 400

    # Responde ao Make.com imediatamente e inicia o vídeo no fundo
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "processando", "message": "Aguarde o vídeo no Telegram"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
