import os
import threading
import requests
import yt_dlp
import tempfile
import whisper
from flask import Flask, request, jsonify

# Importações corrigidas para MoviePy 2.0
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

app = Flask(__name__)

# Carrega o modelo Whisper (Tiny é o melhor para o Railway não travar)
model = whisper.load_model("tiny")

BOT_TOKEN = os.environ.get("BOT_TOKEN")

def get_drive_direct_link(url):
    if 'drive.google.com' in url:
        try:
            parts = url.split('/')
            file_id = parts[parts.index('d') + 1]
            return f'https://drive.google.com/uc?export=download&id={file_id}'
        except: return url
    return url

def create_subtitles(video_clip):
    """Extrai áudio, transcreve e cria os clipes de texto"""
    audio_path = "temp_audio.mp3"
    video_clip.audio.write_audiofile(audio_path, logger=None)
    
    print("🎙️ Transcrevendo áudio com Whisper...")
    result = model.transcribe(audio_path, language='pt')
    
    subtitle_clips = []
    for segment in result['segments']:
        # Criando a legenda visual
        txt = TextClip(
            text=segment['text'].strip(),
            font_size=24,
            color='yellow',
            stroke_color='black',
            stroke_width=1,
            method='caption',
            size=(video_clip.w * 0.8, None)
        ).with_start(segment['start']).with_duration(segment['end'] - segment['start']).with_position(('center', 'bottom'))
        
        subtitle_clips.append(txt)
    
    if os.path.exists(audio_path):
        os.remove(audio_path)
    return subtitle_clips

def process_video_task(video_url, segments, chat_id):
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    
    try:
        # DOWNLOAD (YouTube ou Drive)
        if 'drive.google.com' in video_url:
            direct_link = get_drive_direct_link(video_url)
            response = requests.get(direct_link, stream=True)
            with open(input_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
        else:
            ydl_opts = {'format': 'best', 'outtmpl': input_file, 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([video_url])

        # EDIÇÃO
        print("✂️ Cortando e Legendando...")
        video = VideoFileClip(input_file)
        
        # Fazendo os cortes
        clips = []
        for s, e in segments:
            clip = video.subclipped(s, e) if hasattr(video, 'subclipped') else video.subclip(s, e)
            clips.append(clip)
        
        final_video = concatenate_videoclips(clips)
        
        # GERANDO LEGENDAS
        subtitle_clips = create_subtitles(final_video)
        
        # Sobrepondo as legendas no vídeo
        result_video = CompositeVideoClip([final_video] + subtitle_clips)
        
        # RENDERIZAÇÃO
        result_video.write_videofile(
            output_file, 
            codec="libx264", 
            audio_codec="aac", 
            temp_audiofile=f"audio_{chat_id}.m4a",
            remove_temp=True,
            preset="ultrafast"
        )
        
        video.close()
        result_video.close()
        
        # ENVIO
        with open(output_file, 'rb') as vf:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", 
                          files={'video': vf}, data={'chat_id': chat_id})
        
    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro: {str(e)}"})
    finally:
        for f in [input_file, output_file]:
            if os.path.exists(f): os.remove(f)

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    thread = threading.Thread(target=process_video_task, args=(data['video_url'], data['segments'], data['chat_id']))
    thread.start()
    return jsonify({"status": "ok"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
