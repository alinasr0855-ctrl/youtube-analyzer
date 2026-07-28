"""
AI Assistant Service — Orchestrator.
Flow:
  1. Classify question  (QuestionClassifier)
  2. Route              (AssistantRouter)
  3. Execute path:
       GEMINI_ONLY → gemini_service.chat_with_playlist()
       RAG_ONLY    → rag_service.query()           [with auto-fallback]
       HYBRID      → rag_service.retrieve_context()
                     + prompt_engineer.build_hybrid_prompt()
                     + gemini_service._call_model()
  4. Return unified AssistantResponse dict
"""
import json, re, time
from typing import Dict, List, Optional

from backend.services.assistant.classifier import QuestionClassifier
from backend.services.assistant.router     import AssistantRouter, ExecutionMode


class AssistantService:

    def __init__(self):
        self._classifier = QuestionClassifier()
        self._router     = AssistantRouter()
        self._rag        = None

    @property
    def rag(self):
        if self._rag is None:
            from backend.services.rag.rag_service import get_rag_service
            self._rag = get_rag_service()
        return self._rag

    def handle(self, question: str, session: Dict, history: List[Dict],
               analyzed_videos: List[Dict], video_ids: Optional[List[str]] = None) -> Dict:
        t0 = time.time()
        clf      = self._classifier.classify(question)
        rag_count = session.get("rag_indexed_count", 0)
        decision  = self._router.decide(clf, rag_count)
        result    = self._execute(decision, question, session, history, analyzed_videos, video_ids)
        result["classification"] = clf.question_type.value
        result["routing_reason"] = decision.reason
        result["duration_s"]     = round(time.time() - t0, 2)
        return result

    def _execute(self, decision, question, session, history, analyzed_videos, video_ids):
        if decision.mode == ExecutionMode.GEMINI_ONLY:
            return self._gemini(question, session, analyzed_videos, history)
        if decision.mode == ExecutionMode.RAG_ONLY:
            return self._rag_only(question, session, history, video_ids)
        return self._hybrid(question, session, history, analyzed_videos, video_ids)

    def _gemini(self, question, session, analyzed_videos, history) -> Dict:
        from backend.services.gemini_service import chat_with_playlist
        r = chat_with_playlist(question=question, videos=analyzed_videos,
                               playlist_name=session.get("playlist_name",""), chat_history=history)
        return {"answer":r.get("answer",""),"mode":"gemini","sources":[],
                "referenced_videos":r.get("referenced_videos",[]),
                "confidence":"high","retrieval_count":0,"context_tokens":0}

    def _rag_only(self, question, session, history, video_ids) -> Dict:
        try:
            r = self.rag.query(question=question, session_meta=session,
                               chat_history=history, video_ids=video_ids)
            if r.get("retrieval_count", 0) == 0:
                from backend.services import cache_service
                analyzed = [v for v in cache_service.load_results(session["session_id"]) if v.get("analyzed")]
                fallback = self._gemini(question, session, analyzed, history)
                fallback["mode"] = "gemini"
                fallback["routing_reason"] = "RAG returned 0 results — fell back to Gemini"
                return fallback
            return {"answer":r.get("answer",""),"mode":"rag","sources":r.get("sources",[]),
                    "referenced_videos":r.get("referenced_videos",[]),
                    "confidence":r.get("confidence","medium"),
                    "retrieval_count":r.get("retrieval_count",0),
                    "context_tokens":r.get("context_tokens",0)}
        except Exception:
            from backend.services import cache_service
            analyzed = [v for v in cache_service.load_results(session["session_id"]) if v.get("analyzed")]
            fallback = self._gemini(question, session, analyzed, history)
            fallback["mode"] = "gemini"
            fallback["routing_reason"] = "RAG pipeline error — fell back to Gemini"
            return fallback

    def _hybrid(self, question, session, history, analyzed_videos, video_ids) -> Dict:
        try:
            ctx, results = self.rag.retrieve_context(question, session, video_ids)
            if not results:
                fallback = self._gemini(question, session, analyzed_videos, history)
                fallback["mode"] = "gemini"
                fallback["routing_reason"] = "Hybrid retrieval empty — fell back to Gemini"
                return fallback
            from backend.services.rag.prompt_engineer import PromptEngineer
            from backend.services.gemini_service      import _call_model, _safe_json
            prompt = PromptEngineer().build_hybrid_prompt(question, ctx, history, session)
            raw    = _call_model(prompt)
            parsed = _safe_json(raw) or {}
            return {"answer":parsed.get("answer",raw),"mode":"hybrid",
                    "sources":ctx.sources,"referenced_videos":self.rag._video_refs(ctx.sources),
                    "confidence":parsed.get("confidence","medium"),
                    "retrieval_count":len(results),"context_tokens":ctx.total_tokens}
        except Exception:
            fallback = self._gemini(question, session, analyzed_videos, history)
            fallback["mode"] = "gemini"
            fallback["routing_reason"] = "Hybrid generation error — fell back to Gemini"
            return fallback


_svc: Optional[AssistantService] = None

def get_assistant_service() -> AssistantService:
    global _svc
    if _svc is None: _svc = AssistantService()
    return _svc
