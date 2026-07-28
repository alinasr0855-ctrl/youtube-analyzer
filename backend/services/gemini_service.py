"""AI service — Gemini cascade + OpenRouter fallback + persistent cache."""
import json, os, re, time, httpx
from typing import Dict, List, Optional
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
_GEMINI_KEY = os.getenv("GEMINI_API_KEY","")
if not _GEMINI_KEY: raise EnvironmentError("GEMINI_API_KEY is not set.")
_OR_KEY = os.getenv("OPENROUTER_API_KEY","")
genai.configure(api_key=_GEMINI_KEY)

_GEMINI_MODELS = ["gemini-2.0-flash-lite","gemini-2.0-flash",
                  "gemini-1.5-flash","gemini-1.5-flash-8b","gemini-1.5-pro"]
_OR_FALLBACK = ["deepseek/deepseek-r1:free","deepseek/deepseek-r1-distill-llama-70b:free",
                "meta-llama/llama-3.3-70b-instruct:free","google/gemma-3-27b-it:free",
                "mistralai/mistral-7b-instruct:free"]
_or_models_cache: Optional[List[str]] = None
_gemini_cache: Dict[str,genai.GenerativeModel] = {}

def _fetch_or_models():
    global _or_models_cache
    if _or_models_cache is not None: return _or_models_cache
    if not _OR_KEY: _or_models_cache=[]; return []
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/models",headers={"Authorization":f"Bearer {_OR_KEY}"},timeout=10)
        resp.raise_for_status()
        ds,others=[],[]
        for m in resp.json().get("data",[]):
            mid=m.get("id",""); p=m.get("pricing",{})
            if mid.endswith(":free") or (str(p.get("prompt","1"))=="0" and str(p.get("completion","1"))=="0"):
                (ds if "deepseek" in mid else others).append(mid)
        _or_models_cache=(ds+others) or _OR_FALLBACK
    except: _or_models_cache=_OR_FALLBACK
    return _or_models_cache

def _get_gemini(name):
    if name not in _gemini_cache: _gemini_cache[name]=genai.GenerativeModel(name)
    return _gemini_cache[name]

def _is_quota(exc): err=str(exc); return any(k in err for k in ("429","quota","rate","exceeded","RESOURCE_EXHAUSTED"))

_CFG={"max_output_tokens":2048,"temperature":0.4}

def _call_model(prompt:str) -> str:
    """Public: call the best available model with full fallback chain."""
    last=None
    for name in _GEMINI_MODELS:
        try: return _get_gemini(name).generate_content(prompt,generation_config=_CFG).text.strip()
        except Exception as e:
            last=e
            if _is_quota(e): time.sleep(2); continue
            else: raise
    if _OR_KEY:
        try:
            from openai import OpenAI
            client=OpenAI(base_url="https://openrouter.ai/api/v1",api_key=_OR_KEY)
        except ImportError: raise RuntimeError("openai package required")
        seen,ordered=set(),[]
        for m in _OR_FALLBACK+_fetch_or_models():
            if m not in seen: seen.add(m); ordered.append(m)
        for name in ordered[:5]:
            try:
                c=client.chat.completions.create(model=name,messages=[{"role":"user","content":prompt}],max_tokens=2048,timeout=30)
                return c.choices[0].message.content.strip()
            except Exception as e:
                last=e
                if _is_quota(e): time.sleep(2); continue
                else: raise
    raise RuntimeError(f"All models exhausted. Last: {last}")

def _safe_json(text:str) -> Optional[dict]:
    text=text.strip()
    try: return json.loads(text)
    except: pass
    m=re.search(r"```(?:json)?\s*([\s\S]+?)```",text)
    if m:
        try: return json.loads(m.group(1).strip())
        except: pass
    return None

def analyze_batch(videos:List[Dict]) -> List[Dict]:
    from backend.services import video_cache
    results=[]
    for video in videos:
        vid=video.get("video_id","")
        cached=video_cache.get(vid) if vid else None
        if cached: results.append({**video,**cached,"analyzed":True}); continue
        title=video.get("title",""); desc=(video.get("description","") or "")[:1500]
        transcript=(video.get("transcript","") or "")[:5000]; pos=video.get("position",0)
        parts=[f"عنوان الفيديو: {title}"]
        if desc: parts.append(f"وصف الفيديو:\n{desc}")
        if transcript: parts.append(f"محتوى الفيديو:\n{transcript}")
        prompt=f"""أنت مساعد تعليمي. بناءً على الفيديو رقم {pos+1}:

{chr(10).join(parts)}

أجب بـ JSON فقط:

{{
  "explanation": "شرح مفصل منظم لا يقل عن 400 كلمة:\\n## الهدف الرئيسي\\n## المفاهيم المغطاة\\n## ما ستتعلمه\\n## الأهمية التطبيقية\\n## الترابط مع المحتوى الأوسع",
  "level": "مبتدئ | متوسط | متقدم",
  "type": "نظري | تطبيقي | مراجعة | مشروع",
  "topics": ["موضوع1","موضوع2","موضوع3"],
  "estimated_minutes": 30,
  "requires_previous": true
}}"""
        try:
            raw=_call_model(prompt); parsed=_safe_json(raw)
            if parsed and "explanation" in parsed:
                analysis={"explanation":parsed.get("explanation",""),"level":parsed.get("level",""),
                          "type":parsed.get("type",""),"topics":parsed.get("topics",[]),
                          "estimated_minutes":parsed.get("estimated_minutes"),"requires_previous":parsed.get("requires_previous",False)}
            else:
                analysis={"explanation":raw,"level":"","type":"","topics":[],"estimated_minutes":None,"requires_previous":False}
            if vid: video_cache.set(vid,analysis)
            results.append({**video,**analysis,"analyzed":True})
        except Exception as e:
            results.append({**video,"explanation":f"تعذر التحليل: {e}","level":"","type":"","topics":[],"estimated_minutes":None,"requires_previous":False,"analyzed":True})
    return results

def generate_playlist_summary(videos:List[Dict],playlist_name:str) -> str:
    analyzed=[v for v in videos if v.get("analyzed")]
    if not analyzed: return "لا توجد فيديوهات محللة."
    lines=[f"فيديو {v.get('position',0)+1}: {v.get('title','')} | {v.get('level','—')} | {'، '.join(v.get('topics') or [])}" for v in analyzed]
    prompt=f"""أنت خبير تعليمي. Playlist: {playlist_name}

{chr(10).join(lines)}

اكتب ملخصاً شاملاً منظماً:
## 1. نظرة عامة
## 2. أهم 5 مفاهيم
## 3. المستوى العام
## 4. نقاط القوة
## 5. الثغرات والنواقص
## 6. التوصية النهائية"""
    try: return _call_model(prompt)
    except Exception as e: return f"تعذر توليد الملخص: {e}"

def generate_learning_path(videos:List[Dict]) -> Dict:
    analyzed=[v for v in videos if v.get("analyzed")]
    if not analyzed: return {"phases":[]}
    lines=[f"ID:{v['video_id']} | {v.get('title','')} | {v.get('level','—')} | {'، '.join(v.get('topics') or [])}" for v in analyzed]
    prompt=f"""أنت خبير تعليمي. قسّم الفيديوهات التالية إلى 2-4 مراحل منطقية:

{chr(10).join(lines)}

أجب بـ JSON فقط:
{{"phases":[{{"title":"...","description":"...","video_ids":["..."]}}]}}"""
    try:
        raw=_call_model(prompt); parsed=_safe_json(raw)
        return parsed if parsed and "phases" in parsed else {"phases":[],"raw":raw}
    except Exception as e: return {"phases":[],"error":str(e)}

def chat_with_playlist(question:str,videos:List[Dict],playlist_name:str,chat_history:List[Dict]) -> Dict:
    """Standard analysis-based chat (no RAG)."""
    analyzed=[v for v in videos if v.get("analyzed")]
    explain_kw=["اشرح","شرح","وضح","فسر","تفصيل","بالتفصيل","explain","detail","how does","what is"]
    is_expl=any(kw in question.lower() for kw in explain_kw)
    ctx=[]
    for v in analyzed:
        ctx.append(f"[فيديو {v.get('position',0)+1} | ID:{v['video_id']}]\nعنوان: {v.get('title','')} | مستوى: {v.get('level','—')} | مواضيع: {'، '.join(v.get('topics') or [])}\n{(v.get('explanation') or '')[:1500]}")
    history_lines=[f"{'المستخدم' if m.get('role')=='user' else 'المساعد'}: {m.get('content','')}" for m in (chat_history or [])[-6:]]
    answer_fmt="إجابة تفصيلية منظمة بعناوين وأمثلة" if is_expl else "إجابة واضحة ومفيدة"
    prompt=f"""أنت مساعد ذكي. اسم المحتوى: "{playlist_name}"

{chr(10).join(ctx)}

{("سجل المحادثة:\n"+chr(10).join(history_lines)) if history_lines else ""}

سؤال المستخدم: {question}

أجب بـ JSON فقط:
{{"answer":"{answer_fmt}","referenced_videos":[{{"video_id":"...","title":"...","position":0}}]}}"""
    try:
        raw=_call_model(prompt); parsed=_safe_json(raw)
        if parsed and "answer" in parsed: return {"answer":parsed.get("answer",""),"referenced_videos":parsed.get("referenced_videos",[])}
        return {"answer":raw,"referenced_videos":[]}
    except Exception as e: return {"answer":f"تعذر الإجابة: {e}","referenced_videos":[]}

def compare_playlists(playlist_a:Dict,playlist_b:Dict) -> Dict:
    def _sum(pl):
        vids=[v for v in pl.get("videos",[]) if v.get("analyzed")]
        topics=[]; levels=[]
        for v in vids: topics.extend(v.get("topics") or []); (levels.append(v["level"]) if v.get("level") else None)
        return (f"اسم: {pl.get('name','—')}\nعدد الفيديوهات: {len(vids)}\nالمستويات: {'، '.join(set(levels)) if levels else '—'}\n"
                f"الوقت: {sum(v.get('estimated_minutes') or 0 for v in vids)} دقيقة\nالمواضيع: {', '.join(list(dict.fromkeys(topics))[:15])}")
    prompt=f"""قارن بين الـ Playlist التاليتين وأجب بـ JSON فقط:

--- A ---\n{_sum(playlist_a)}
--- B ---\n{_sum(playlist_b)}

{{"criteria":[{{"name":"المستوى","playlist_a":"...","playlist_b":"..."}},{{"name":"نوع المحتوى","playlist_a":"...","playlist_b":"..."}},{{"name":"الوقت الإجمالي","playlist_a":"...","playlist_b":"..."}},{{"name":"التغطية","playlist_a":"...","playlist_b":"..."}},{{"name":"المناسب لـ","playlist_a":"...","playlist_b":"..."}}],"recommendation":"...","winner":"A أو B أو كلاهما"}}"""
    try:
        raw=_call_model(prompt); parsed=_safe_json(raw)
        if parsed and "criteria" in parsed:
            return {**parsed,"playlist_a_name":playlist_a.get("name","A"),"playlist_b_name":playlist_b.get("name","B")}
        return {"criteria":[],"recommendation":raw,"winner":"—","playlist_a_name":playlist_a.get("name","A"),"playlist_b_name":playlist_b.get("name","B")}
    except Exception as e: return {"criteria":[],"recommendation":f"تعذر المقارنة: {e}","winner":"—"}
