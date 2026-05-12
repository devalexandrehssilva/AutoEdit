import os
import threading
import requests
import yt_dlp
from flask import Flask, request, jsonify

# Importações específicas para MoviePy 2.0+
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips

app = Flask(__name__)

# Configurações de ambiente
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def get_drive_direct_link(url):
    """Converte link de visualização do Drive em link de download direto"""
    if 'drive.google.com' in url:
        try:
            parts = url.split('/')
            file_id = parts[parts.index('d') + 1]
            return f'https://drive.google.com/uc?export=download&id={file_id}'
        except Exception:
            return url
    return url

def process_video_task(video_url, segments, chat_id):
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    
    try:
        # --- PASSO 1: DOWNLOAD ---
        if 'drive.google.com' in video_url:
            print(f"📥 Baixando do Drive para {chat_id}...")
            direct_link = get_drive_direct_link(video_url)
            r = requests.get(direct_link, stream=True)
            with open(input_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk: f.write(chunk)
        else:
            print(f"📥 Baixando do YouTube para {chat_id}...")
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': input_file,
                'quiet': True,
                'nocheckcertificate': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        # --- PASSO 2: EDIÇÃO ---
        print("✂️ Iniciando cortes...")
        video = VideoFileClip(input_file)
        
        # Garante que o FPS esteja definido para evitar erros de renderização
        if not video.fps:
            video.fps = 24
            
        clips = []
        for s, e in segments:
            # Compatibilidade MoviePy 2.0
            clip = video.subclipped(s, e) if hasattr(video, 'subclipped') else video.subclip(s, e)
            clips.append(clip)
        
        final_video = concatenate_videoclips(clips)

        # --- PASSO 3: RENDERIZAÇÃO (BAIXO CONSUMO) ---
        final_video.write_videofile(
            output_file, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac",
            preset="ultrafast", # Menor uso de CPU
            threads=1,          # Evita picos de memória RAM
            logger=None
        )
        
        video.close()
        final_video.close()
        
        # --- PASSO 4: ENVIO ---
        print("📤 Enviando para Telegram...")
        with open(output_file, 'rb') as vf:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", 
                files={'video': vf}, 
                data={'chat_id': chat_id, 'caption': "✅ Corte finalizado com sucesso!"}
            )
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro no processamento: {str(e)}"})
    finally:
        # Limpeza de arquivos temporários
        for f in [input_file, output_file]:
            if os.path.exists(f):
                os.remove(f)

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    # Inicia a tarefa em uma thread separada para não dar timeout no Make.com
    thread = threading.Thread(target=process_video_task, args=(data['video_url'], data['segments'], data['chat_id']))
    thread.start()
    return jsonify({"status": "processando"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
