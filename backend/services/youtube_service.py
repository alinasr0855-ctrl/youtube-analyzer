"""YouTube Data API — parallel search + thread-safe clients."""
import os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
if not YOUTUBE_API_KEY:
    raise EnvironmentError("YOUTUBE_API_KEY is not set.")

def _make_youtube():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

youtube = _make_youtube()

def extract_playlist_id(url: str) -> Optional[str]:
    m = re.search(r"list=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None

def _search(query, type_, max_results):
    yt = _make_youtube()
    try: resp = yt.search().list(part="snippet", q=query, type=type_, maxResults=max_results, order="relevance").execute()
    except HttpError as e: raise RuntimeError(str(e))
    return resp.get("items", [])

def search_all(query: str) -> Dict:
    results = {"videos": [], "playlists": [], "channels": []}
    def _task(kind):
        type_map = {"videos":"video","playlists":"playlist","channels":"channel"}
        max_map  = {"videos":12,"playlists":6,"channels":5}
        items = _search(query, type_map[kind], max_map[kind])
        if kind == "videos":
            return kind, [{"video_id":i["id"]["videoId"],"title":i["snippet"]["title"],
                "description":i["snippet"].get("description",""),"channel_id":i["snippet"]["channelId"],
                "channel_name":i["snippet"]["channelTitle"],
                "thumbnail":i["snippet"]["thumbnails"].get("medium",{}).get("url","")} for i in items]
        elif kind == "playlists":
            return kind, [{"playlist_id":i["id"]["playlistId"],"title":i["snippet"]["title"],
                "description":i["snippet"].get("description",""),"channel_id":i["snippet"]["channelId"],
                "channel_name":i["snippet"]["channelTitle"],
                "thumbnail":i["snippet"]["thumbnails"].get("medium",{}).get("url",""),"video_count":0} for i in items]
        else:
            return kind, [{"channel_id":i["snippet"]["channelId"],"title":i["snippet"]["title"],
                "description":i["snippet"].get("description",""),
                "thumbnail":i["snippet"]["thumbnails"].get("default",{}).get("url","")} for i in items]
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in as_completed({ex.submit(_task,k):k for k in ("videos","playlists","channels")}):
            try: kind, data = f.result(); results[kind] = data
            except: pass
    return results

def get_channel_playlists(channel_id: str) -> List[Dict]:
    playlists, npt = [], None
    while True:
        try: resp = youtube.playlists().list(part="snippet,contentDetails",channelId=channel_id,maxResults=50,pageToken=npt).execute()
        except HttpError as e: raise RuntimeError(str(e))
        for item in resp.get("items",[]):
            playlists.append({"playlist_id":item["id"],"title":item["snippet"]["title"],
                "description":item["snippet"].get("description",""),
                "thumbnail":item["snippet"]["thumbnails"].get("medium",{}).get("url",""),
                "video_count":item["contentDetails"]["itemCount"]})
        npt = resp.get("nextPageToken")
        if not npt: break
    return playlists

def get_playlist_info(playlist_id: str) -> Optional[Dict]:
    try: resp = youtube.playlists().list(part="snippet,contentDetails",id=playlist_id).execute()
    except HttpError as e: raise RuntimeError(str(e))
    items = resp.get("items",[])
    if not items: return None
    item = items[0]
    return {"playlist_id":playlist_id,"title":item["snippet"]["title"],
            "description":item["snippet"].get("description",""),
            "thumbnail":item["snippet"]["thumbnails"].get("medium",{}).get("url",""),
            "video_count":item["contentDetails"]["itemCount"],
            "channel_id":item["snippet"]["channelId"],"channel_name":item["snippet"]["channelTitle"]}

def get_playlist_videos(playlist_id: str) -> List[Dict]:
    videos, npt = [], None
    while True:
        try: resp = youtube.playlistItems().list(part="snippet,contentDetails",playlistId=playlist_id,maxResults=50,pageToken=npt).execute()
        except HttpError as e: raise RuntimeError(str(e))
        for item in resp.get("items",[]):
            s = item["snippet"]; vid = s["resourceId"]["videoId"]
            if s["title"] in ("Deleted video","Private video"): continue
            videos.append({"video_id":vid,"title":s["title"],"position":s["position"],
                "thumbnail":s["thumbnails"].get("medium",{}).get("url",""),"description":s.get("description","")})
        npt = resp.get("nextPageToken")
        if not npt: break
    return videos

def get_transcript(video_id: str, languages=("ar","en"), max_chars=8000) -> str:
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        return " ".join(t["text"] for t in segs)[:max_chars]
    except (NoTranscriptFound, TranscriptsDisabled):
        try: segs = YouTubeTranscriptApi.get_transcript(video_id); return " ".join(t["text"] for t in segs)[:max_chars]
        except: return ""
    except: return ""

def get_transcript_with_timestamps(video_id: str, languages=("ar","en")) -> List[Dict]:
    try: return YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
    except (NoTranscriptFound, TranscriptsDisabled):
        try: return YouTubeTranscriptApi.get_transcript(video_id)
        except: return []
    except: return []
