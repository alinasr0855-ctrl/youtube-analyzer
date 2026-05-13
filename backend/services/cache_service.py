"""Video results — lives in memory only, gone when server stops."""
from typing import Dict, List

_store: Dict[str, List[dict]] = {}


def save_results(session_id: str, videos: List[dict]) -> None:
    existing = {v["video_id"]: v for v in _store.get(session_id, [])}
    for v in videos:
        existing[v["video_id"]] = v
    _store[session_id] = list(existing.values())


def load_results(session_id: str) -> List[dict]:
    return list(_store.get(session_id, []))


def get_analyzed_count(session_id: str) -> int:
    return sum(1 for v in _store.get(session_id, []) if v.get("analyzed"))


def delete_session_cache(session_id: str) -> None:
    _store.pop(session_id, None)
