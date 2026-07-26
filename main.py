import os
import shutil
import zipfile
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import whisper

app = FastAPI(title="Dark Video Automation Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = os.path.abspath("output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "SUA_CHAVE_PEXELS_AQUI")

class NicheRequest(BaseModel):
    niche: str

class Scene(BaseModel):
    id: int
    narration: str
    visual_prompt: str

class ScriptRequest(BaseModel):
    topic: str
    scenes: List[Scene]

def format_timestamp(seconds: float) -> str:
    millis = int((seconds % 1) * 1000)
    seconds = int(seconds)
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

@app.post("/api/analyze-niche")
async def analyze_niche(data: NicheRequest):
    try:
        trends = {
            "curiosidades": [
                "5 Fatos Perturbadores Sobre o Espaço",
                "Segredos Históricos Jamais Revelados",
                "O Mistério do Buraco das Marianas"
            ],
            "financas": [
                "Como Regras Silenciosas Fazem os Ricos Enriquecerem",
                "Os 3 Erros Financeiros Que Te Mantêm Duro",
                "O Que Acontecerá Com o Dinheiro em 2030"
            ],
            "misterio": [
                "O Incidente da Passagem Dyatlov Explicado",
                "Cidades Fantasma Que Ainda Existem Hoje",
                "Arquivos Confidenciais Desclassificados"
            ]
        }
        selected = trends.get(data.niche.lower(), [
            f"Tendência Viral 1 para {data.niche}",
            f"Segredos Ocultos em {data.niche}",
            f"O Lado Sombrio de {data.niche}"
        ])
        return {"niche": data.niche, "trends": selected}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-script")
async def generate_script(data: NicheRequest):
    try:
        sample_script = [
            Scene(id=1, narration="Você sabia que o oceano esconde segredos que a ciência ainda não consegue explicar?", visual_prompt="deep dark ocean water underwater cinematic"),
            Scene(id=2, narration="Nas profundezas mais escuras, criaturas bizarras emitem sua própria luz para caçar.", visual_prompt="bioluminescent deep sea creature dark background"),
            Scene(id=3, narration="E quanto mais fundo descemos, mais a pressão humana se torna insuportável.", visual_prompt="abyssal trench dark underwater pressure abstract")
        ]
        return {"topic": data.niche, "scenes": sample_script}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/render-video")
async def render_video(data: ScriptRequest):
    project_dir = os.path.join(OUTPUT_DIR, "current_project")
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    os.makedirs(project_dir, exist_ok=True)

    try:
        full_text = " ".join([s.narration for s in data.scenes])
        audio_path = os.path.join(project_dir, "narration.mp3")
        
        communicate = edge_tts.Communicate(full_text, "pt-BR-AntonioNeural")
        await communicate.save(audio_path)

        media_files = []
        headers = {"Authorization": PEXELS_API_KEY} if PEXELS_API_KEY != "SUA_CHAVE_PEXELS_AQUI" else {}
        
        for idx, scene in enumerate(data.scenes):
            media_path = os.path.join(project_dir, f"scene_{idx+1}.mp4")
            downloaded = False
            
            if PEXELS_API_KEY != "SUA_CHAVE_PEXELS_AQUI":
                url = f"https://api.pexels.com/videos/search?query={scene.visual_prompt}&per_page=1&orientation=portrait"
                res = requests.get(url, headers=headers)
                if res.status_code == 200:
                    json_data = res.json()
                    if json_data.get("videos"):
                        video_files = json_data["videos"][0]["video_files"]
                        link = video_files[0]["link"]
                        v_res = requests.get(link)
                        with open(media_path, "wb") as f:
                            f.write(v_res.content)
                        downloaded = True

            if not downloaded:
                from moviepy.editor import ColorClip
                fallback = ColorClip(size=(1080, 1920), color=(15, 15, 20), duration=4)
                fallback.write_videofile(media_path, fps=24, logger=None)
            
            media_files.append(media_path)

        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration
        scene_duration = total_duration / len(media_files)

        clips = []
        for media_path in media_files:
            clip = VideoFileClip(media_path).resize((1080, 1920))
            clip = clip.subclip(0, min(clip.duration, scene_duration)).set_duration(scene_duration)
            clips.append(clip)

        final_video = concatenate_videoclips(clips, method="compose").set_audio(audio_clip)
        
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        
        srt_path = os.path.join(project_dir, "subtitle.srt")
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            for i, segment in enumerate(result.get("segments", []), start=1):
                start = format_timestamp(segment["start"])
                end = format_timestamp(segment["end"])
                text = segment["text"].strip()
                srt_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        final_mp4_path = os.path.join(OUTPUT_DIR, "final_video.mp4")
        final_video.write_videofile(final_mp4_path, fps=24, codec="libx264", audio_codec="aac", logger=None)

        zip_path = os.path.join(OUTPUT_DIR, "capcut_package.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(audio_path, arcname="narration.mp3")
            zipf.write(srt_path, arcname="subtitle.srt")
            for idx, m_file in enumerate(media_files):
                zipf.write(m_file, arcname=f"media_scene_{idx+1}.mp4")

        return {
            "status": "success",
            "video_url": "/api/download/video",
            "zip_url": "/api/download/zip"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na renderização: {str(e)}")

@app.get("/api/download/video")
async def download_video():
    path = os.path.join(OUTPUT_DIR, "final_video.mp4")
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename="final_video.mp4")
    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

@app.get("/api/download/zip")
async def download_zip():
    path = os.path.join(OUTPUT_DIR, "capcut_package.zip")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/zip", filename="capcut_package.zip")
    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
