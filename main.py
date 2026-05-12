import os
import threading
import requests
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
COOKIES_CONTENT = os.environ.get("YOUTUBE_COOKIES_CONTENT")

def process_video_task(video_url, segments, chat_id):
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    temp_cookies = os.path.join(tempfile.gettempdir(), f"cookies_{chat_id}.txt")
    
    try:
        # 1. Gerenciamento de Cookies
        if COOKIES_CONTENT:
            with open(temp_cookies, "w", encoding="utf-8") as f:
                f.write(COOKIES_CONTENT)
            actual_cookies = temp_cookies
        else:
            actual_cookies = "youtube_cookies.txt"

        # 2. Configuração de Download Camuflada
        ydl_opts = {
            'cookiefile': actual_cookies,
            # 'best' puro para evitar conflitos de merge/ffmpeg
            'format': 'best', 
            'outtmpl': input_file,
            'quiet': True,
            'no_warnings': True,
            # Camuflagem: faz o servidor parecer um celular Android
            'user_agent': 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.181 Mobile Safari/537.36',
            'nocheckcertificate': True,
        }
        
        print(f"📥 Tentativa de download camuflado: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 3. Edição
        video = VideoFileClip(input_file)
        clips = [video.subclip(s, e) for s, e in segments]
        final = concatenate_videoclips(clips)
        
        final.write_videofile(
            output_file,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4
        )
        
        video.close()
        final.close()
        
        # 4. Envio
        with open(output_file, 'rb') as vf:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", 
                          files={'video': vf}, data={'chat_id': chat_id})
        
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro final: {str(e)}"})
    finally:
        for f in [input_file, output_file, temp_cookies]:
            if os.path.exists(f): os.remove(f)

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    thread = threading.Thread(target=process_video_task, args=(data['video_url'], data['segments'], data['chat_id']))
    thread.start()
    return jsonify({"status": "processando"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
