import os
import threading
import requests
import yt_dlp
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
# O Token deve ser configurado nas Variáveis de Ambiente do Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def send_video_to_telegram(chat_id, video_path, caption="✅ Vídeo editado com sucesso!"):
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
    """Converte links do YouTube ou limpa links do Dropbox/Drive"""
    # Se for YouTube
    if "youtube.com" in url or "youtu.be" in url:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info['url']
    
    # Se for Dropbox, garante link de download direto
    if "dropbox.com" in url:
        return url.replace("?dl=0", "?dl=1").replace("www.dropbox.com", "dl.dropboxusercontent.com")
        
    return url

def process_video_task(video_url, segments, chat_id):
    """Processamento pesado em segundo plano"""
    output_filename = f"final_{chat_id}.mp4"
    
    try:
        print(f"Processando vídeo: {video_url}")
        
        # 1. Obtém a URL real do vídeo
        direct_url = get_direct_url(video_url)
        
        # 2. Abre o vídeo (MoviePy 2.0+ lê URLs via FFmpeg)
        video = VideoFileClip(direct_url)
        
        # 3. Executa os cortes
        clips = []
        for start, end in segments:
            clip = video.subclip(start, end)
            clips.append(clip)
        
        # 4. Concatena e Renderiza
        final_video = concatenate_videoclips(clips)
        final_video.write_videofile(
            output_filename,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=f"audio_{chat_id}.m4a",
            remove_temp=True,
            preset="ultrafast", # Essencial para não estourar CPU no Railway
            threads=4
        )
        
        # 5. Limpeza de memória
        video.close()
        final_video.close()
        
        # 6. Envio
        send_video_to_telegram(chat_id, output_filename)
        
    except Exception as e:
        error_msg = f"❌ Erro no processamento: {str(e)}"
        print(error_msg)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': error_msg})
    finally:
        # 7. Limpa o arquivo do disco para economizar espaço
        if os.path.exists(output_filename):
            os.remove(output_filename)

@app.route('/')
def health():
    return "Editor de Vídeo IA Ativo", 200

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments') # Ex: [[0, 10], [30, 40]]
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Parâmetros ausentes"}), 400

    # Dispara a Thread para o Make.com não receber Timeout
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "accepted", "message": "Vídeo em processamento"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
