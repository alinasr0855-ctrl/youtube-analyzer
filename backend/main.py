import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from backend.models.schemas import (
    AssistantRequest, AssistantResponse, RAGIndexRequest,
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
         "type": None, "topics": [], "estimated_minutes": None,
         "requires_previous": False, "rag_indexed": False}
        for v in videos
    ])
    return {"session_id": sid, "total_videos": len(videos),
            "channel_name": data.channel_name, "playlist_name": data.playlist_name}

# ── Analyze Next ──────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/analyze-next")
def analyze_next(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    all_v = cache_service.load_results(session_id)
    pending = [v for v in all_v if not v.get("analyzed")]
    if not pending:
        memory_service.complete_session(session_id)
        return {"is_complete": True, "analyzed_count": len(all_v), "total_videos": len(all_v)}

    batch = pending[:3]
    # Fetch transcripts for batch
    for v in batch:
        if not v.get("transcript"):
            v["transcript"] = youtube_service.get_transcript(v["video_id"])

    analyzed = gemini_service.analyze_batch(batch)
    cache_service.save_results(session_id, analyzed)

    total_analyzed = cache_service.get_analyzed_count(session_id)
    is_complete = total_analyzed >= s["total_videos"]
    if is_complete:
        memory_service.complete_session(session_id)
    else:
        memory_service.update_session(session_id, total_analyzed, s.get("last_batch", 0) + len(batch))

    return {"is_complete": is_complete, "analyzed_count": total_analyzed,
            "total_videos": s["total_videos"], "batch_size": len(analyzed)}

# ── Analyze Single Video ───────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/analyze-video")
def analyze_video(session_id: str, data: dict):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    vid = data.get("video_id")
    if not vid:
        raise HTTPException(400, "video_id required")
    all_v = cache_service.load_results(session_id)
    target = next((v for v in all_v if v["video_id"] == vid), None)
    if not target:
        raise HTTPException(404, "Video not in session")
    if not target.get("transcript"):
        target["transcript"] = youtube_service.get_transcript(vid)
    result = gemini_service.analyze_batch([target])
    cache_service.save_results(session_id, result)
    total_analyzed = cache_service.get_analyzed_count(session_id)
    memory_service.update_session(session_id, total_analyzed, s.get("last_batch", 0))
    return result[0] if result else target

# ── RAG Indexing ──────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/rag/index")
def rag_index_session(session_id: str, req: RAGIndexRequest):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    try:
        from backend.services.rag.rag_service import get_rag_service
        rag = get_rag_service()
    except Exception as e:
        raise HTTPException(503, f"RAG service unavailable: {e}")
    videos = [v for v in cache_service.load_results(session_id) if v.get("analyzed")]
    if not videos:
        raise HTTPException(400, "No analyzed videos to index")
    result = rag.index_session(videos, s, force=req.force_reindex)
    memory_service.update_rag_index_count(session_id, result["indexed_videos"])
    # Mark rag_indexed on individual videos
    all_v = cache_service.load_results(session_id)
    indexed_ids = {r["video_id"] for r in result.get("results",[]) if r["status"] in ("indexed","already_indexed")}
    for v in all_v:
        if v["video_id"] in indexed_ids:
            v["rag_indexed"] = True
    cache_service.save_results(session_id, all_v)
    return result

@app.post("/api/sessions/{session_id}/rag/index-video")
def rag_index_video(session_id: str, req: RAGIndexRequest):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    if not req.video_id:
        raise HTTPException(400, "video_id required")
    try:
        from backend.services.rag.rag_service import get_rag_service
        rag = get_rag_service()
    except Exception as e:
        raise HTTPException(503, f"RAG service unavailable: {e}")
    meta = {"title": req.video_id, "channel_name": s.get("channel_name",""),
            "channel_id": s.get("channel_id",""), "playlist_id": s.get("playlist_id",""),
            "playlist_name": s.get("playlist_name","")}
    all_v = cache_service.load_results(session_id)
    target = next((v for v in all_v if v["video_id"] == req.video_id), None)
    if target:
        meta["title"] = target.get("title", req.video_id)
    result = rag.index_video(req.video_id, meta, force=req.force_reindex)
    if result["status"] in ("indexed","already_indexed") and target:
        target["rag_indexed"] = True
        cache_service.save_results(session_id, all_v)
        rag_count = sum(1 for v in all_v if v.get("rag_indexed"))
        memory_service.update_rag_index_count(session_id, rag_count)
    return result

# ── AI Assistant ──────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/assistant", response_model=AssistantResponse)
def assistant(session_id: str, req: AssistantRequest):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    analyzed = [v for v in cache_service.load_results(session_id) if v.get("analyzed")]
    if not analyzed:
        raise HTTPException(400, "No analyzed videos yet. Please analyze videos first.")
    history = [msg.model_dump() for msg in (req.history or [])]
    try:
        from backend.services.assistant.assistant_service import get_assistant_service
        svc = get_assistant_service()
        result = svc.handle(
            question=req.question, session=s, history=history,
            analyzed_videos=analyzed, video_ids=req.video_ids,
        )
    except Exception as e:
        # Graceful fallback to standard Gemini chat
        result = gemini_service.chat_with_playlist(
            question=req.question, videos=analyzed,
            playlist_name=s.get("playlist_name",""), chat_history=history)
        result["mode"] = "gemini"
        result["classification"] = "general"
        result["routing_reason"] = f"Assistant error — fell back to Gemini: {e}"
        result["retrieval_count"] = 0
        result["context_tokens"] = 0

    return AssistantResponse(
        answer=result.get("answer",""),
        mode=result.get("mode","gemini"),
        classification=result.get("classification","general"),
        sources=result.get("sources",[]),
        referenced_videos=result.get("referenced_videos",[]),
        confidence=result.get("confidence","medium"),
        retrieval_count=result.get("retrieval_count",0),
        context_tokens=result.get("context_tokens",0),
        duration_s=result.get("duration_s",0.0),
    )

# ── Summary ───────────────────────────────────────────────────────────────────
@app.post("/api/sessions/{session_id}/summary")
def summary(session_id: str):
    s = memory_service.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    cached = memory_service.get_session_summary(session_id)
    if cached:
        return {"summary": cached, "cached": True}
    videos = cache_service.load_results(session_id)
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

# ── Legacy Chat ───────────────────────────────────────────────────────────────
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
        raise HTTPException(404, "Session A not found")
    if not sb:
        raise HTTPException(404, "Session B not found")
    return gemini_service.compare_playlists(
        {"name": sa.get("playlist_name", "A"), "videos": cache_service.load_results(req.session_id_a)},
        {"name": sb.get("playlist_name", "B"), "videos": cache_service.load_results(req.session_id_b)})
