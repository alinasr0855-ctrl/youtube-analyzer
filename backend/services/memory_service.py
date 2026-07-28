"""Session metadata store — in-memory."""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

_sessions: Dict[str, dict] = {}

def create_session(channel_name, channel_id, playlist_name, playlist_id, total_videos):
    sid = str(uuid.uuid4())[:8]
    _sessions[sid] = {
        "session_id": sid, "channel_name": channel_name, "channel_id": channel_id,
        "playlist_name": playlist_name, "playlist_id": playlist_id,
        "total_videos": total_videos, "analyzed_count": 0, "last_batch": 0,
        "last_updated": datetime.now().isoformat(), "status": "in_progress",
        "summary": None, "learning_path": None, "rag_indexed_count": 0,
    }
    return sid

def get_session(sid: str) -> Optional[dict]:
    return _sessions.get(sid)

def update_session(sid: str, analyzed_count: int, last_batch: int) -> None:
    s = _sessions.get(sid)
    if not s: return
    s["analyzed_count"] = analyzed_count
    s["last_batch"] = last_batch
    s["last_updated"] = datetime.now().isoformat()
    if analyzed_count >= s["total_videos"]: s["status"] = "completed"

def update_rag_index_count(sid: str, count: int) -> None:
    s = _sessions.get(sid)
    if s: s["rag_indexed_count"] = count; s["last_updated"] = datetime.now().isoformat()

def complete_session(sid: str) -> None:
    s = _sessions.get(sid)
    if s: s["status"] = "completed"; s["last_updated"] = datetime.now().isoformat()

def delete_session(sid: str) -> None:
    _sessions.pop(sid, None)

def save_session_summary(sid: str, summary: str) -> None:
    s = _sessions.get(sid)
    if s: s["summary"] = summary

def get_session_summary(sid: str) -> Optional[str]:
    s = _sessions.get(sid)
    return s.get("summary") if s else None

def save_learning_path(sid: str, path: dict) -> None:
    s = _sessions.get(sid)
    if s: s["learning_path"] = path

def get_learning_path(sid: str) -> Optional[dict]:
    s = _sessions.get(sid)
    return s.get("learning_path") if s else None

def get_all_sessions() -> List[dict]:
    return sorted(_sessions.values(), key=lambda x: x["last_updated"], reverse=True)
