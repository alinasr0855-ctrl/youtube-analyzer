from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChannelSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)

class StartSessionRequest(BaseModel):
    playlist_id: str
    channel_id: Optional[str] = ""
    channel_name: Optional[str] = "Unknown Channel"
    playlist_name: Optional[str] = "Unknown Playlist"

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str

# ── AI Assistant (unified Chat + RAG) ─────────────────────────────────────────
class AssistantRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: Optional[List[ChatMessage]] = []
    video_ids: Optional[List[str]] = None   # optional filter to specific videos

class AssistantResponse(BaseModel):
    answer: str
    mode: str                               # "gemini" | "rag" | "hybrid"
    classification: str                     # "general" | "video_specific" | "hybrid"
    sources: Optional[List[Dict[str, Any]]] = []
    referenced_videos: Optional[List[Dict[str, Any]]] = []
    confidence: str = "medium"              # "high" | "medium" | "low"
    retrieval_count: int = 0
    context_tokens: int = 0
    duration_s: float = 0.0

# ── RAG Index ──────────────────────────────────────────────────────────────────
class RAGIndexRequest(BaseModel):
    video_id: Optional[str] = None
    force_reindex: bool = False

# ── Compare ───────────────────────────────────────────────────────────────────
class CompareRequest(BaseModel):
    session_id_a: str
    session_id_b: str

# ── Legacy (kept for backwards compat) ────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: Optional[List[ChatMessage]] = []

class ChatResponse(BaseModel):
    answer: str
    referenced_videos: Optional[List[Dict[str, Any]]] = []
