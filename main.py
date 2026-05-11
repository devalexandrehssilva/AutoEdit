import os
import threading
import requests
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
# Pegue seu Token no @BotFather e coloque aqui ou nas variáveis do Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SEU_TOKEN_AQUI")

def send_video_to_telegram(chat_id, video_path):
    """Envia o arquivo final editado de volta para o usuário no Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, 'rb') as video:
            files = {'video': video}
            data = {'chat_id': chat_id, 'caption': "✅ Aqui está seu vídeo editado!"}
            response = requests.post(url, files=files, data=data)
            print(f"Telegram Response: {response.status_code}")
    except Exception as e:
        print(f"Erro ao enviar para Telegram: {e}")

def process_video_task(video_url, segments, chat_id):
    """Lógica de edição em segundo plano"""
    output_path = "video_final.mp4"
    
    try:
        print(f"Iniciando download e edição: {video_url}")
        
        # Carrega o vídeo diretamente da URL (MoviePy 2.0+ suporta via FFmpeg)
        video = VideoFileClip(video_url)
        
        clips = []
        for start, end in segments:
            # Cria os cortes baseados nos timestamps
            clip = video.subclip(start, end)
            clips.append(clip)
        
        # Concatena os pedaços
        final_video = concatenate_videoclips(clips)
        
        # Renderiza o arquivo (preset 'ultrafast' para economizar CPU no Railway)
        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            temp_audiofile='temp-audio.m4a', 
            remove_temp=True,
            preset="ultrafast"
        )
        
        # Fecha os arquivos para liberar memória
        video.close()
        final_video.close()

        # Envia o resultado
        send_video_to_telegram(chat_id, output_path)
        
        # Limpa o arquivo local para não encher o disco do servidor
        if os.path.exists(output_path):
            os.remove(output_path)

    except Exception as e:
        print(f"Erro no processamento: {e}")
        # Opcional: enviar mensagem de erro para o Telegram do usuário
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"❌ Erro na edição: {str(e)}"})

@app.route('/')
def health():
    return "Editor IA Online", 200

@app.route('/edit', methods=['POST'])
def start_edit():
    data = request.json
    
    # Extrai os dados enviados pelo Make.com
    video_url = data.get('video_url')
    segments = data.get('segments') # Formato: [[0, 10], [20, 30]]
    chat_id = data.get('chat_id')   # ID do usuário do Telegram

    if not video_url or not segments or not chat_id:
        return jsonify({"error": "Dados incompletos"}), 400

    # Inicia o processamento sem travar a requisição (Assíncrono)
    thread = threading.Thread(target=process_video_task, args=(video_url, segments, chat_id))
    thread.start()

    return jsonify({"status": "processing", "message": "Aguarde o envio no Telegram"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
