import logging
from fastapi import FastAPI, Request, Response
import json
from datetime import datetime

# --- FastAPI App Definition (NO LIFESPAN FOR THIS TEST) ---
logging.basicConfig(level=logging.INFO)
app = FastAPI()

@app.get("/health")
async def health_check():
    """A simple endpoint to prove the server is running."""
    return {"status": "ok"}

# We will also include the real endpoint to ensure it can be imported,
# even though we won't call it.
from intents.summary import Summary
INTENTS = {'summary': Summary}

@app.get("/{intent}")
async def handle_intent(intent: str, request: Request):
    return Response(
        content=json.dumps({"message": f"Server is running, but intent '{intent}' was not executed."}),
        media_type="application/json",
        status_code=200
    )
