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
        self._d:Dict[str,List[float]]={};self._lk=threading.Lock();self._ok=False
    def _load(self):
        if self._ok: return
        if _CACHE.exists():
            try: self._d=json.loads(_CACHE.read_text())
            except: self._d={}
        self._ok=True
    def _save(self):
        try: _CACHE.write_text(json.dumps(self._d))
        except: pass
    @staticmethod
    def _k(t): return hashlib.md5(f"{MODEL}:{t}".encode()).hexdigest()
    def get(self,t): 
        with self._lk: self._load(); return self._d.get(self._k(t))
    def set(self,t,e):
        with self._lk: self._load(); self._d[self._k(t)]=e; self._save()

class _Limiter:
    def __init__(self,rpm):
        self.rpm=rpm;self._tok=float(rpm);self._last=time.time();self._lk=threading.Lock()
    def acquire(self):
        with self._lk:
            now=time.time(); self._tok=min(self.rpm,self._tok+(now-self._last)*(self.rpm/60)); self._last=now
            if self._tok<1: time.sleep((1-self._tok)*60/self.rpm); self._tok=0.0
            else: self._tok-=1.0

class VoyageEmbedder:
    def __init__(self):
        if not _KEY: raise EnvironmentError("VOYAGE_API_KEY is not set.")
        try:
            import voyageai; self._c=voyageai.Client(api_key=_KEY)
        except ImportError: raise EnvironmentError("Run: pip install voyageai")
        self._cache=_Cache(); self._lim=_Limiter(RATE)

    def embed_texts(self,texts:List[str],input_type="document") -> List[List[float]]:
        res=[None]*len(texts); miss_i=[]; miss_t=[]
        for i,t in enumerate(texts):
            c=self._cache.get(t)
            if c: res[i]=c
            else: miss_i.append(i); miss_t.append(t)
        if miss_t:
            embs=self._batch(miss_t,input_type)
            for i,e in zip(miss_i,embs):
                if e: res[i]=e; self._cache.set(texts[i],e)
        zero=[0.0]*DIM; return [r if r else zero for r in res]

    def embed_query(self,q:str) -> List[float]:
        return self.embed_texts([q],"query")[0]

    def validate(self,e:List[float]) -> bool:
        return bool(e) and len(e)==DIM and not all(v==0.0 for v in e)

    def _batch(self,texts,input_type):
        all_e=[]
        for i in range(0,len(texts),BATCH):
            all_e.extend(self._retry(texts[i:i+BATCH],input_type))
        return all_e

    def _retry(self,texts,input_type):
        for a in range(RETRIES):
            try:
                self._lim.acquire(); r=self._c.embed(texts,model=MODEL,input_type=input_type)
                return list(r.embeddings)
            except Exception as e:
                if a<RETRIES-1: time.sleep(2*(2**a)); continue
                return [None]*len(texts)
        return [None]*len(texts)

_emb:Optional[VoyageEmbedder]=None
def get_embedder() -> VoyageEmbedder:
    global _emb
    if _emb is None: _emb=VoyageEmbedder()
    return _emb
