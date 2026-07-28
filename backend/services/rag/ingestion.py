"""Step 1 — Transcript download, cleaning, validation, metadata extraction."""
import re, time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

@dataclass
class TranscriptSegment:
    text: str; start: float; duration: float
    @property
    def end(self): return self.start + self.duration

@dataclass
class IngestedDocument:
    video_id: str; title: str; channel_name: str; channel_id: str
    playlist_id: str; playlist_name: str; full_text: str
    segments: List[TranscriptSegment]; language: str
    total_duration: float; word_count: int; char_count: int
    ingested_at: float = field(default_factory=time.time)

class DocumentIngester:
    PREFERRED = ["ar","en"]
    MIN_CHARS = 100

    def ingest(self, video_id: str, meta: Dict) -> Optional[IngestedDocument]:
        segs, lang = self._download(video_id)
        if not segs: return None
        cleaned = self._clean(segs)
        if not cleaned: return None
        text = self._build_text(cleaned)
        if len(text) < self.MIN_CHARS: return None
        return IngestedDocument(
            video_id=video_id, title=meta.get("title",""),
            channel_name=meta.get("channel_name",""), channel_id=meta.get("channel_id",""),
            playlist_id=meta.get("playlist_id",""), playlist_name=meta.get("playlist_name",""),
            full_text=text, segments=cleaned, language=lang,
            total_duration=cleaned[-1].end if cleaned else 0.0,
            word_count=len(text.split()), char_count=len(text))

    def _download(self, vid) -> Tuple[List[TranscriptSegment], str]:
        def _p(raw): return [TranscriptSegment(s["text"],s["start"],s.get("duration",0.0)) for s in raw]
        for lang in self.PREFERRED:
            try: return _p(YouTubeTranscriptApi.get_transcript(vid,languages=[lang])), lang
            except: continue
        try: return _p(YouTubeTranscriptApi.get_transcript(vid)), "unknown"
        except: return [], "unknown"

    def _clean(self, segs):
        out=[]
        for s in segs:
            t=re.sub(r"<[^>]+>"," ",s.text); t=re.sub(r"\[.*?\]","",t); t=re.sub(r"\s+"," ",t).strip()
            if t: out.append(TranscriptSegment(t,s.start,s.duration))
        return out

    def _build_text(self, segs):
        parts=[]
        for s in segs:
            if parts and not parts[-1][-1] in ".!?،؟" and s.text and s.text[0].isupper(): parts[-1]+="."
            parts.append(s.text)
        return " ".join(parts)
