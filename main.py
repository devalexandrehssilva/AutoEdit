import os
import threading
import requests
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
COOKIES_CONTENT = os.environ.get("YOUTUBE_COOKIES_CONTENT")

def get_drive_direct_link(url):
    """Converte link de visualização do Google Drive em link de download direto"""
    if 'drive.google.com' in url:
        try:
            # Extrai o ID do arquivo entre /d/ e /view
            file_id = url.split('/')[-2]
            return f'https://drive.google.com/uc?export=download&id={file_id}'
        except:
            return url
    return url

def process_video_task(video_url, segments, chat_id):
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    temp_cookies = os.path.join(tempfile.gettempdir(), f"cookies_{chat_id}.txt")
    
    try:
        # 1. Tenta baixar do Google Drive primeiro se o link for compatível
        if 'drive.google.com' in video_url:
            direct_link = get_drive_direct_link(video_url)
            print(f"📥 Baixando do Drive: {direct_link}")
            response = requests.get(direct_link, stream=True)
            with open(input_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 2. Caso contrário, tenta baixar do YouTube com configurações de elite
        else:
            if COOKIES_CONTENT:
                with open(temp_cookies, "w", encoding="utf-8") as f:
                    f.write(COOKIES_CONTENT)
                actual_cookies = temp_cookies
            else:
                actual_cookies = "youtube_cookies.txt"

            ydl_opts = {
                'cookiefile': actual_cookies,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': input_file,
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['ios']}},
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
                'nocheckcertificate': True,
            }
            
            print(f"📥 Baixando do YouTube via iOS Client: {video_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        # 3. Processamento com MoviePy (Edição)
        print("✂️ Iniciando cortes...")
        video = VideoFileClip(input_file)
        clips = [video.subclip(start, end) for start, end in segments]
        final_video = concatenate_videoclips(clips)
        
        # 4. Renderização otimizada
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
        
        # 5. Envio para o Telegram
        print("📤 Enviando para o Telegram...")
        with open(output_file, 'rb') as vf:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", 
                          files={'video': vf}, data={'chat_id': chat_id})
        
    except Exception as e:
        error_msg = f"❌ Erro técnico: {str(e)}"
        print(error_msg)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': error_msg})
    finally:
        # Limpeza total de arquivos temporários
        for f in [input_file, output_file, temp_cookies]:
            if os.path.exists(f):
                os.remove(f)

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments')
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Dados incompletos"}), 400

    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "processando"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
