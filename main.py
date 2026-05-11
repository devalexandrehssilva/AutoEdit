import os
from flask import Flask, request, jsonify
from moviepy import VideoFileClip, concatenate_videoclips

app = Flask(__name__)

@app.route('/')
def health():
    return "Servidor de Edição Ativo", 200

@app.route('/edit', methods=['POST'])
def edit():
    # Aqui virá a lógica que discutimos
    return jsonify({"status": "recebido"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
