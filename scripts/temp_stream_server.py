"""Temporary minimal server for manually testing stream_chat via curl.

Exposes a single endpoint: POST /stream/{session_id}
Automatically creates a session on first request if one doesn't exist.

Usage:
    source .venv/bin/activate
    python scripts/temp_stream_server.py

Then in another terminal:
    # Get a session id from the output, then:
    curl -N -X POST http://localhost:8001/stream/<session_id> \
         -H "Content-Type: application/json" \
         -d '{"message": "What is the current status of the project?"}'

    # To test disconnect: pipe through head to cut off after a few lines:
    curl -N -s -X POST http://localhost:8001/stream/<session_id> \
         -H "Content-Type: application/json" \
         -d '{"message": "Tell me about the team"}' | head -5

DO NOT use this server in production. For manual testing only.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai_agent.ai_agent import new_chat, stream_chat, get_streaming_metrics

app = FastAPI()


class MessageBody(BaseModel):
    message: str


@app.post("/stream/{session_id}")
async def stream_endpoint(session_id: str, body: MessageBody):
    return StreamingResponse(
        stream_chat(session_id, body.message),
        media_type="text/event-stream",
    )


@app.get("/metrics")
def metrics():
    return get_streaming_metrics()


if __name__ == "__main__":
    session_id = new_chat()
    print(f"\n=== Temp stream server ===")
    print(f"Session ID: {session_id}")
    print(f"Full stream:")
    print(f"  curl -N -X POST http://localhost:8001/stream/{session_id} \\")
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"message": "What is the current status of the project?"}}\'\n')
    print(f"Disconnect test (pipe through head):")
    print(f"  curl -N -s -X POST http://localhost:8001/stream/{session_id} \\")
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"message": "Tell me about the team"}}\' | head -5\n')
    print(f"Metrics: curl http://localhost:8001/metrics\n")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
