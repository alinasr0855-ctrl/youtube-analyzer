"""
Step 7 — Prompt Engineering.
Two prompt builders:
  build_rag_prompt()    → strict transcript-only (RAG mode)
  build_hybrid_prompt() → transcript + general knowledge (Hybrid mode)
"""
from typing import Dict, List, Optional
from backend.services.rag.context_builder import BuiltContext


_RAG_SYSTEM = """أنت مساعد ذكي متخصص في الإجابة على أسئلة حول محتوى YouTube التعليمي.

## قواعد صارمة:
1. أجب فقط بناءً على السياق المقدم أدناه.
2. إذا لم يكن السياق كافياً، صرّح بذلك صراحةً.
3. لا تخترع أي معلومة غير موجودة في السياق.
4. استشهد دائماً بالطوابع الزمنية [MM:SS] الموجودة في السياق.
5. قل بالضبط "هذه المعلومة غير متوفرة في المحتوى المحلَّل" إذا لم تجد إجابة."""

_HYBRID_SYSTEM = """أنت مساعد ذكي يمتلك مصدرين للمعرفة:

**المصدر 1 — نصوص الفيديو:** مقاطع مسترجعة من تسجيلات YouTube (مقدمة أدناه مع طوابع زمنية).
**المصدر 2 — معرفتك العامة:** كنموذج ذكاء اصطناعي.

## قواعد الإجابة:
1. استخدم نصوص الفيديو أولاً للتفاصيل المحددة — مع الاستشهاد بالطوابع الزمنية [MM:SS].
2. أثرِ الإجابة بمعرفتك العامة عند الحاجة أو لسد الفجوات.
3. ميّز بوضوح: ما جاء من الفيديو وما جاء من معرفتك العامة.
4. لا تخترع معلومات وتدّعي أنها من الفيديو إذا لم تكن في السياق."""

_OUTPUT_SCHEMA = """
## تعليمات الإخراج — أجب بـ JSON فقط:
{
  "answer": "إجابتك الكاملة",
  "referenced_timestamps": ["00:00"],
  "confidence": "high | medium | low",
  "has_sufficient_context": true
}"""


class PromptEngineer:

    def build_rag_prompt(self, question, context, chat_history, session_metadata=None):
        return self._assemble(_RAG_SYSTEM, question, context, chat_history, session_metadata)

    def build_hybrid_prompt(self, question, context, chat_history, session_metadata=None):
        return self._assemble(_HYBRID_SYSTEM, question, context, chat_history, session_metadata)

    def _assemble(self, system, question, context, chat_history, session_metadata):
        parts = [system]
        if session_metadata:
            pl = session_metadata.get("playlist_name",""); ch = session_metadata.get("channel_name","")
            if pl: parts.append(f"\n## المحتوى المحلَّل: {pl}" + (f" | القناة: {ch}" if ch else ""))
        if context.context_text:
            parts.append(f"\n## السياق المسترجع ({context.chunk_count} مقطع — {context.total_tokens} token):\n" + context.context_text)
        else:
            parts.append("\n## السياق: لا يوجد محتوى ذو صلة.")
        if chat_history:
            lines = []
            for m in chat_history[-4:]:
                role = "المستخدم" if m.get("role")=="user" else "المساعد"
                lines.append(f"{role}: {m.get('content','')[:300]}")
            parts.append("\n## سجل المحادثة:\n" + "\n".join(lines))
        parts.append(f"\n## سؤال المستخدم:\n{question}")
        parts.append(_OUTPUT_SCHEMA)
        return "\n".join(parts)
