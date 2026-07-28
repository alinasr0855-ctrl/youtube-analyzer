"""Step 3 — Voyage AI embeddings. Batching · Disk cache · Retry · Rate limiting."""
import hashlib, json, os, time, threading
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

_KEY   = os.getenv("VOYAGE_API_KEY","")
_CACHE = Path(__file__).resolve().parent.parent.parent.parent/".embedding_cache.json"
MODEL  = "voyage-large-2"; DIM=1536; BATCH=128; RETRIES=3; RATE=300

class _Cache:
    def __init__(self):
        self._d: Dict[str,List[float]] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self):
        if self._loaded: return
        if _CACHE.exists():
            try: self._d = json.loads(_CACHE.read_text(encoding="utf-8"))
            except: self._d = {}
        self._loaded = True

    def _save(self):
        try: _CACHE.write_text(json.dumps(self._d,ensure_ascii=False), encoding="utf-8")
        except: pass

    def get(self, key: str) -> Optional[List[float]]:
        with self._lock: self._load(); return self._d.get(key)

    def set(self, key: str, val: List[float]):
        with self._lock: self._load(); self._d[key]=val; self._save()

_emb_cache = _Cache()

def _key(text: str, input_type: str) -> str:
    return hashlib.md5(f"{MODEL}:{input_type}:{text}".encode()).hexdigest()

class VoyageEmbedder:
    def __init__(self):
        if not _KEY:
            raise EnvironmentError("VOYAGE_API_KEY is not set. Required for RAG embeddings.")
        import voyageai
        self._client = voyageai.Client(api_key=_KEY)

    def embed_texts(self, texts: List[str], input_type: str = "document") -> List[List[float]]:
        results: List[Optional[List[float]]] = [None] * len(texts)
        to_embed = []
        for i, t in enumerate(texts):
            cached = _emb_cache.get(_key(t, input_type))
            if cached: results[i] = cached
            else: to_embed.append((i, t))

        for batch_start in range(0, len(to_embed), BATCH):
            batch = to_embed[batch_start:batch_start+BATCH]
            idxs, txts = zip(*batch)
            for attempt in range(RETRIES):
                try:
                    resp = self._client.embed(list(txts), model=MODEL, input_type=input_type)
                    for i, emb in zip(idxs, resp.embeddings):
                        results[i] = emb
                        _emb_cache.set(_key(txts[idxs.index(i)], input_type), emb)
                    break
                except Exception as e:
                    if attempt < RETRIES-1: time.sleep(2**attempt)
                    else: results[i] = [0.0]*DIM

        return [r if r else [0.0]*DIM for r in results]

    def embed_query(self, query: str) -> List[float]:
        cached = _emb_cache.get(_key(query, "query"))
        if cached: return cached
        result = self.embed_texts([query], "query")
        return result[0] if result else [0.0]*DIM

    @staticmethod
    def validate(embedding: List[float]) -> bool:
        return bool(embedding) and len(embedding) == DIM and not all(v==0.0 for v in embedding)


class FallbackEmbedder:
    """Dummy embedder when Voyage API key is not set — enables graceful degradation."""
    def embed_texts(self, texts, input_type="document"): return [[0.0]*DIM for _ in texts]
    def embed_query(self, query): return [0.0]*DIM
    @staticmethod
    def validate(embedding): return False


_embedder_instance = None

def get_embedder():
    global _embedder_instance
    if _embedder_instance is None:
        try: _embedder_instance = VoyageEmbedder()
        except EnvironmentError: _embedder_instance = FallbackEmbedder()
    return _embedder_instance
