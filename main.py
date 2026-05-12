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

def create_subtitles(video_path):
    """Extrai áudio direto do arquivo original para economizar RAM"""
    audio_path = "temp_audio.mp3"
    try:
        print("🔊 Extraindo áudio do arquivo original...")
        # Usamos um clipe temporário só para extrair o áudio e fechamos logo em seguida
        temp_clip = VideoFileClip(video_path)
        temp_clip.audio.write_audiofile(audio_path, logger=None)
        temp_clip.close()
        
        print("🎙️ Transcrevendo com Whisper...")
        # Otimização: Whisper Tiny + fp16 False para usar menos RAM
        result = model.transcribe(audio_path, language='pt', fp16=False)
        
        subtitle_clips = []
        for segment in result['segments']:
            txt = TextClip(
                text=segment['text'].strip(),
                font_size=24,
                color='yellow',
                stroke_color='black',
                stroke_width=1,
                method='caption',
                size=(720 * 0.8, None), # Largura fixa baseada em HD padrão
                font="DejaVu-Sans"
            ).with_start(segment['start']).with_duration(segment['end'] - segment['start']).with_position(('center', 'bottom'))
            subtitle_clips.append(txt)
        
        return subtitle_clips
    except Exception as e:
        print(f"⚠️ Erro na legenda: {e}")
        return []
    finally:
        if os.path.exists(audio_path): os.remove(audio_path)

def process_video_task(video_url, segments, chat_id):
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    
    try:
        # 1. Download (Drive ou YT) - Igual ao anterior
        # ... [Mantenha sua lógica de download aqui] ...

        # 2. Gerar legendas PRIMEIRO (usando o arquivo original para salvar RAM)
        subtitle_clips = create_subtitles(input_file)

        # 3. Edição dos Cortes
        print("✂️ Cortando vídeo...")
        video = VideoFileClip(input_file)
        # Forçamos o FPS para evitar o erro 'CompositeAudioClip has no attribute fps'
        if video.fps is None: video.fps = 24 
        
        clips = [video.subclipped(s, e) for s, e in segments]
        final_video = concatenate_videoclips(clips)
        
        # 4. Composição Final
        if subtitle_clips:
            print("🎬 Aplicando legendas no corte final...")
            result_video = CompositeVideoClip([final_video] + subtitle_clips)
        else:
            result_video = final_video

        # 5. Renderização ultra-leve
        result_video.write_videofile(
            output_file,
            fps=24, # Força o FPS na saída
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            logger=None
        )
        
        # Fechamento seguro
        video.close()
        result_video.close()
        
        # Envio...
        # ... [Mantenha sua lógica de envio aqui] ...

    except Exception as e:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro: {str(e)}"})
    finally:
        # Limpeza...
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
