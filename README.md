# PlaylistAI — YouTube Playlist Analyzer

An AI-powered web application that analyzes YouTube playlists using Google Gemini.
Instead of watching an entire playlist blindly, the app reads every video and gives you
a complete intelligent report in minutes.

All data lives in memory only — nothing is written to disk.

---

## What It Does

The application takes any YouTube channel or playlist link, fetches all videos and their
transcripts automatically, then sends each one to Gemini AI for deep analysis. You get
a full dashboard showing difficulty levels, topics, estimated watch times, an executive
summary, a smart learning path, and a chat interface you can ask anything about the content.

---

## Features

| Feature | Description |
|---|---|
| Playlist Discovery | Search by channel name or paste a playlist URL directly |
| AI Video Analysis | Each video is analyzed for level, type, topics, and estimated watch time |
| Executive Summary | AI-generated overview of the entire playlist |
| Smart Learning Path | AI-curated watching order grouped into logical phases |
| Chat with Playlist | Ask questions in natural language about the playlist content |
| Compare Playlists | Side-by-side AI comparison between two analyzed playlists |
| Dark / Light Mode | Full theme toggle built into the interface |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI 0.111, Uvicorn |
| AI | Google Gemini 1.5 Flash |
| Data | YouTube Data API v3, youtube-transcript-api |
| Frontend | Single-file HTML with embedded CSS and JavaScript |
| Storage | In-memory only — no database, no files written to disk |

---

## Project Structure

```
youtube-playlist-analyzer/
├── backend/
│   ├── main.py                  FastAPI app and all API endpoints
│   ├── models/
│   │   └── schemas.py           Pydantic v2 request and response models
│   └── services/
│       ├── youtube_service.py   YouTube Data API v3 integration
│       ├── gemini_service.py    Google Gemini AI integration
│       ├── cache_service.py     In-memory video results store
│       └── memory_service.py   In-memory session store
├── frontend/
│   └── index.html               Complete single-file UI
├── main.py                      Replit entry point
├── run.py                       Local development runner
├── .replit                      Replit configuration
├── replit.nix                   Replit Python environment
├── requirements.txt
└── .env.example
```

---

## Prerequisites

- Python 3.11 or higher
- A YouTube Data API v3 key from https://console.cloud.google.com/apis/credentials
- A Google Gemini API key from https://aistudio.google.com/app/apikey

---

## Quick Start

1. Clone the repository

```bash
git clone https://github.com/Ali-Zaki/Youtube-Playlists-Analyzer.git
cd Youtube-Playlists-Analyzer
```

2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Set your API keys

```bash
cp .env.example .env
```

Open .env and fill in:

```
YOUTUBE_API_KEY=your_youtube_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

5. Run the server

```bash
python run.py
```

6. Open your browser at http://localhost:8000

---

## Running on Replit

1. Import the repository or upload the files to a new Replit project.
2. Open the Secrets tab and add two secrets:
   - YOUTUBE_API_KEY with your YouTube API key
   - GEMINI_API_KEY with your Gemini API key
3. Click Run. Replit installs dependencies and starts the server automatically.

The app will be available at the Replit-provided URL on port 80.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/health | Health check |
| GET | /api/sessions | List all active sessions |
| GET | /api/sessions/{id}/results | Get session data and all videos |
| DELETE | /api/sessions/{id} | Delete a session from memory |
| POST | /api/search | Search for a channel or playlist URL |
| GET | /api/channels/{id}/playlists | Get playlists for a channel |
| POST | /api/sessions/start | Create a new analysis session |
| POST | /api/sessions/{id}/analyze-next | Analyze the next batch of 3 videos |
| POST | /api/sessions/{id}/analyze-video | Analyze a single video on demand |
| POST | /api/sessions/{id}/summary | Generate an executive summary |
| POST | /api/sessions/{id}/learning-path | Generate a smart learning path |
| POST | /api/sessions/{id}/chat | Chat with the playlist content |
| POST | /api/compare | Compare two analyzed playlists |

---

## Environment Variables

| Variable | Description | Where to Get |
|---|---|---|
| YOUTUBE_API_KEY | YouTube Data API v3 key | Google Cloud Console |
| GEMINI_API_KEY | Google Gemini API key | Google AI Studio |

Never commit your .env file. It is listed in .gitignore.

---

## Important Notes

In-memory storage: All session and video data lives in RAM for the duration of the server
process. When the server stops or restarts, all data is cleared. This is by design for
temporary, session-based usage.

Batch analysis: Videos are analyzed in batches of 3 to respect Gemini API rate limits.
A playlist with 30 videos requires 10 batch operations.

Transcripts: The app attempts to fetch transcripts in Arabic first, then English, then any
available language. Videos without transcripts are analyzed using title and description only.

---

## Troubleshooting

EnvironmentError: YOUTUBE_API_KEY is not set
The .env file is missing or the keys are not filled in. Copy .env.example to .env and add
your keys.

ModuleNotFoundError: No module named 'backend'
Always run from the project root using python run.py or uvicorn backend.main:app --reload,
not from inside the backend/ folder.

HTTP 403 from YouTube API
Verify that YouTube Data API v3 is enabled in your Google Cloud Console project and that
the API key has no domain restrictions blocking server-side requests.

Gemini returns empty or malformed JSON
This usually means the video has no transcript and very little description. The app falls
back to raw text in this case and still marks the video as analyzed.

---

## Author

Ali Zaki — Software Engineer

---

MIT License
