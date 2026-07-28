# PlaylistAI — YouTube Playlist Analyzer

PlaylistAI is an intelligent YouTube playlist analysis platform powered by a unified AI Assistant that automatically selects the most appropriate reasoning strategy for every user query.

The assistant dynamically routes requests between Gemini, Retrieval-Augmented Generation (RAG), and Hybrid reasoning without requiring any manual mode selection.

---

# Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env

# Configure your API keys
python run.py
```

Application URL:

```
http://localhost:8000
```

---

# Environment Variables

| Variable             | Required  | Description              |
| -------------------- | --------- | ------------------------ |
| `GEMINI_API_KEY`     | Yes       | Google Gemini API        |
| `YOUTUBE_API_KEY`    | Yes       | YouTube Data API         |
| `VOYAGE_API_KEY`     | Yes (RAG) | Voyage AI Embeddings     |
| `PINECONE_API_KEY`   | Yes (RAG) | Pinecone Vector Database |
| `PINECONE_INDEX`     | No        | Defaults to `playlistai` |
| `OPENROUTER_API_KEY` | No        | Optional LLM Provider    |

---

# Project Structure

```text
PlaylistAI/
├── main.py                          # Replit entry point
├── run.py                           # Local development launcher
├── requirements.txt
├── .env.example
│
├── backend/
│   ├── main.py                      # FastAPI application (17 REST endpoints)
│   ├── models/
│   │   └── schemas.py
│   │
│   └── services/
│       ├── youtube_service.py       # YouTube API integration
│       ├── gemini_service.py        # Gemini with multi-model fallback
│       ├── video_cache.py           # Persistent disk cache
│       ├── cache_service.py         # Session cache
│       ├── memory_service.py        # Session metadata
│       │
│       ├── rag/
│       │   ├── ingestion.py         # Transcript extraction and preprocessing
│       │   ├── chunker.py           # Hybrid Recursive + Sliding Window chunking
│       │   ├── embedder.py          # Voyage AI embeddings
│       │   ├── vector_store.py      # Pinecone vector database
│       │   ├── retriever.py         # Top-K retrieval, MMR, and deduplication
│       │   ├── context_builder.py   # Context construction
│       │   ├── prompt_engineer.py   # Prompt generation
│       │   └── rag_service.py       # RAG orchestration
│       │
│       └── assistant/
│           ├── classifier.py        # Local question classifier
│           ├── router.py            # Intelligent routing engine
│           └── assistant_service.py # Unified AI Assistant
│
└── frontend/
    └── index.html                   # Web interface
```

---

# AI Assistant Workflow

```text
                    User Question
                          │
                          ▼
               Question Classifier
          (Local classification, no API calls)
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
     General        Video-Specific       Hybrid
        │                 │                 │
        └─────────────────┴─────────────────┘
                          │
                          ▼
                  Assistant Router
           + RAG Index Availability Check
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
     Gemini             RAG              Hybrid
  General AI       Transcript-Based   Combined Reasoning
                    Retrieval
                          │
                          ▼
            Automatic Gemini Fallback
          (If no relevant documents exist)
                          │
                          ▼
                 Unified AI Response

{
    answer,
    mode,
    sources,
    confidence
}
```

---

# Routing Strategy

| Question Type                 | RAG Available | Selected Mode   |
| ----------------------------- | ------------- | --------------- |
| Any                           | No            | Gemini          |
| General                       | Yes           | Gemini          |
| Video-Specific                | Yes           | RAG             |
| Hybrid or Ambiguous           | Yes           | Hybrid          |
| Retrieval Returned No Results | —             | Gemini Fallback |

---

# REST API

### System

```text
GET    /api/health
GET    /api/cache/info
DELETE /api/cache/clear
```

### Search

```text
POST   /api/search
GET    /api/channels/{id}/playlists
```

### Sessions

```text
POST   /api/sessions/start
GET    /api/sessions
GET    /api/sessions/{id}/results
DELETE /api/sessions/{id}
```

### Playlist Analysis

```text
POST   /api/sessions/{id}/analyze-next
POST   /api/sessions/{id}/analyze-video
POST   /api/sessions/{id}/summary
POST   /api/sessions/{id}/learning-path
POST   /api/compare
```

### AI Assistant

```text
POST   /api/sessions/{id}/assistant
```

### RAG

```text
POST   /api/sessions/{id}/rag/index
POST   /api/sessions/{id}/rag/index-video
GET    /api/sessions/{id}/rag/stats
```

---

# Deployment

For local development:

```bash
python run.py
```

For Replit deployment:

1. Upload the project.
2. Configure the required secrets:

   * `GEMINI_API_KEY`
   * `YOUTUBE_API_KEY`
   * `VOYAGE_API_KEY`
   * `PINECONE_API_KEY`
3. Run:

```bash
python main.py
```

---

# Dependencies

```text
fastapi
uvicorn
python-dotenv
pydantic

google-generativeai
google-api-python-client
youtube-transcript-api

voyageai
pinecone

httpx
openai
tiktoken
```

---

# Features

* Unified AI Assistant with automatic routing.
* End-to-end Retrieval-Augmented Generation pipeline.
* Automatic selection between Gemini, RAG, and Hybrid reasoning.
* Local question classification without additional API calls.
* Intelligent fallback when no relevant transcript content is available.
* Transcript indexing using Pinecone vector search.
* Hybrid chunking strategy for improved retrieval quality.
* Multi-model Gemini fallback chain.
* Persistent caching and session management.
* FastAPI backend exposing 17 REST endpoints.
* Interactive web interface for playlist analysis and AI conversations.

