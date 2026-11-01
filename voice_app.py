
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from google.adk.runners import InMemoryRunner
from google.genai import types

from agent import root_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError("GOOGLE_API_KEY is missing from .env")

APP_NAME = "wesonga_voice"
USER_ID = "wesonga_user"

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="Wesonga AI Assistant")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

runner = InMemoryRunner(
    agent=root_agent,
    app_name=APP_NAME,
)

session_id = None


class ChatRequest(BaseModel):
    message: str


@app.on_event("startup")
async def startup():
    global session_id

    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )
    session_id = session.id


@app.get("/")
async def home():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/chat")
async def chat(request: ChatRequest):
    question = request.message.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question."
        )

    final_answer = None

    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=question)],
            ),
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    texts = [
                        part.text
                        for part in event.content.parts
                        if part.text
                    ]
                    if texts:
                        final_answer = "\n".join(texts)

        if not final_answer:
            raise HTTPException(
                status_code=502,
                detail="Wesonga did not return an answer."
            )

        return {"answer": final_answer}

    except Exception:
        logger.exception("Error while processing /chat request")
        raise HTTPException(
            status_code=500,
            detail="Wesonga encountered an error. Check the terminal."
        )
