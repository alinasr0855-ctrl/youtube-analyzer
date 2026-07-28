"""Persistent disk cache for video analysis. Thread-safe."""
import json, threading
from pathlib import Path
from typing import Dict, Optional

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / ".video_analysis_cache.json"
_cache: Dict[str, dict] = {}
_loaded = False
_lock = threading.Lock()

def _load():
    global _cache, _loaded
    if _loaded: return
    if _CACHE_FILE.exists():
        try: _cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except: _cache = {}
    _loaded = True

def _save():
    try: _CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except: pass

def get(video_id: str) -> Optional[dict]:
    with _lock: _load(); return _cache.get(video_id)

def set(video_id: str, analysis: dict) -> None:
    with _lock: _load(); _cache[video_id] = analysis; _save()

def size() -> int:
    with _lock: _load(); return len(_cache)
