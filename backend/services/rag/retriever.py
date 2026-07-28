"""Step 5 — MMR retriever with deduplication."""
from typing import Dict, List, Optional


class RetrievalResult:
    def __init__(self,chunk_id,text,score,metadata):
        self.chunk_id=chunk_id; self.text=text; self.score=score; self.metadata=metadata
        self.video_id=metadata.get("video_id",""); self.start_time=float(metadata.get("start_time",0))
        self.end_time=float(metadata.get("end_time",0)); self.chunk_index=int(metadata.get("chunk_index",0))

class RAGRetriever:
    def __init__(self,top_k=10,score_threshold=0.30,mmr_lambda=0.70,mmr_top_n=5,dedup_threshold=0.92):
        self.top_k=top_k; self.score_threshold=score_threshold
        self.mmr_lambda=mmr_lambda; self.mmr_top_n=mmr_top_n; self.dedup_threshold=dedup_threshold

    def retrieve(self,query_embedding,vector_store,namespace="default",
                 video_ids=None,playlist_id=None) -> List[RetrievalResult]:
        f=self._filter(video_ids,playlist_id)
        raw=vector_store.query(embedding=query_embedding,top_k=self.top_k*2,namespace=namespace,filter_dict=f)
        results=[RetrievalResult(r["id"],r["metadata"].get("text",""),r["score"],r["metadata"]) for r in raw]
        results=[r for r in results if r.score>=self.score_threshold][:self.top_k]
        results=self._mmr(results)
        return self._dedup(results)

    def _filter(self,video_ids,playlist_id):
        if video_ids and len(video_ids)==1: return {"video_id":{"$eq":video_ids[0]}}
        if video_ids: return {"video_id":{"$in":video_ids}}
        if playlist_id: return {"playlist_id":{"$eq":playlist_id}}
        return None

    def _mmr(self,results):
        if len(results)<=self.mmr_top_n: return results
        sel=[results[0]]; rem=list(results[1:])
        while len(sel)<self.mmr_top_n and rem:
            best=-1e9; bi=0
            for i,c in enumerate(rem):
                ms=max(self._jac(c.text,s.text) for s in sel)
                score=self.mmr_lambda*c.score-(1-self.mmr_lambda)*ms
                if score>best: best=score; bi=i
            sel.append(rem.pop(bi))
        return sel

    def _dedup(self,results):
        u=[]
        for c in results:
            if not any(self._jac(c.text,x.text)>=self.dedup_threshold for x in u): u.append(c)
        return u

    @staticmethod
    def _jac(a,b):
        wa,wb=set(a.lower().split()),set(b.lower().split())
        if not wa or not wb: return 0.0
        return len(wa&wb)/len(wa|wb)
