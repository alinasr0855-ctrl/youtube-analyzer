"""Session store — lives in memory only, gone when server stops."""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

_sessions: Dict[str, dict] = {}


def create_session(channel_name: str, channel_id: str, playlist_name: str,
                   playlist_id: str, total_videos: int) -> str:
    sid = str(uuid.uuid4())[:8]
    _sessions[sid] = {
        "session_id": sid, "channel_name": channel_name,
        "channel_id": channel_id, "playlist_name": playlist_name,
        "playlist_id": playlist_id, "total_videos": total_videos,
        "analyzed_count": 0, "last_batch": 0,
        "last_updated": datetime.now().isoformat(),
        "status": "in_progress", "summary": None, "learning_path": None,
    }
    return sid


def get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def update_session(session_id: str, analyzed_count: int, last_batch: int) -> None:
    s = _sessions.get(session_id)
    if not s:
        return
    s["analyzed_count"] = analyzed_count
    s["last_batch"] = last_batch
    s["last_updated"] = datetime.now().isoformat()
    if analyzed_count >= s["total_videos"]:
        s["status"] = "completed"


def complete_session(session_id: str) -> None:
    s = _sessions.get(session_id)
    if s:
        s["status"] = "completed"
        s["last_updated"] = datetime.now().isoformat()


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def save_session_summary(session_id: str, summary: str) -> None:
    s = _sessions.get(session_id)
    if s:
        s["summary"] = summary


def get_session_summary(session_id: str) -> Optional[str]:
    s = _sessions.get(session_id)
    return s.get("summary") if s else None


def save_learning_path(session_id: str, path: dict) -> None:
    s = _sessions.get(session_id)
    if s:
        s["learning_path"] = path


def get_learning_path(session_id: str) -> Optional[dict]:
    s = _sessions.get(session_id)
    return s.get("learning_path") if s else None


def get_all_sessions() -> List[dict]:
    return sorted(_sessions.values(), key=lambda x: x["last_updated"], reverse=True)


def get_active_sessions() -> List[dict]:
    return [s for s in get_all_sessions() if s["status"] == "in_progress"]
