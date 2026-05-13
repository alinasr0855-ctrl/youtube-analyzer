from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChannelSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Channel name, URL, or direct playlist URL")


class PlaylistSelectRequest(BaseModel):
    channel_id: str
    playlist_id: str


class BatchAnalyzeRequest(BaseModel):
    session_id: str


class VideoSummary(BaseModel):
    video_id: str
    title: str
    position: int
    thumbnail: Optional[str] = None
    explanation: Optional[str] = None
    analyzed: bool = False
    level: Optional[str] = None
    type: Optional[str] = None
    topics: Optional[List[str]] = []
    estimated_minutes: Optional[int] = None
    requires_previous: Optional[bool] = False


class PlaylistInfo(BaseModel):
    playlist_id: str
    title: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    video_count: int = 0
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None


class ChannelInfo(BaseModel):
    channel_id: str
    title: str
    description: Optional[str] = None
    thumbnail: Optional[str] = None
    subscriber_count: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: str
    channel_name: str
    playlist_name: str
    playlist_id: str
    channel_id: str
    total_videos: int
    analyzed_count: int
    last_batch: int
    last_updated: str
    status: str  # "in_progress" | "completed"
    summary: Optional[str] = None


class BatchResult(BaseModel):
    session_id: str
    batch_number: int
    videos: List[VideoSummary]
    analyzed_count: int
    total_videos: int
    is_complete: bool


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: Optional[List[ChatMessage]] = []


class ChatResponse(BaseModel):
    answer: str
    referenced_videos: Optional[List[Dict[str, Any]]] = []


class CompareRequest(BaseModel):
    session_id_a: str
    session_id_b: str


class StartSessionRequest(BaseModel):
    playlist_id: str
    channel_id: Optional[str] = ""
    channel_name: Optional[str] = "Unknown Channel"
    playlist_name: Optional[str] = "Unknown Playlist"
