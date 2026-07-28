"""
RAG Service Orchestrator.
INDEX : Ingestion → Chunking → Embedding → Validation → Pinecone
QUERY : Embed → Retrieve → Context → Prompt → Gemini → Post-process

retrieve_context() is exposed so the AssistantService can use it
directly for Hybrid mode without duplicating retrieval logic.
"""
import json, re, time
from typing import Dict, List, Optional, Tuple

from backend.services.rag.ingestion       import DocumentIngester
from backend.services.rag.chunker         import HybridChunker
from backend.services.rag.retriever       import RAGRetriever, RetrievalResult
from backend.services.rag.context_builder import ContextBuilder, BuiltContext
from backend.services.rag.prompt_engineer import PromptEngineer


class RAGService:

    def __init__(self):
        self.ingester    = DocumentIngester()
        self.chunker     = HybridChunker(chunk_size=512, chunk_overlap=64)
        self.retriever   = RAGRetriever(top_k=10, score_threshold=0.30, mmr_top_n=5)
        self.ctx_builder = ContextBuilder(max_context_tokens=6000)
        self.prompter    = PromptEngineer()
        self._embedder   = None
        self._vs         = None

    # ── Lazy singletons ────────────────────────────────────────────────────────
    @property
    def embedder(self):
        if self._embedder is None:
            from backend.services.rag.embedder import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    @property
    def vs(self):
        if self._vs is None:
            from backend.services.rag.vector_store import get_vector_store
            self._vs = get_vector_store()
        return self._vs

    # ── INDEX ──────────────────────────────────────────────────────────────────
    def index_video(self, video_id: str, meta: Dict, force: bool = False) -> Dict:
        t0 = time.time()
        ns = meta.get("playlist_id", "default")

        if not force:
            try:
                if self.vs.video_exists(video_id, ns):
                    return {"status":"already_indexed","video_id":video_id,"chunks":0,"duration_s":0}
            except Exception:
                pass

        doc = self.ingester.ingest(video_id, meta)
        if not doc:
            return {"status":"no_transcript","video_id":video_id,"chunks":0,"duration_s":round(time.time()-t0,2)}

        chunks = self.chunker.chunk(doc)
        if not chunks:
            return {"status":"chunking_failed","video_id":video_id,"chunks":0,"duration_s":round(time.time()-t0,2)}

        embeddings = self.embedder.embed_texts([c.text for c in chunks], "document")
        pairs = [(c,e) for c,e in zip(chunks,embeddings) if self.embedder.validate(e)]
        if not pairs:
            return {"status":"embedding_failed","video_id":video_id,"chunks":0,"duration_s":round(time.time()-t0,2)}

        vc, ve = zip(*pairs)
        version  = f"v{int(time.time())}"
        upserted = self.vs.upsert_chunks(list(vc), list(ve), namespace=ns, version=version)

        return {"status":"indexed","video_id":video_id,"chunks":upserted,
                "language":doc.language,"word_count":doc.word_count,
                "duration_s":round(time.time()-t0,2),"version":version}

    def index_session(self, videos: List[Dict], session_meta: Dict, force: bool = False) -> Dict:
        results = []
        total_chunks = 0
        for v in videos:
            meta = {"title":v.get("title",""),"channel_name":session_meta.get("channel_name",""),
                    "channel_id":session_meta.get("channel_id",""),
                    "playlist_id":session_meta.get("playlist_id",""),
                    "playlist_name":session_meta.get("playlist_name","")}
            r = self.index_video(v["video_id"], meta, force)
            results.append(r); total_chunks += r.get("chunks",0)
        indexed = sum(1 for r in results if r["status"] in ("indexed","already_indexed"))
        return {"indexed_videos":indexed,"total_chunks":total_chunks,"results":results}

    # ── RETRIEVE CONTEXT (used by AssistantService for Hybrid mode) ────────────
    def retrieve_context(
        self,
        question: str,
        session_meta: Dict,
        video_ids: Optional[List[str]] = None,
    ) -> Tuple[BuiltContext, List[RetrievalResult]]:
        """
        Retrieves relevant chunks and builds context WITHOUT generating.
        Exposed so AssistantService can use it for Hybrid mode,
        avoiding duplication of retrieval logic.
        """
        ns      = session_meta.get("playlist_id", "default")
        q_emb   = self.embedder.embed_query(question)
        results = self.retriever.retrieve(
            query_embedding=q_emb, vector_store=self.vs, namespace=ns,
            video_ids=video_ids, playlist_id=session_meta.get("playlist_id"),
        )
        ctx = self.ctx_builder.build(results)
        return ctx, results

    # ── FULL QUERY (RAG-only mode) ─────────────────────────────────────────────
    def query(
        self,
        question: str,
        session_meta: Dict,
        chat_history: List[Dict],
        video_ids: Optional[List[str]] = None,
    ) -> Dict:
        t0 = time.time()
        ctx, results = self.retrieve_context(question, session_meta, video_ids)
        prompt  = self.prompter.build_rag_prompt(question, ctx, chat_history, session_meta)
        raw     = self._generate(prompt)
        parsed  = self._parse(raw, bool(results))

        return {
            "answer":               parsed["answer"],
            "referenced_videos":    self._video_refs(ctx.sources),
            "sources":              ctx.sources,
            "confidence":           parsed.get("confidence","medium"),
            "has_sufficient_context": parsed.get("has_sufficient_context", bool(results)),
            "retrieval_count":      len(results),
            "context_tokens":       ctx.total_tokens,
            "duration_s":           round(time.time()-t0,2),
        }

    # ── Internal ───────────────────────────────────────────────────────────────
    def _generate(self, prompt: str) -> str:
        from backend.services.gemini_service import _call_model
        try: return _call_model(prompt)
        except Exception as e:
            return json.dumps({"answer":f"تعذر الإجابة: {e}","referenced_timestamps":[],
                               "confidence":"low","has_sufficient_context":False})

    def _parse(self, raw: str, has_ctx: bool) -> Dict:
        raw = raw.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if m: raw = m.group(1).strip()
        try:
            p = json.loads(raw)
            if "answer" in p: return p
        except Exception: pass
        return {"answer":raw,"referenced_timestamps":[],"confidence":"medium","has_sufficient_context":has_ctx}

    def _video_refs(self, sources: List[Dict]) -> List[Dict]:
        seen, refs = set(), []
        for s in sources:
            vid = s.get("video_id","")
            if vid and vid not in seen:
                seen.add(vid)
                refs.append({"video_id":vid,"timestamp":s.get("timestamp","00:00"),"score":s.get("score",0)})
        return refs

    def get_stats(self) -> Dict:
        try: return self.vs.get_stats()
        except Exception as e: return {"error":str(e)}


_rag: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    global _rag
    if _rag is None: _rag = RAGService()
    return _rag
