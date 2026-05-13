import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from backend.models.schemas import (
    ChannelSearchRequest, ChatRequest, ChatResponse,
    CompareRequest, StartSessionRequest,
)
from backend.services import cache_service, gemini_service, memory_service, youtube_service

app = FastAPI(title="PlaylistAI", version="3.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

FRONTEND = Path(__file__).resolve().parent.parent / "Frontend"
FRONTEND.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(str(FRONTEND / "index.html"))

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0.0"}

# ── Sessions ──────────────────────────────────────────────────────────────────
@app.get("/api/sessions")
def get_sessions():
    return {"sessions": memory_service.get_all_sessions()}

@app.get("/api/sessions/{session_id}/results")
def get_results(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return {"session": s, "videos": cache_service.load_results(session_id)}

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    if not memory_service.get_session(session_id):
        raise HTTPException(404, "Session not found")
    memory_service.delete_session(session_id)
    cache_service.delete_session_cache(session_id)
    return {"message": "Deleted"}

# ── Search ────────────────────────────────────────────────────────────────────
@app.post("/api/search")
def search(req: ChannelSearchRequest):
    q = req.query.strip()
    pid = youtube_service.extract_playlist_id(q)
    if pid:
        try:
            info = youtube_service.get_playlist_info(pid)
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        if not info:
            raise HTTPException(404, "Playlist not found")
        return {"type": "playlist", "playlist": info, "channels": []}
    try:
        channels = youtube_service.search_channels(q)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not channels:
        raise HTTPException(404, "No channels found")
    return {"type": "channels", "channels": channels, "playlist": None}

@app.get("/api/channels/{channel_id}/playlists")
def get_playlists(channel_id: str):
    try:
        return {"playlists": youtube_service.get_channel_playlists(channel_id)}
    except RuntimeError as e:
        raise HTTPException(502, str(e))

# ── Start Session ─────────────────────────────────────────────────────────────
@app.post("/api/sessions/start")
def start_session(data: StartSessionRequest):
    try:
        videos = youtube_service.get_playlist_videos(data.playlist_id)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not videos:
        raise HTTPException(404, "No videos found")
    sid = memory_service.create_session(
        channel_name=data.channel_name or "Unknown",
        channel_id=data.channel_id or "",
        playlist_name=data.playlist_name or "Unknown",
        playlist_id=data.playlist_id,
        total_videos=len(videos),
    )
    cache_service.save_results(sid, [
        {**v, "analyzed": False, "explanation": None, "level": None,
         "type": None, "topics": [], "estimated_minutes": None, "requires_previous": False}
        for v in videos
    ])
    return {"session_id": sid, "total_videos": len(videos),
            "session": memory_service.get_session(sid)}

# ── Analyze ───────────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/analyze-next")
def analyze_next(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    if s["status"] == "completed":
        return {"message": "Already complete", "is_complete": True, "videos": []}
    unanalyzed = [v for v in cache_service.load_results(session_id) if not v.get("analyzed")]
    if not unanalyzed:
        memory_service.complete_session(session_id)
        return {"message": "All analyzed!", "is_complete": True, "videos": []}
    batch = unanalyzed[:3]
    enriched = [{**v, "transcript": youtube_service.get_transcript(v["video_id"])} for v in batch]
    analyzed = gemini_service.analyze_batch(enriched)
    cache_service.save_results(session_id, analyzed)
    new_count = cache_service.get_analyzed_count(session_id)
    memory_service.update_session(session_id, new_count, s["last_batch"] + 1)
    is_complete = new_count >= s["total_videos"]
    return {"session_id": session_id, "batch_number": s["last_batch"] + 1,
            "videos": analyzed, "analyzed_count": new_count,
            "total_videos": s["total_videos"], "is_complete": is_complete}

@app.post("/api/sessions/{session_id}/analyze-video")
def analyze_video(session_id: str, data: dict):
    vid = data.get("video_id")
    if not vid:
        raise HTTPException(400, "video_id required")
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    all_v = cache_service.load_results(session_id)
    target = next((v for v in all_v if v["video_id"] == vid), None)
    if not target:
        raise HTTPException(404, "Video not found")
    if target.get("analyzed"):
        return {"video": target, "already_analyzed": True}
    analyzed = gemini_service.analyze_batch(
        [{**target, "transcript": youtube_service.get_transcript(vid)}])
    cache_service.save_results(session_id, analyzed)
    new_count = cache_service.get_analyzed_count(session_id)
    memory_service.update_session(session_id, new_count, s["last_batch"])
    if new_count >= s["total_videos"]:
        memory_service.complete_session(session_id)
    return {"video": analyzed[0], "analyzed_count": new_count,
            "total_videos": s["total_videos"],
            "is_complete": new_count >= s["total_videos"]}

# ── Summary ───────────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/summary")
def summary(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    cached = memory_service.get_session_summary(session_id)
    if cached:
        return {"summary": cached, "cached": True}
    videos = [v for v in cache_service.load_results(session_id) if v.get("analyzed")]
    if not videos:
        raise HTTPException(400, "No analyzed videos yet")
    result = gemini_service.generate_playlist_summary(videos, s.get("playlist_name", ""))
    memory_service.save_session_summary(session_id, result)
    return {"summary": result, "cached": False}

# ── Learning Path ─────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/learning-path")
def learning_path(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    cached = memory_service.get_learning_path(session_id)
    if cached:
        return {"learning_path": cached, "cached": True}
    videos = [v for v in cache_service.load_results(session_id) if v.get("analyzed")]
    if not videos:
        raise HTTPException(400, "No analyzed videos yet")
    result = gemini_service.generate_learning_path(videos)
    memory_service.save_learning_path(session_id, result)
    return {"learning_path": result, "cached": False}

# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
def chat(session_id: str, req: ChatRequest):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    videos = [v for v in cache_service.load_results(session_id) if v.get("analyzed")]
    if not videos:
        raise HTTPException(400, "No analyzed videos yet")
    history = [msg.model_dump() for msg in (req.history or [])]
    result = gemini_service.chat_with_playlist(
        question=req.question, videos=videos,
        playlist_name=s.get("playlist_name", ""), chat_history=history)
    return ChatResponse(answer=result.get("answer", ""),
                        referenced_videos=result.get("referenced_videos", []))

# ── Compare ───────────────────────────────────────────────────────────────────
@app.post("/api/compare")
def compare(req: CompareRequest):
    sa = memory_service.get_session(req.session_id_a)
    sb = memory_service.get_session(req.session_id_b)
    if not sa:
        raise HTTPException(404, f"Session A not found")
    if not sb:
        raise HTTPException(404, f"Session B not found")
    return gemini_service.compare_playlists(
        {"name": sa.get("playlist_name", "A"),
         "videos": cache_service.load_results(req.session_id_a)},
        {"name": sb.get("playlist_name", "B"),
         "videos": cache_service.load_results(req.session_id_b)})
