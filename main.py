import os
from moviepy import VideoFileClip, concatenate_videoclips

def auto_edit_video(input_path, output_path, segments):
    """
    segments: Lista de tuplas com (start_time, end_time) em segundos
    """
    video = VideoFileClip(input_path)
    clips = []

    try:
        for start, end in segments:
            # Extrai o trecho relevante
            clip = video.subclip(start, end)
            clips.append(clip)

        # Concatena os trechos selecionados
        final_video = concatenate_videoclips(clips)
        
        # Renderização com codec otimizado
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
        
    finally:
        video.close()

# Exemplo de uso: O Agente de IA forneceu esses timestamps
momentos_relevantes = [(10, 25), (45, 60), (120, 150)]
auto_edit_video("video_bruto.mp4", "video_final.mp4", momentos_relevantes)
