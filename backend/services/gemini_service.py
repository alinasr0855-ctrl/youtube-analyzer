import json
import os
import re
import time
import httpx
from typing import Dict, List, Optional

import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_GEMINI_KEY: str = os.getenv("GEMINI_API_KEY", "")
if not _GEMINI_KEY:
    raise EnvironmentError("GEMINI_API_KEY is not set.")

_OPENROUTER_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

genai.configure(api_key=_GEMINI_KEY)

# ── Gemini Models ──────────────────────────────────────────────────────────────
_GEMINI_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

# ── OpenRouter Free Models ─────────────────────────────────────────────────────
# Primary model tried first before the dynamic list
_OPENROUTER_PRIMARY = "meta-llama/llama-3.2-3b-instruct:free"

# Fallback hardcoded list (used if live fetch fails or returns empty)
_OPENROUTER_FALLBACK = [
    "mistralai/mistral-small-2603",
    "deepseek/deepseek-chat",
    "google/gemma-3-4b-it:free",
]

_openrouter_models_cache: Optional[List[str]] = None


def _fetch_free_openrouter_models() -> List[str]:
    """Fetches all currently available :free models from OpenRouter at runtime."""
    global _openrouter_models_cache
    if _openrouter_models_cache is not None:
        return _openrouter_models_cache

    if not _OPENROUTER_KEY:
        _openrouter_models_cache = []
        return []

    try:
        resp = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {_OPENROUTER_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        free_models = []
        deepseek_first = []
        others = []
        for m in data:
            mid = m.get("id", "")
            # A model is free if its id ends with :free OR both prompt/completion pricing = "0"
            pricing = m.get("pricing", {})
            is_free = mid.endswith(":free") or (
                str(pricing.get("prompt", "1")) == "0"
                and str(pricing.get("completion", "1")) == "0"
            )
            if is_free:
                if "deepseek" in mid:
                    deepseek_first.append(mid)
                else:
                    others.append(mid)

        free_models = deepseek_first + others
        _openrouter_models_cache = free_models if free_models else _OPENROUTER_FALLBACK
    except Exception:
        _openrouter_models_cache = _OPENROUTER_FALLBACK

    return _openrouter_models_cache


# Cache Gemini model instances
_gemini_cache: Dict[str, genai.GenerativeModel] = {}

def _get_gemini(name: str) -> genai.GenerativeModel:
    if name not in _gemini_cache:
        _gemini_cache[name] = genai.GenerativeModel(name)
    return _gemini_cache[name]

def _get_openrouter_client() -> Optional[OpenAI]:
    if not _OPENROUTER_KEY:
        return None
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=_OPENROUTER_KEY,
    )


# ── JSON Parsing Helper ────────────────────────────────────────────────────────

def _safe_json(text: str) -> Optional[dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None


def _is_quota_error(exc: Exception) -> bool:
    err = str(exc)
    return "429" in err or "quota" in err.lower() or "rate" in err.lower() or "exceeded" in err.lower()


_GEMINI_CONFIG = {
    "max_output_tokens": 2048,
    "temperature": 0.4,
}

def _call_model(prompt: str) -> str:
    """
    Tries all providers in order with fast fallback:
      1. Gemini free-tier models (gemini-2.0-flash-lite first — fastest)
      2. Top OpenRouter free models (limited to 5 to avoid long chains)
    Quota errors trigger immediate move to next model (2s sleep only).
    """
    last_exc: Optional[Exception] = None

    # ── 1. Try Gemini models ──────────────────────────────────────────────────
    for model_name in _GEMINI_MODELS:
        model = _get_gemini(model_name)
        try:
            response = model.generate_content(
                prompt,
                generation_config=_GEMINI_CONFIG,
            )
            return response.text.strip()
        except Exception as exc:
            last_exc = exc
            if _is_quota_error(exc):
                time.sleep(2)   # short pause then try next model immediately
                continue
            else:
                raise           # non-quota error → surface immediately

    # ── 2. Try free models via OpenRouter ────────────────────────────────────
    client = _get_openrouter_client()
    if client:
        dynamic = _fetch_free_openrouter_models()
        seen: set = set()
        ordered: List[str] = []
        for m in [_OPENROUTER_PRIMARY] + dynamic + _OPENROUTER_FALLBACK:
            if m not in seen:
                seen.add(m)
                ordered.append(m)
        # Limit to top 5 to avoid long fallback chains
        for model_name in ordered[:5]:
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                    timeout=30,
                )
                return completion.choices[0].message.content.strip()
            except Exception as exc:
                last_exc = exc
                if _is_quota_error(exc):
                    time.sleep(2)
                    continue
                else:
                    raise

    raise RuntimeError(f"تجاوزت جميع النماذج المتاحة حد الاستخدام. آخر خطأ: {last_exc}")


# ── Video Analysis ─────────────────────────────────────────────────────────────

def analyze_batch(videos: List[Dict]) -> List[Dict]:
    """
    Analyzes a list of video dicts (which may include a ``transcript`` key)
    and annotates each with: explanation, level, type, topics,
    estimated_minutes, requires_previous.
    """
    results: List[Dict] = []

    for video in videos:
        title: str = video.get("title", "")
        description: str = (video.get("description", "") or "")[:1500]
        transcript: str = (video.get("transcript", "") or "")[:5000]
        position: int = video.get("position", 0)

        context_parts = [f"عنوان الفيديو: {title}"]
        if description:
            context_parts.append(f"وصف الفيديو:\n{description}")
        if transcript:
            context_parts.append(f"محتوى الفيديو (Transcript):\n{transcript}")
        context = "\n\n".join(context_parts)

        prompt = f"""أنت مساعد تعليمي متخصص في تحليل محتوى الفيديوهات التقنية والتعليمية.

بناءً على المعلومات التالية للفيديو رقم {position + 1}:

{context}

أجب بـ JSON فقط (بدون أي نص خارجه) بالشكل التالي:

{{
  "explanation": "شرح مفصل لا يقل عن 400 كلمة يغطي: الهدف الرئيسي، المفاهيم المغطاة، ما ستتعلمه، الأهمية التطبيقية، والترابط مع المحتوى الأوسع.",
  "level": "مبتدئ | متوسط | متقدم",
  "type": "نظري | تطبيقي | مراجعة | مشروع",
  "topics": ["موضوع1", "موضوع2", "موضوع3"],
  "estimated_minutes": 30,
  "requires_previous": true
}}"""

        try:
            raw = _call_model(prompt)
            parsed = _safe_json(raw)
            if parsed and "explanation" in parsed:
                results.append(
                    {
                        **video,
                        "explanation": parsed.get("explanation", ""),
                        "level": parsed.get("level", ""),
                        "type": parsed.get("type", ""),
                        "topics": parsed.get("topics", []),
                        "estimated_minutes": parsed.get("estimated_minutes"),
                        "requires_previous": parsed.get("requires_previous", False),
                        "analyzed": True,
                    }
                )
            else:
                # Model returned non-JSON; store raw text as explanation
                results.append(
                    {
                        **video,
                        "explanation": raw,
                        "level": "",
                        "type": "",
                        "topics": [],
                        "estimated_minutes": None,
                        "requires_previous": False,
                        "analyzed": True,
                    }
                )
        except Exception as exc:
            results.append(
                {
                    **video,
                    "explanation": f"تعذر تحليل هذا الفيديو: {exc}",
                    "level": "",
                    "type": "",
                    "topics": [],
                    "estimated_minutes": None,
                    "requires_previous": False,
                    "analyzed": True,
                }
            )

    return results


# ── Playlist Summary ───────────────────────────────────────────────────────────

def generate_playlist_summary(videos: List[Dict], playlist_name: str) -> str:
    """Generates an executive summary for all analyzed videos in a playlist."""
    analyzed = [v for v in videos if v.get("analyzed")]
    if not analyzed:
        return "لا توجد فيديوهات محللة بعد."

    lines = []
    for v in analyzed:
        topics_str = "، ".join(v.get("topics") or []) or "—"
        lines.append(
            f"فيديو {v.get('position', 0) + 1}: {v.get('title', '')} | "
            f"المستوى: {v.get('level', '—')} | المواضيع: {topics_str}"
        )

    prompt = f"""أنت خبير تعليمي. تم تحليل الـ Playlist التالية:

اسم الـ Playlist: {playlist_name}

قائمة الفيديوهات المحللة:
{chr(10).join(lines)}

اكتب ملخصاً تنفيذياً شاملاً يتضمن:

1. **نظرة عامة**: ما الذي تغطيه هذه الـ Playlist بشكل عام؟
2. **أهم 5 مفاهيم**: أبرز المواضيع التي يكتسبها المشاهد.
3. **المستوى العام**: هل هي مناسبة للمبتدئين أم المتقدمين؟
4. **نقاط القوة**: ما الذي يميز هذا المنهج؟
5. **الثغرات أو النواقص**: هل هناك مواضيع مهمة غير مغطاة؟
6. **التوصية النهائية**: لمن تناسب هذه الـ Playlist؟

اكتب بأسلوب احترافي وواضح بالعربية."""

    try:
        return _call_model(prompt)
    except Exception as exc:
        return f"تعذر توليد الملخص: {exc}"


# ── Learning Path ──────────────────────────────────────────────────────────────

def generate_learning_path(videos: List[Dict]) -> Dict:
    """
    Groups analyzed videos into 2–4 logical learning phases.
    Returns ``{"phases": [{"title", "description", "video_ids"}]}``.
    """
    analyzed = [v for v in videos if v.get("analyzed")]
    if not analyzed:
        return {"phases": []}

    lines = []
    for v in analyzed:
        topics_str = "، ".join(v.get("topics") or []) or "—"
        lines.append(
            f"ID:{v['video_id']} | رقم:{v.get('position', 0) + 1} | "
            f"العنوان:{v.get('title', '')} | المستوى:{v.get('level', '—')} | "
            f"المواضيع:{topics_str} | يعتمد على سابق:{v.get('requires_previous', False)}"
        )

    prompt = f"""أنت خبير تعليمي. لديك قائمة الفيديوهات التالية:

{chr(10).join(lines)}

صمم مسار تعلم ذكياً يقسم هذه الفيديوهات إلى مراحل منطقية (من 2 إلى 4 مراحل).
أجب بـ JSON فقط بالشكل التالي:

{{
  "phases": [
    {{
      "title": "عنوان المرحلة",
      "description": "وصف مختصر للمرحلة وما ستتعلمه",
      "video_ids": ["video_id_1", "video_id_2"]
    }}
  ]
}}

ضع الفيديوهات في ترتيب منطقي للتعلم بغض النظر عن ترقيمها الأصلي."""

    try:
        raw = _call_model(prompt)
        parsed = _safe_json(raw)
        if parsed and "phases" in parsed:
            return parsed
        return {"phases": [], "raw": raw}
    except Exception as exc:
        return {"phases": [], "error": str(exc)}


# ── Chat with Playlist ─────────────────────────────────────────────────────────

def chat_with_playlist(
    question: str,
    videos: List[Dict],
    playlist_name: str,
    chat_history: List[Dict],
) -> Dict:
    """
    Answers a user question using the playlist analysis as context.

    Returns ``{"answer": str, "referenced_videos": [{"video_id", "title", "position"}]}``.
    """
    analyzed = [v for v in videos if v.get("analyzed")]

    video_context = []
    for v in analyzed:
        topics_str = "، ".join(v.get("topics") or []) or "—"
        snippet = (v.get("explanation") or "")[:300]
        video_context.append(
            f"[فيديو {v.get('position', 0) + 1} | ID:{v['video_id']}] "
            f"عنوان: {v.get('title', '')} | مستوى: {v.get('level', '—')} | "
            f"مواضيع: {topics_str} | ملخص: {snippet}"
        )

    # Keep only the last 6 turns to stay within token limits
    history_lines = []
    for msg in (chat_history or [])[-6:]:
        role = "المستخدم" if msg.get("role") == "user" else "المساعد"
        history_lines.append(f"{role}: {msg.get('content', '')}")
    history_str = "\n".join(history_lines)

    prompt = f"""أنت مساعد ذكي متخصص في Playlist YouTube باسم "{playlist_name}".
لديك المعلومات التالية عن فيديوهات هذه الـ Playlist:

{chr(10).join(video_context)}

{"سجل المحادثة السابقة:" + chr(10) + history_str if history_str else ""}

سؤال المستخدم: {question}

أجب بـ JSON فقط بالشكل التالي:
{{
  "answer": "إجابة واضحة ومفيدة بالعربية مبنية على محتوى الـ Playlist",
  "referenced_videos": [
    {{"video_id": "...", "title": "...", "position": 0}}
  ]
}}

إذا كان السؤال غير متعلق بالـ Playlist، وضح ذلك بلطف."""

    try:
        raw = _call_model(prompt)
        parsed = _safe_json(raw)
        if parsed and "answer" in parsed:
            return {
                "answer": parsed.get("answer", ""),
                "referenced_videos": parsed.get("referenced_videos", []),
            }
        return {"answer": raw, "referenced_videos": []}
    except Exception as exc:
        return {"answer": f"تعذر الإجابة: {exc}", "referenced_videos": []}


# ── Playlist Comparison ────────────────────────────────────────────────────────

def compare_playlists(playlist_a: Dict, playlist_b: Dict) -> Dict:
    """
    Compares two analyzed playlists and returns a structured comparison.

    Each argument: ``{"name": str, "videos": List[Dict]}``.
    """

    def _summarize(playlist: Dict) -> str:
        name = playlist.get("name", "—")
        vids = [v for v in playlist.get("videos", []) if v.get("analyzed")]
        all_topics: List[str] = []
        levels: List[str] = []
        for v in vids:
            all_topics.extend(v.get("topics") or [])
            if v.get("level"):
                levels.append(v["level"])
        unique_topics = list(dict.fromkeys(all_topics))[:15]
        level_str = "، ".join(set(levels)) if levels else "—"
        return (
            f"اسم الـ Playlist: {name}\n"
            f"عدد الفيديوهات المحللة: {len(vids)}\n"
            f"المستويات: {level_str}\n"
            f"أبرز المواضيع: {', '.join(unique_topics)}"
        )

    prompt = f"""أنت خبير تعليمي. قارن بين الـ Playlist التاليتين:

--- Playlist A ---
{_summarize(playlist_a)}

--- Playlist B ---
{_summarize(playlist_b)}

أجب بـ JSON فقط بالشكل التالي:
{{
  "criteria": [
    {{"name": "المستوى", "playlist_a": "وصف A", "playlist_b": "وصف B"}},
    {{"name": "التغطية", "playlist_a": "وصف A", "playlist_b": "وصف B"}},
    {{"name": "عدد الفيديوهات", "playlist_a": "وصف A", "playlist_b": "وصف B"}},
    {{"name": "المواضيع الحصرية", "playlist_a": "وصف A", "playlist_b": "وصف B"}},
    {{"name": "المناسب لـ", "playlist_a": "وصف A", "playlist_b": "وصف B"}}
  ],
  "recommendation": "توصية واضحة: أيهما أفضل ولماذا؟ وهل يمكن الجمع بينهما؟",
  "winner": "A أو B أو كلاهما"
}}"""

    try:
        raw = _call_model(prompt)
        parsed = _safe_json(raw)
        if parsed and "criteria" in parsed:
            return {
                **parsed,
                "playlist_a_name": playlist_a.get("name", "Playlist A"),
                "playlist_b_name": playlist_b.get("name", "Playlist B"),
            }
        return {
            "criteria": [],
            "recommendation": raw,
            "winner": "—",
            "playlist_a_name": playlist_a.get("name", "Playlist A"),
            "playlist_b_name": playlist_b.get("name", "Playlist B"),
        }
    except Exception as exc:
        return {
            "criteria": [],
            "recommendation": f"تعذر المقارنة: {exc}",
            "winner": "—",
        }
