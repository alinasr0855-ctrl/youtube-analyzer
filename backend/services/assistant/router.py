"""
Assistant Router — Single Responsibility.
Decides the execution path given a Classification + context.
"""
from dataclasses import dataclass
from enum import Enum
from backend.services.assistant.classifier import Classification, QuestionType


class ExecutionMode(str, Enum):
    GEMINI_ONLY = "gemini"
    RAG_ONLY    = "rag"
    HYBRID      = "hybrid"


@dataclass
class RoutingDecision:
    mode: ExecutionMode
    reason: str
    rag_available: bool


class AssistantRouter:
    GENERAL_CONFIDENCE_THRESHOLD = 0.75

    def decide(self, classification: Classification, rag_indexed_count: int) -> RoutingDecision:
        has_rag = rag_indexed_count > 0

        if not has_rag:
            return RoutingDecision(
                mode=ExecutionMode.GEMINI_ONLY,
                reason="No indexed transcripts available — using Gemini analysis",
                rag_available=False,
            )

        qt = classification.question_type
        cf = classification.confidence

        if qt == QuestionType.GENERAL and cf >= self.GENERAL_CONFIDENCE_THRESHOLD:
            return RoutingDecision(
                mode=ExecutionMode.GEMINI_ONLY,
                reason=f"General question (confidence={cf:.0%}) — Gemini sufficient",
                rag_available=True,
            )

        if qt == QuestionType.VIDEO_SPECIFIC:
            return RoutingDecision(
                mode=ExecutionMode.RAG_ONLY,
                reason="Video-specific question — retrieving transcript chunks",
                rag_available=True,
            )

        return RoutingDecision(
            mode=ExecutionMode.HYBRID,
            reason=f"{'Hybrid question' if qt == QuestionType.HYBRID else 'Ambiguous general question'} — combining transcript + general knowledge",
            rag_available=True,
        )
