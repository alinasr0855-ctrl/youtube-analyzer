"""Step 6 — Context Builder: sort → deduplicate → token budget → format."""
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import tiktoken; _enc=tiktoken.get_encoding("cl100k_base")
    def _tok(t): return len(_enc.encode(t))
except ImportError:
    def _tok(t): return max(1,len(t)//4)

@dataclass
class BuiltContext:
    context_text: str; sources: List[Dict]; total_tokens: int; chunk_count: int

class ContextBuilder:
    SEP="\n\n---\n\n"
    def __init__(self,max_tokens=6000): self.max_tokens=max_tokens

    def build(self,results,video_metadata=None) -> BuiltContext:
        if not results: return BuiltContext("",[], 0, 0)
        ordered=sorted(results,key=lambda r:r.chunk_index)
        blocks=[]; sources=[]; budget=self.max_tokens; sc=_tok(self.SEP)
        for r in ordered:
            block=self._fmt(r,video_metadata); cost=_tok(block)+sc
            if cost>budget: break
            blocks.append(block); budget-=cost
            sources.append({"chunk_id":r.chunk_id,"video_id":r.video_id,"score":round(r.score,3),
                "start_time":r.start_time,"end_time":r.end_time,"timestamp":self._ts(r.start_time)})
        text=self.SEP.join(blocks)
        return BuiltContext(context_text=text,sources=sources,total_tokens=_tok(text),chunk_count=len(blocks))

    def _fmt(self,r,meta):
        ts=self._ts(r.start_time); title=""
        if meta and r.video_id in meta: title=meta[r.video_id].get("title","")
        header=f"[{ts}]"+(f" ({title})" if title else "")
        return f"{header}\n{r.text}"

    @staticmethod
    def _ts(s):
        s=max(0,int(s)); h,m,sec=s//3600,(s%3600)//60,s%60
        return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
