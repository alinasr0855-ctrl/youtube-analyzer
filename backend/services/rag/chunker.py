"""Step 2 — Hybrid Recursive + Sliding Window chunker. Token-based via tiktoken."""
import re, time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def _tok(t): return len(_enc.encode(t))
except ImportError:
    def _tok(t): return max(1,len(t)//4)

@dataclass
class Chunk:
    chunk_id: str; video_id: str; playlist_id: str; text: str
    token_count: int; char_count: int; chunk_index: int; total_chunks: int
    start_time: float; end_time: float; start_char: int; end_char: int
    created_at: float = field(default_factory=time.time)

    def to_metadata(self) -> Dict:
        return {"chunk_id":self.chunk_id,"video_id":self.video_id,"playlist_id":self.playlist_id,
                "text":self.text[:1000],"token_count":self.token_count,"chunk_index":self.chunk_index,
                "total_chunks":self.total_chunks,"start_time":round(self.start_time,2),
                "end_time":round(self.end_time,2),"start_char":self.start_char,"end_char":self.end_char}

class HybridChunker:
    def __init__(self,chunk_size=512,chunk_overlap=64,min_tokens=30):
        self.chunk_size=chunk_size; self.chunk_overlap=chunk_overlap; self.min_tokens=min_tokens

    def chunk(self,doc) -> List[Chunk]:
        tm=self._time_map(doc.full_text,doc.segments)
        raw=self._split(doc.full_text,tm,doc.total_duration)
        raw=[r for r in raw if r["token_count"]>=self.min_tokens]
        total=len(raw)
        return [Chunk(chunk_id=f"{doc.video_id}_c{i:04d}",video_id=doc.video_id,playlist_id=doc.playlist_id,
                      text=r["text"],token_count=r["token_count"],char_count=len(r["text"]),
                      chunk_index=i,total_chunks=total,start_time=r["start_time"],end_time=r["end_time"],
                      start_char=r["start_char"],end_char=r["end_char"]) for i,r in enumerate(raw)]

    def _split(self,text,tm,total_dur):
        sents=self._sentences(text); chunks=[]; cur=""; cs=0; ct=0
        for sent in sents:
            st=_tok(sent)
            if ct+st>self.chunk_size and cur:
                ec=cs+len(cur); chunks.append({"text":cur.strip(),"start_char":cs,"end_char":ec,
                    "token_count":ct,**self._tr(cs,ec,tm,total_dur)})
                ov=self._tail(cur,self.chunk_overlap); cur=ov+" "+sent; cs=ec-len(ov); ct=_tok(cur)
            else:
                if not cur: idx=text.find(sent); cs=idx if idx>=0 else 0
                cur=(cur+" "+sent).strip(); ct+=st
        if cur.strip():
            ec=cs+len(cur); chunks.append({"text":cur.strip(),"start_char":cs,"end_char":ec,
                "token_count":ct,**self._tr(cs,ec,tm,total_dur)})
        return chunks

    def _sentences(self,text):
        return [p.strip() for p in re.split(r'(?<=[.!?؟،\n])\s+',text) if p.strip() and len(p.strip())>5]

    def _tail(self,text,target):
        words=text.split(); return " ".join(words[-max(1,target*3//4):])

    def _time_map(self,text,segs):
        tm=[]; pos=0
        for s in segs:
            idx=text.find(s.text,pos)
            if idx>=0: tm.append((idx,s.start)); pos=idx+len(s.text)
        return tm

    def _tr(self,sc,ec,tm,total):
        if not tm: return {"start_time":0.0,"end_time":total}
        st,et=0.0,total
        for cp,t in tm:
            if cp<=sc: st=t
            if cp<=ec: et=t
        return {"start_time":st,"end_time":min(et+30,total)}
