"""
Question Classifier — Single Responsibility.
Classifies each question as General, VideoSpecific, or Hybrid
using keyword scoring. Zero API calls — instant, deterministic.

Open/Closed: add new signal lists without touching scoring logic.
"""
from dataclasses import dataclass
from enum import Enum
from typing import List
import re


class QuestionType(str, Enum):
    GENERAL        = "general"
    VIDEO_SPECIFIC = "video_specific"
    HYBRID         = "hybrid"


@dataclass
class Classification:
    question_type: QuestionType
    confidence: float      # 0.0 – 1.0
    video_score: float
    general_score: float
    reason: str


# ── Signal lists ───────────────────────────────────────────────────────────────

_VIDEO_SIGNALS: List[str] = [
    # Arabic — explicit video references
    "في الفيديو", "في هذا الفيديو", "ذكر", "قال", "أشار", "تحدث",
    "شرح في", "في الدقيقة", "في الوقت", "المحاضرة", "ما ورد",
    "ما جاء", "ما قيل", "هل ذكر", "هل قال", "هل أشار",
    "في التسجيل", "في المقطع", "في الشرح", "المدرس", "المحاضر",
    "في الجزء", "في المقدمة", "في الخلاصة", "في الدرس",
    # English
    "in the video", "in this video", "mentioned", "said", "explained",
    "at minute", "at timestamp", "transcript", "lecture", "the instructor",
    "did he say", "was it mentioned", "in the clip", "in the lesson",
    "the speaker", "according to the video",
]

_GENERAL_SIGNALS: List[str] = [
    # Arabic — general knowledge queries
    "ما هو", "ما هي", "ما معنى", "عرّف", "اشرح بشكل عام",
    "ما الفرق بين", "قارن بين", "أفضل الممارسات", "كيف يعمل",
    "ما هي أنواع", "ما فوائد", "ما عيوب", "متى ظهر",
    "من اخترع", "ما تاريخ", "كيف أتعلم", "ما المقصود",
    # English
    "what is", "what are", "define", "explain in general",
    "difference between", "compare", "best practices",
    "how does it work", "types of", "benefits of",
    "history of", "who invented", "how to learn",
)

_HYBRID_SIGNALS: List[str] = [
    # Questions that benefit from both sources
    "كيف أطبق", "كيف أستخدم ما تعلمته", "أعطني مزيداً",
    "وضّح أكثر", "أكمل الشرح", "هل يمكنك توسيع",
    "ما الذي يجب أن أعرفه أيضاً", "أريد فهماً أعمق",
    "give me more", "elaborate", "expand on", "dive deeper",
    "tell me more about", "can you also explain",
]


class QuestionClassifier:
    """
    Scores a question against three signal lists and returns
    the most likely QuestionType with a confidence score.
    """

    VIDEO_WEIGHT   = 1.0
    GENERAL_WEIGHT = 1.0
    HYBRID_WEIGHT  = 1.2   # slight bias toward hybrid when signals present

    # Thresholds
    DOMINANCE_RATIO  = 1.5   # one score must be N× the other to win outright
    MIN_SIGNAL_SCORE = 0.15  # below this → default to GENERAL

    def classify(self, question: str) -> Classification:
        q = question.lower()

        vs  = self._score(q, _VIDEO_SIGNALS)   * self.VIDEO_WEIGHT
        gs  = self._score(q, _GENERAL_SIGNALS) * self.GENERAL_WEIGHT
        hs  = self._score(q, _HYBRID_SIGNALS)  * self.HYBRID_WEIGHT
        total = vs + gs + hs + 1e-9

        # Normalize
        vs_n = vs / total
        gs_n = gs / total
        hs_n = hs / total

        # Decision logic
        if hs > 0:
            qtype = QuestionType.HYBRID
            confidence = min(0.95, hs_n + 0.3)
            reason = f"Hybrid signals detected (score={hs:.2f})"

        elif vs > 0 and gs > 0:
            # Both present — pick dominant, else hybrid
            if vs > gs * self.DOMINANCE_RATIO:
                qtype = QuestionType.VIDEO_SPECIFIC
                confidence = min(0.95, vs_n + 0.2)
                reason = f"Video signals dominate (vs={vs:.2f} > gs={gs:.2f})"
            elif gs > vs * self.DOMINANCE_RATIO:
                qtype = QuestionType.GENERAL
                confidence = min(0.95, gs_n + 0.2)
                reason = f"General signals dominate (gs={gs:.2f} > vs={vs:.2f})"
            else:
                qtype = QuestionType.HYBRID
                confidence = 0.60
                reason = f"Mixed signals (vs={vs:.2f}, gs={gs:.2f})"

        elif vs > self.MIN_SIGNAL_SCORE:
            qtype = QuestionType.VIDEO_SPECIFIC
            confidence = min(0.90, vs_n + 0.25)
            reason = f"Video-specific signals (score={vs:.2f})"

        elif gs > self.MIN_SIGNAL_SCORE:
            qtype = QuestionType.GENERAL
            confidence = min(0.90, gs_n + 0.25)
            reason = f"General knowledge signals (score={gs:.2f})"

        else:
            # No strong signals → default to HYBRID for best UX
            qtype = QuestionType.HYBRID
            confidence = 0.50
            reason = "No strong signals — defaulting to Hybrid for best coverage"

        return Classification(
            question_type=qtype,
            confidence=round(confidence, 3),
            video_score=round(vs, 4),
            general_score=round(gs, 4),
            reason=reason,
        )

    @staticmethod
    def _score(question: str, signals: List[str]) -> float:
        """Count how many signals appear in the question, normalized by question length."""
        hits = sum(1 for sig in signals if sig.lower() in question)
        # Normalize: more hits = higher score, diminishing returns
        return hits / (hits + 3) if hits > 0 else 0.0
