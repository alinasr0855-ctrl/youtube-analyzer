"""Entry point — Replit runs this."""
import uvicorn, os
if __name__ == "__main__":
    uvicorn.run("backend.main:app",
                host="0.0.0.0",
                port=int(os.environ.get("PORT", 5000)),
                reload=False)
