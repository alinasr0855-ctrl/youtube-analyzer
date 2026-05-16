"""Persistent file-based cache for video analysis results, keyed by video_id."""
import json
from pathlib import Path
from typing import Dict, Optional

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / ".video_analysis_cache.json"
_cache: Dict[str, dict] = {}
_loaded = False


def _load() -> None:
    global _cache, _loaded
    if _loaded:
        return
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    _loaded = True


def _save() -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get(video_id: str) -> Optional[dict]:
    """Return cached analysis for a video_id, or None if not cached."""
    _load()
    return _cache.get(video_id)


def set(video_id: str, data: dict) -> None:
    """Cache analysis result for a video_id and persist to disk."""
    _load()
    _cache[video_id] = data
    _save()


def size() -> int:
    _load()
    return len(_cache)
