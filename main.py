import os
import threading
import requests
import yt_dlp
import tempfile
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES DO RAILWAY ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Variável de ambiente com o texto dos cookies (opcional para o Plano B)
COOKIES_CONTENT = os.environ.get("YOUTUBE_COOKIES_CONTENT")

def get_drive_direct_link(url):
    """Transforma link de visualização do Drive em link de download direto"""
    if 'drive.google.com' in url:
        try:
            # Extrai o ID do arquivo da URL do Drive
            parts = url.split('/')
            file_id = parts[parts.index('d') + 1]
            return f'https://drive.google.com/uc?export=download&id={file_id}'
        except:
            return url
    return url

def process_video_task(video_url, segments, chat_id):
    """Baixa o vídeo (Drive ou YT), corta e envia para o Telegram"""
    input_file = f"in_{chat_id}.mp4"
    output_file = f"out_{chat_id}.mp4"
    temp_cookies = os.path.join(tempfile.gettempdir(), f"cookies_{chat_id}.txt")
    
    try:
        # --- PASSO 1: DOWNLOAD ---
        if 'drive.google.com' in video_url:
            print(f"📥 Baixando do Drive para o chat {chat_id}...")
            direct_link = get_drive_direct_link(video_url)
            response = requests.get(direct_link, stream=True)
            with open(input_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
        else:
            print(f"📥 Tentando download do YouTube para o chat {chat_id}...")
            if COOKIES_CONTENT:
                with open(temp_cookies, "w", encoding="utf-8") as f:
                    f.write(COOKIES_CONTENT)
            
            ydl_opts = {
                'cookiefile': temp_cookies if COOKIES_CONTENT else None,
                'format': 'best',
                'outtmpl': input_file,
                'quiet': True,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['ios']}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        # --- PASSO 2: EDIÇÃO (MOVIEPY 2.0 COMPATÍVEL) ---
        print("✂️ Iniciando cortes no vídeo...")
        video = VideoFileClip(input_file)
        
        clips = []
        for s, e in segments:
            # Tenta o comando da versão 2.0, se falhar usa o da 1.0
            if hasattr(video, 'subclipped'):
                clips.append(video.subclipped(s, e))
            else:
                clips.append(video.subclip(s, e))
        
        final_video = concatenate_videoclips(clips)
        
        # Renderização rápida para o Railway
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
        
        # --- PASSO 3: ENVIO ---
        print("📤 Enviando para o Telegram...")
        with open(output_file, 'rb') as vf:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo", 
                files={'video': vf}, 
                data={'chat_id': chat_id, 'caption': "✅ Seu corte está pronto!"}
            )
        
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

@app.route('/')
def health():
    return "Editor de Vídeos Online", 200

@app.route('/edit', methods=['POST'])
def handle_edit():
    data = request.json
    video_url = data.get('video_url')
    segments = data.get('segments')
    chat_id = data.get('chat_id')

    if not all([video_url, segments, chat_id]):
        return jsonify({"error": "Dados incompletos"}), 400

    # Inicia o processamento em segundo plano (Thread)
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "processando"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
