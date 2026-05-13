import os
import re
from typing import Dict, List, Optional

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

load_dotenv()

YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

if not YOUTUBE_API_KEY:
    raise EnvironmentError(
        "YOUTUBE_API_KEY is not set. Add it to your .env file."
    )

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


# ── URL Helpers ────────────────────────────────────────────────────────────────

def extract_playlist_id(url: str) -> Optional[str]:
    """Extracts a playlist ID from any YouTube URL that contains `list=`."""
    match = re.search(r"list=([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else None


def extract_channel_handle(url: str) -> Optional[str]:
    """Extracts the @handle from a YouTube channel URL."""
    match = re.search(r"@([A-Za-z0-9_.-]+)", url)
    return match.group(1) if match else None


# ── Channels ───────────────────────────────────────────────────────────────────

def search_channels(query: str) -> List[Dict]:
    """
    Searches YouTube for channels matching *query*.
    Returns an empty list when *query* is a playlist URL (handled separately).
    """
    if "list=" in query:
        return []

    handle = extract_channel_handle(query)
    search_query = handle if handle else query

    try:
        response = youtube.search().list(
            part="snippet",
            q=search_query,
            type="channel",
            maxResults=20,
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"YouTube API error while searching channels: {exc}") from exc

    return [
        {
            "channel_id": item["snippet"]["channelId"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "thumbnail": (
                item["snippet"]["thumbnails"].get("default", {}).get("url", "")
            ),
        }
        for item in response.get("items", [])
    ]


# ── Playlists ──────────────────────────────────────────────────────────────────

def get_channel_playlists(channel_id: str) -> List[Dict]:
    """Returns all playlists for a channel, handling API pagination."""
    playlists: List[Dict] = []
    next_page_token: Optional[str] = None

    while True:
        try:
            response = youtube.playlists().list(
                part="snippet,contentDetails",
                channelId=channel_id,
                maxResults=50,
                pageToken=next_page_token,
            ).execute()
        except HttpError as exc:
            raise RuntimeError(f"YouTube API error fetching playlists: {exc}") from exc

        for item in response.get("items", []):
            playlists.append(
                {
                    "playlist_id": item["id"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"].get("description", ""),
                    "thumbnail": (
                        item["snippet"]["thumbnails"].get("medium", {}).get("url", "")
                    ),
                    "video_count": item["contentDetails"]["itemCount"],
                }
            )

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return playlists


def get_playlist_info(playlist_id: str) -> Optional[Dict]:
    """Returns metadata for a single playlist, or None if not found."""
    try:
        response = youtube.playlists().list(
            part="snippet,contentDetails",
            id=playlist_id,
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"YouTube API error fetching playlist info: {exc}") from exc

    items = response.get("items", [])
    if not items:
        return None

    item = items[0]
    return {
        "playlist_id": playlist_id,
        "title": item["snippet"]["title"],
        "description": item["snippet"].get("description", ""),
        "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
        "video_count": item["contentDetails"]["itemCount"],
        "channel_id": item["snippet"]["channelId"],
        "channel_name": item["snippet"]["channelTitle"],
    }


# ── Videos ─────────────────────────────────────────────────────────────────────

def get_playlist_videos(playlist_id: str) -> List[Dict]:
    """Fetches every video in a playlist with title, position, and thumbnail."""
    videos: List[Dict] = []
    next_page_token: Optional[str] = None

    while True:
        try:
            response = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            ).execute()
        except HttpError as exc:
            raise RuntimeError(f"YouTube API error fetching playlist videos: {exc}") from exc

        for item in response.get("items", []):
            snippet = item["snippet"]
            # Skip deleted/private videos
            video_id = snippet["resourceId"]["videoId"]
            if snippet["title"] in ("Deleted video", "Private video"):
                continue
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet["title"],
                    "position": snippet["position"],
                    "thumbnail": (
                        snippet["thumbnails"].get("medium", {}).get("url", "")
                    ),
                    "description": snippet.get("description", ""),
                }
            )

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return videos


def get_video_details(video_ids: List[str]) -> Dict[str, Dict]:
    """Batch-fetches full metadata for a list of video IDs."""
    if not video_ids:
        return {}
    try:
        response = youtube.videos().list(
            part="snippet,contentDetails",
            id=",".join(video_ids),
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"YouTube API error fetching video details: {exc}") from exc

    return {
        item["id"]: {
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "duration": item["contentDetails"].get("duration", ""),
            "thumbnail": (
                item["snippet"]["thumbnails"].get("medium", {}).get("url", "")
            ),
        }
        for item in response.get("items", [])
    }


# ── Transcripts ────────────────────────────────────────────────────────────────

def get_transcript(
    video_id: str,
    languages: List[str] = ("ar", "en"),
    max_chars: int = 8000,
) -> str:
    """
    Tries to fetch a transcript for *video_id* in the preferred *languages*.
    Falls back to any available language, then returns an empty string on failure.
    """
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        return " ".join(t["text"] for t in segments)[:max_chars]
    except (NoTranscriptFound, TranscriptsDisabled):
        try:
            segments = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(t["text"] for t in segments)[:max_chars]
        except Exception:
            return ""
    except Exception:
        return ""
