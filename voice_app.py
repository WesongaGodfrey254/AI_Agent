"""STA AI web application.

A multi-user, ChatGPT-style interface built on FastAPI and Google ADK:

* Google sign-in with ID-token verification and server-side sessions
* Per-user, persistent conversations, messages and uploads stored in PostgreSQL
* Streaming answers (Server-Sent Events)
* File uploads with text extraction and Gemini-compatible image/PDF parts
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from xml.etree import ElementTree

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response as RawResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.events import Event
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.genai import types
from google.oauth2 import id_token
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, AsyncNullConnectionPool
from pydantic import BaseModel, Field

from agent import root_agent
from db_schema import SCHEMA_STATEMENTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY is missing from .env")

# Google Identity Services client ID. Create an OAuth client of type
# "Web application" in Google Cloud Console and add the deployed HTTPS origin
# (plus http://localhost:8000 for local development) as authorised JS origins.
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()

# PostgreSQL connection string, e.g. postgresql://user:password@host:5432/dbname
# On Render this is injected from the managed database by render.yaml.
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env or the environment.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]

# Optional hardening. TRUSTED_HOSTS is a comma-separated list; when empty,
# all hosts are accepted (useful for local development).
TRUSTED_HOSTS = [host.strip() for host in (os.getenv("TRUSTED_HOSTS") or "").split(",") if host.strip()]
COOKIE_SECURE = (os.getenv("COOKIE_SECURE", "true").strip().lower() not in {"0", "false", "no", "off"})
IS_VERCEL = bool(os.getenv("VERCEL"))

APP_NAME = "weai"
SESSION_COOKIE = "weai_session"
SESSION_LIFETIME_SECONDS = 30 * 24 * 60 * 60

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB per file
MAX_EMBED_BYTES = 8 * 1024 * 1024  # inline bytes sent to Gemini per file
MAX_TEXT_CHARS = 30_000

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".csv", ".tsv", ".log", ".html", ".htm", ".css", ".xml",
    ".yaml", ".yml", ".sql", ".sh", ".env", ".ini", ".toml", ".java",
    ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
}

try:  # Optional: enables PDF text extraction when installed.
    import pypdf  # type: ignore

    PDF_READER = pypdf.PdfReader
except Exception:  # pragma: no cover - depends on local environment
    PDF_READER = None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def now_ts() -> int:
    return int(time.time())


def hash_token(token: str) -> str:
    """Hash session tokens before storing them (a DB leak cannot reuse them)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_pool: AsyncConnectionPool | AsyncNullConnectionPool | None = None
_pool_lock = asyncio.Lock()


def pool() -> AsyncConnectionPool | AsyncNullConnectionPool:
    if _pool is None:
        raise RuntimeError("Database connection pool is not initialised.")
    return _pool


@asynccontextmanager
async def db() -> AsyncIterator[AsyncConnection]:
    async with pool().connection() as connection:
        yield connection


async def init_db() -> None:
    """Open the connection pool and create any missing tables."""
    global _pool
    if _pool is not None:
        return

    async with _pool_lock:
        if _pool is not None:
            return

        pool_kwargs: dict[str, Any] = {
            "conninfo": DATABASE_URL,
            "kwargs": {"row_factory": dict_row},
            "open": False,
        }
        if IS_VERCEL:
            # Serverless functions are stateless and may fan out; avoid holding
            # idle connections across invocations.
            _pool = AsyncNullConnectionPool(**pool_kwargs)
        else:
            _pool = AsyncConnectionPool(
                **pool_kwargs,
                min_size=1,
                max_size=10,
            )

        await _pool.open(wait=True, timeout=30)
        async with db() as connection:
            for statement in SCHEMA_STATEMENTS:
                await connection.execute(statement)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class GoogleCredential(BaseModel):
    credential: str


class ChatRequest(BaseModel):
    conversation_id: str
    message: str = ""
    file_ids: list[str] = Field(default_factory=list)


class ConversationRequest(BaseModel):
    title: str = "New chat"


class TitleRequest(BaseModel):
    title: str


def verify_google_credential(credential: str) -> dict[str, Any]:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured. Add GOOGLE_CLIENT_ID to .env.",
        )

    try:
        info = id_token.verify_oauth2_token(
            credential,
            GoogleAuthRequest(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Google sign-in failed. Please try again.",
        ) from exc

    if info.get("aud") != GOOGLE_CLIENT_ID or not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Invalid Google account.")

    return info


async def current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in with Google.")

    async with db() as connection:
        cursor = await connection.execute(
            """
            SELECT u.sub, u.email, u.name, u.picture
            FROM app_sessions s
            JOIN users u ON u.sub = s.user_sub
            WHERE s.token = %s AND s.expires_at > %s
            """,
            (hash_token(token), now_ts()),
        )
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Your session has expired.")

    return dict(row)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "file"
    return cleaned[:120]


def extract_text(data: bytes, mime_type: str, filename: str) -> str:
    """Best-effort plain-text extraction for uploaded documents."""
    lower = filename.lower()
    try:
        if lower.endswith(".docx") or mime_type.endswith("wordprocessingml.document"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            pieces = [
                node.text or ""
                for node in root.iter()
                if node.tag.endswith("}t")
            ]
            return " ".join(pieces)[:MAX_TEXT_CHARS]

        if lower.endswith(".pdf") and PDF_READER is not None:
            reader = PDF_READER(io.BytesIO(data))
            pages = [(page.extract_text() or "") for page in reader.pages[:40]]
            return "\n".join(pages)[:MAX_TEXT_CHARS]

        if (
            mime_type.startswith("text/")
            or lower.endswith(tuple(TEXT_EXTENSIONS))
            or mime_type
            in {"application/json", "application/xml", "application/javascript"}
        ):
            return data.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
    except Exception as exc:
        logger.info("Could not extract text from %s: %s", filename, exc)

    return ""


def attachment_metadata(attachment: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON-safe part of an attachment (never serialise file bytes)."""
    return {key: value for key, value in attachment.items() if key != "data"}


def build_parts(
    text: str,
    attachments: list[dict[str, Any]],
    *,
    include_bytes: bool = False,
) -> list[types.Part]:
    """Turn a stored message into Gemini content parts."""
    parts: list[types.Part] = []

    for attachment in attachments:
        name = attachment.get("name", "file")
        mime_type = attachment.get("mime_type", "application/octet-stream")
        parts.append(types.Part(text=f"[The user attached a file: {name} ({mime_type})]"))

        extracted = attachment.get("extracted_text") or ""
        if extracted:
            parts.append(
                types.Part(
                    text=(
                        f"--- Text extracted from {name} ---\n"
                        f"{extracted}\n"
                        f"--- End of {name} ---"
                    )
                )
            )

        if include_bytes and mime_type.startswith(("image/", "application/pdf")):
            size = int(attachment.get("size") or 0)
            blob = attachment.get("data") or b""
            if 0 < size <= MAX_EMBED_BYTES and blob:
                try:
                    parts.append(types.Part.from_bytes(data=blob, mime_type=mime_type))
                except Exception as exc:
                    logger.info("Could not embed %s: %s", name, exc)
            elif size > MAX_EMBED_BYTES:
                parts.append(
                    types.Part(
                        text=(
                            f"{name} is too large to embed directly; only its "
                            "metadata and extracted text are available."
                        )
                    )
                )

    if text:
        parts.append(types.Part(text=text))

    return parts or [types.Part(text="(empty message)")]


async def load_attachments(file_ids: list[str], user_sub: str) -> list[dict[str, Any]]:
    """Validate and load uploaded files owned by the current user."""
    unique_ids = list(dict.fromkeys(file_ids))
    if not unique_ids:
        return []

    placeholders = ",".join(["%s"] * len(unique_ids))
    async with db() as connection:
        cursor = await connection.execute(
            f"""
            SELECT id, name, mime_type, size, data, extracted_text
            FROM files
            WHERE user_sub = %s AND id IN ({placeholders})
            """,
            [user_sub, *unique_ids],
        )
        rows = await cursor.fetchall()

    by_id = {row["id"]: dict(row) for row in rows}
    attachments: list[dict[str, Any]] = []
    for file_id in unique_ids:
        row = by_id.get(file_id)
        if not row:
            raise HTTPException(status_code=400, detail="An attached file was not found.")
        attachments.append(row)
    return attachments


# ---------------------------------------------------------------------------
# Runner / session handling
# ---------------------------------------------------------------------------

runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
adk_sessions: dict[str, Session] = {}
session_locks: dict[str, asyncio.Lock] = {}


async def get_adk_session(conversation_id: str, user_sub: str) -> Session:
    """Get (or rebuild from PostgreSQL) the ADK session for a conversation."""
    existing = adk_sessions.get(conversation_id)
    if existing is not None:
        return existing

    lock = session_locks.setdefault(conversation_id, asyncio.Lock())
    async with lock:
        existing = adk_sessions.get(conversation_id)
        if existing is not None:
            return existing

        try:
            session = await runner.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_sub,
                session_id=conversation_id,
            )
            replay_history = True
        except AlreadyExistsError:
            # The in-memory ADK service still has this session (e.g. our local
            # cache was cleared). Reuse it instead of replaying the history.
            session = await runner.session_service.get_session(
                app_name=APP_NAME,
                user_id=user_sub,
                session_id=conversation_id,
            )
            if session is None:
                raise
            replay_history = False

        if replay_history:
            async with db() as connection:
                cursor = await connection.execute(
                    """
                    SELECT role, content, attachments
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY id ASC
                    """,
                    (conversation_id,),
                )
                rows = await cursor.fetchall()

            for row in rows:
                attachments = json.loads(row["attachments"] or "[]")
                is_user = row["role"] == "user"
                await runner.session_service.append_event(
                    session,
                    Event(
                        author="user" if is_user else root_agent.name,
                        content=types.Content(
                            role="user" if is_user else "model",
                            parts=build_parts(row["content"], attachments),
                        ),
                    ),
                )

        adk_sessions[conversation_id] = session
        return session


def sse(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def stream_answer(
    conversation_id: str,
    user_sub: str,
    text: str,
    attachments: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Run the agent and stream its answer as Server-Sent Events."""
    title = (text.strip()[:48] or "File upload") + ("…" if len(text.strip()) > 48 else "")

    async with db() as connection:
        await connection.execute(
            """
            INSERT INTO messages (conversation_id, role, content, attachments, created_at)
            VALUES (%s, 'user', %s, %s, %s)
            """,
            (
                conversation_id,
                text,
                json.dumps([attachment_metadata(item) for item in attachments], ensure_ascii=False),
                now_ts(),
            ),
        )
        await connection.execute(
            """
            UPDATE conversations
            SET title = CASE WHEN title = 'New chat' THEN %s ELSE title END,
                updated_at = %s
            WHERE id = %s
            """,
            (title, now_ts(), conversation_id),
        )

    streamed = ""
    final_text = ""

    try:
        session = await get_adk_session(conversation_id, user_sub)
        new_message = types.Content(
            role="user",
            parts=build_parts(text, attachments, include_bytes=True),
        )

        async for event in runner.run_async(
            user_id=user_sub,
            session_id=session.id,
            new_message=new_message,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            if event.error_code or event.error_message:
                yield sse(
                    {
                        "type": "error",
                        "message": event.error_message or event.error_code,
                    }
                )
                continue

            chunk = "".join(
                part.text
                for part in (event.content.parts if event.content else [])
                if part.text
            )
            if not chunk:
                continue

            if event.partial:
                streamed += chunk
                yield sse({"type": "delta", "text": chunk})
            else:
                final_text = chunk
                if chunk.startswith(streamed):
                    remainder = chunk[len(streamed) :]
                    if remainder:
                        streamed += remainder
                        yield sse({"type": "delta", "text": remainder})
                else:
                    streamed = chunk
                    yield sse({"type": "replace", "text": chunk})

    except Exception as exc:
        logger.exception("STA AI failed to answer in conversation %s", conversation_id)
        yield sse({"type": "error", "message": "STA AI could not complete the request."})
    finally:
        answer = (final_text or streamed).strip()
        if answer:
            async with db() as connection:
                await connection.execute(
                    """
                    INSERT INTO messages
                        (conversation_id, role, content, attachments, created_at)
                    VALUES (%s, 'assistant', %s, '[]', %s)
                    """,
                    (conversation_id, answer, now_ts()),
                )
                await connection.execute(
                    "UPDATE conversations SET updated_at = %s WHERE id = %s",
                    (now_ts(), conversation_id),
                )

    yield sse({"type": "done", "answer": answer})


# ---------------------------------------------------------------------------
# Application + routes
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    try:
        yield
    finally:
        if _pool is not None:
            await _pool.close()


app = FastAPI(title="STA AI", description="STA AI intelligent assistant", lifespan=lifespan)
if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    # Vercel serverless instances can receive requests before lifespan startup
    # has completed in every execution context; ensure the DB is ready.
    if _pool is None:
        await init_db()
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Lightweight readiness probe used by the deployment platform."""
    async with db() as connection:
        await connection.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/api/auth/config")
async def auth_config() -> dict[str, Any]:
    return {"client_id": GOOGLE_CLIENT_ID, "configured": bool(GOOGLE_CLIENT_ID)}


@app.post("/api/auth/google")
async def google_sign_in(
    payload: GoogleCredential,
    response: Response,
) -> dict[str, Any]:
    info = verify_google_credential(payload.credential)
    sub = info["sub"]
    timestamp = now_ts()
    token = secrets.token_urlsafe(32)

    async with db() as connection:
        await connection.execute(
            """
            INSERT INTO users (sub, email, name, picture, created_at, last_login)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (sub) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                picture = excluded.picture,
                last_login = excluded.last_login
            """,
            (
                sub,
                info.get("email", ""),
                info.get("name", ""),
                info.get("picture", ""),
                timestamp,
                timestamp,
            ),
        )
        await connection.execute(
            "INSERT INTO app_sessions (token, user_sub, expires_at, created_at) VALUES (%s, %s, %s, %s)",
            (
                hash_token(token),
                sub,
                timestamp + SESSION_LIFETIME_SECONDS,
                timestamp,
            ),
        )

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {
        "user": {
            "sub": sub,
            "email": info.get("email", ""),
            "name": info.get("name", ""),
            "picture": info.get("picture", ""),
        }
    }


@app.get("/api/auth/me")
async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"user": user}


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    response: Response,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE)
    async with db() as connection:
        await connection.execute("DELETE FROM app_sessions WHERE token = %s", (hash_token(token),))
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return {"ok": True}


async def require_conversation(conversation_id: str, user_sub: str) -> dict[str, Any]:
    async with db() as connection:
        cursor = await connection.execute(
            "SELECT * FROM conversations WHERE id = %s AND user_sub = %s",
            (conversation_id, user_sub),
        )
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return dict(row)


@app.get("/api/conversations")
async def list_conversations(
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    async with db() as connection:
        cursor = await connection.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT content FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.id DESC LIMIT 1) AS last_message
            FROM conversations c
            WHERE c.user_sub = %s
            ORDER BY c.updated_at DESC
            """,
            (user["sub"],),
        )
        rows = await cursor.fetchall()
    return {"conversations": [dict(row) for row in rows]}


@app.post("/api/conversations", status_code=201)
async def create_conversation(
    payload: ConversationRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    timestamp = now_ts()
    async with db() as connection:
        await connection.execute(
            """
            INSERT INTO conversations (id, user_sub, title, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                conversation_id,
                user["sub"],
                (payload.title or "New chat").strip()[:120] or "New chat",
                timestamp,
                timestamp,
            ),
        )
    return {
        "id": conversation_id,
        "title": payload.title or "New chat",
        "created_at": timestamp,
        "updated_at": timestamp,
    }


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    conversation = await require_conversation(conversation_id, user["sub"])
    async with db() as connection:
        cursor = await connection.execute(
            """
            SELECT id, role, content, attachments, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        rows = await cursor.fetchall()

    messages = []
    for row in rows:
        item = dict(row)
        item["attachments"] = json.loads(item["attachments"] or "[]")
        messages.append(item)
    return {**conversation, "messages": messages}


@app.patch("/api/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    payload: TitleRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    await require_conversation(conversation_id, user["sub"])
    title = payload.title.strip()[:120] or "New chat"
    async with db() as connection:
        await connection.execute(
            "UPDATE conversations SET title = %s, updated_at = %s WHERE id = %s",
            (title, now_ts(), conversation_id),
        )
    return {"id": conversation_id, "title": title}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, bool]:
    await require_conversation(conversation_id, user["sub"])
    async with db() as connection:
        await connection.execute(
            "DELETE FROM conversations WHERE id = %s", (conversation_id,)
        )
    adk_sessions.pop(conversation_id, None)
    session_locks.pop(conversation_id, None)
    return {"ok": True}


@app.post("/api/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    uploaded: list[dict[str, Any]] = []

    for upload in files:
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename} is larger than the 20 MB limit.",
            )

        name = safe_filename(upload.filename or "file")
        mime_type = (
            upload.content_type
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream"
        )
        file_id = str(uuid.uuid4())
        extracted = await asyncio.to_thread(extract_text, data, mime_type, name)
        async with db() as connection:
            await connection.execute(
                """
                INSERT INTO files
                    (id, user_sub, name, mime_type, size, data, extracted_text, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_id,
                    user["sub"],
                    name,
                    mime_type,
                    len(data),
                    data,
                    extracted,
                    now_ts(),
                ),
            )

        uploaded.append(
            {
                "id": file_id,
                "name": name,
                "mime_type": mime_type,
                "size": len(data),
                "preview": extracted[:300],
            }
        )

    return {"files": uploaded}


@app.get("/api/files/{file_id}")
async def download_file(
    file_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> RawResponse:
    async with db() as connection:
        cursor = await connection.execute(
            "SELECT name, mime_type, data FROM files WHERE id = %s AND user_sub = %s",
            (file_id, user["sub"]),
        )
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found.")

    filename = safe_filename(row["name"])
    return RawResponse(
        content=row["data"],
        media_type=row["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/chat")
async def chat(
    payload: ChatRequest,
    user: dict[str, Any] = Depends(current_user),
) -> StreamingResponse:
    message = payload.message.strip()
    if not message and not payload.file_ids:
        raise HTTPException(status_code=400, detail="Please enter a message.")

    await require_conversation(payload.conversation_id, user["sub"])
    attachments = await load_attachments(payload.file_ids, user["sub"])

    return StreamingResponse(
        stream_answer(payload.conversation_id, user["sub"], message, attachments),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
