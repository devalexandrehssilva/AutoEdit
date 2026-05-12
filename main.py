import os
import threading
import requests
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Pega o conteúdo dos cookies da variável de ambiente caso o arquivo falhe
COOKIES_ENV = os.environ.get("YOUTUBE_COOKIES_CONTENT")

def create_temp_cookies():
    """Cria um arquivo temporário de cookies para o yt-dlp usar"""
    if COOKIES_ENV:
        temp_path = os.path.join(tempfile.gettempdir(), "cookies.txt")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(COOKIES_ENV)
        return temp_path
    return "youtube_cookies.txt" # fallback para o arquivo local

def process_video_task(video_url, segments, chat_id):
    cookies_path = create_temp_cookies()
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    
    try:
        ydl_opts = {
            'cookiefile': cookies_path,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': input_file,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        video = VideoFileClip(input_file)
        clips = [video.subclip(s, e) for s, e in segments]
        final = concatenate_videoclips(clips)
        final.write_videofile(output_file, codec="libx264", audio_codec="aac", preset="ultrafast")
        
        video.close()
        final.close()
        
        send_video_to_telegram(chat_id, output_file)
        
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro: {str(e)}"})
    finally:
        for f in [input_file, output_file]:
            if os.path.exists(f): os.remove(f)
