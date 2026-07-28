"""Step 4 — Pinecone vector store. Upsert · Namespace · Versioning · Stats."""
import os, time
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

_KEY   = os.getenv("PINECONE_API_KEY","")
_IDX   = os.getenv("PINECONE_INDEX","playlistai")
DIM    = 1536

class PineconeVectorStore:
    def __init__(self):
        if not _KEY: raise EnvironmentError("PINECONE_API_KEY is not set.")
        try:
            from pinecone import Pinecone, ServerlessSpec
        except ImportError: raise EnvironmentError("Run: pip install pinecone")
        self._pc=Pinecone(api_key=_KEY)
        if _IDX not in [i.name for i in self._pc.list_indexes()]:
            self._pc.create_index(name=_IDX,dimension=DIM,metric="cosine",
                spec=ServerlessSpec(cloud="aws",region="us-east-1"))
            time.sleep(5)
        self._idx=self._pc.Index(_IDX)

    def upsert_chunks(self,chunks,embeddings:List[List[float]],namespace="default",version="v1") -> int:
        vectors=[]
        for c,e in zip(chunks,embeddings):
            if not e or all(v==0.0 for v in e): continue
            m=c.to_metadata(); m["version"]=version; m["indexed_at"]=time.time()
            vectors.append({"id":c.chunk_id,"values":e,"metadata":m})
        if not vectors: return 0
        n=0
        for i in range(0,len(vectors),100):
            self._idx.upsert(vectors=vectors[i:i+100],namespace=namespace); n+=min(100,len(vectors)-i)
        return n

    def query(self,embedding,top_k=10,namespace="default",filter_dict=None) -> List[Dict]:
        kw={"vector":embedding,"top_k":top_k,"namespace":namespace,"include_metadata":True}
        if filter_dict: kw["filter"]=filter_dict
        r=self._idx.query(**kw)
        return [{"id":m.id,"score":m.score,"metadata":m.metadata or {}} for m in r.matches]

    def delete_video(self,video_id,namespace="default"):
        try: self._idx.delete(filter={"video_id":{"$eq":video_id}},namespace=namespace)
        except: pass

    def video_exists(self,video_id,namespace="default") -> bool:
        try:
            r=self._idx.query(vector=[0.0]*DIM,top_k=1,namespace=namespace,
                filter={"video_id":{"$eq":video_id}},include_metadata=False)
            return len(r.matches)>0
        except: return False

    def get_stats(self) -> Dict:
        try:
            s=self._idx.describe_index_stats()
            return {"total_vectors":s.total_vector_count,"dimension":s.dimension,
                    "namespaces":{k:v.vector_count for k,v in (s.namespaces or {}).items()}}
        except Exception as e: return {"error":str(e)}

_store:Optional[PineconeVectorStore]=None
def get_vector_store() -> PineconeVectorStore:
    global _store
    if _store is None: _store=PineconeVectorStore()
    return _store
