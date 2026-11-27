# STA AI

**STA AI is a ChatGPT-style AI assistant you sign into with Google.** It keeps a separate chat history for every user, streams answers as they are written, and lets you attach files (including images and documents) to your messages.

It is built with FastAPI, Google's Agent Development Kit (ADK), Gemini 2.5 Flash, Google Search, **PostgreSQL**, and the Google Identity Services sign-in button.

## Features

- **Google sign-in** — users authenticate with a Google account before they can chat.
- **ChatGPT-like interface** — conversation sidebar, new-chat button, message history, streaming replies, copy/speak actions, and responsive mobile layout.
- **Per-user chat history** — conversations, messages and uploaded files are stored in PostgreSQL and restored when a conversation is reopened.
- **File uploads** — attach up to 20 MB per file. Text files, Markdown, source code, CSV, JSON, DOCX and PDFs have their text extracted; images and PDFs are also sent to Gemini for visual/document understanding. File bytes are stored in PostgreSQL, so deployments need no persistent local disk.
- **Voice input and speech output** — browser speech recognition and speech synthesis, with a microphone button in the composer.
- **Web research** — the agent can call Google Search when current information is needed.
- **Dark and light mode** — switch themes from the sign-in screen or the chat header; the choice is remembered in your browser.
- **Session security** — Google ID tokens are verified on the server; random session tokens are stored only as SHA-256 hashes and sent to the browser in an HttpOnly, SameSite=Lax, Secure cookie.

## Project structure

```text
AI_Agent-main/
├── app.py                          # Vercel entrypoint (exports the FastAPI `app`)
├── agent.py                        # STA AI agent definition (Gemini + Google Search)
├── voice_app.py                    # FastAPI app: auth, chats, history, uploads, streaming
├── db_schema.py                    # Shared PostgreSQL schema
├── life_history.md                 # Background about the creator, used only when relevant
├── requirements.txt                # Python dependencies
├── .python-version                 # Python version pinned for Vercel (3.12)
├── .env.example                    # Template of required environment variables (no secrets)
├── vercel.json                     # Vercel function timeout configuration
├── Dockerfile                      # Production container image
├── docker-compose.yml              # Local app + PostgreSQL
├── render.yaml                     # Render Blueprint (web service + managed PostgreSQL)
├── migrate_sqlite_to_postgres.py   # One-off migration from the old SQLite database
├── .github/workflows/ci.yml        # Secret guard + import smoke test
├── web/
│   ├── index.html                  # STA AI single-page interface
│   ├── sta-ai-logo.webp            # Logo used across the UI
│   └── favicon.png                 # Browser tab icon
└── data/                           # Legacy SQLite DB (gitignored, not used at runtime)
```

## Configuration

Copy the template and fill in the real values:

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Gemini API key from Google AI Studio / Google Cloud. |
| `GOOGLE_CLIENT_ID` | Yes | OAuth **Web application** client ID for Google Identity Services. This value is public by design, but keep it in configuration rather than source code. |
| `DATABASE_URL` | Yes | PostgreSQL connection string, e.g. `postgresql://user:password@host:5432/dbname`. |
| `COOKIE_SECURE` | No | Defaults to `true` and is forced to `true` on Vercel. Set to `false` only for local HTTP development if the browser will not store Secure cookies on `localhost`. |
| `TRUSTED_HOSTS` | No | Comma-separated list of allowed Host headers. For Vercel use your exact host(s), e.g. `sta-ai.vercel.app,sta_ai.vercel.com`. When unset, Vercel automatically trusts its own `VERCEL_URL`; locally all hosts are accepted. |

`GOOGLE_CLIENT_SECRET` is **not** used by this app (the browser receives an ID token and the server verifies it), so it should not be added to the deployment or committed anywhere.

### Google OAuth setup

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. Create an OAuth client ID of type **Web application**.
3. Under **Authorised JavaScript origins**, add your production origin, e.g. `https://sta-ai.onrender.com`. For local development also add `http://localhost:8000` and `http://127.0.0.1:8000`.
4. Copy the **Client ID** into `.env` (local) or into the Render service environment (deployment). No redirect URI is needed for Google Identity Services popup mode.

## Local development

### Option A — Docker Compose (recommended)

1. Create `.env` from `.env.example`. The `DATABASE_URL` in the template already points at the Compose database.
2. Start everything:

   ```bash
   docker compose up --build
   ```

3. Open <http://127.0.0.1:8000>, sign in with Google, and start chatting.

The schema is created automatically on startup. Uploaded files live in the `pgdata` Docker volume.

### Option B — run uvicorn directly

1. Start a PostgreSQL server and create a database.
2. Set `DATABASE_URL` in `.env` to point at it.
3. Install dependencies and run:

   ```bash
   python -m venv venv
   source venv/bin/activate
   python -m pip install -r requirements.txt
   uvicorn voice_app:app --reload
   ```

## Deploying to Vercel (public URL)

Vercel generates `*.vercel.app` hostnames with hyphens, so the project should be named **`sta-ai`** and its default public URL is **`https://sta-ai.vercel.app`**. An underscore hostname such as `sta_ai.vercel.com` is not a valid DNS hostname and is not Vercel-generated; it only works if you own that domain and add it as a custom domain. The configuration below accepts both names if you do.

This repo is already Vercel-ready: `app.py` exports the FastAPI `app`, `.python-version` pins Python 3.12, and `vercel.json` sets a 60-second function timeout. Vercel runs the app as a serverless function, so you must use an **external PostgreSQL database** (Neon/Supabase/Render Postgres/etc.). The Docker-only `db` hostname will not resolve there.

1. Push the repo to GitHub (`git push origin main`).
2. In Vercel, **Add New → Project** and import `WesongaGodfrey254/AI_Agent`.
3. Let Vercel detect the Python/FastAPI preset (or choose **Other**). No build command is required.
4. Add these Environment Variables in **Project Settings → Environment Variables** (never commit them):

   | Variable | Value |
   |---|---|
   | `GOOGLE_API_KEY` | Gemini API key from Google AI Studio / Google Cloud |
   | `GOOGLE_CLIENT_ID` | Google OAuth **Web application** client ID |
   | `DATABASE_URL` | External Postgres URL, e.g. `postgresql://user:password@host:5432/dbname?sslmode=require` |
   | `COOKIE_SECURE` | `true` (also forced by the app on Vercel) |
   | `TRUSTED_HOSTS` | `sta-ai.vercel.app,sta_ai.vercel.com` — list only the hosts you actually serve |

   For preview deployments, either leave `TRUSTED_HOSTS` unset (the app then trusts Vercel's own `VERCEL_URL`) or add your preview hostnames to the list.

5. Deploy and copy the URL from the dashboard.
6. In Google Cloud Console → OAuth client → **Authorised JavaScript origins**, add the exact HTTPS origin(s): `https://sta-ai.vercel.app` (and `https://sta_ai.vercel.com` if used as a custom domain), plus `http://localhost:8000` for local development. No redirect URI is needed.
7. Verify `https://sta-ai.vercel.app/api/health` returns `{"status":"ok"}` and that `/` shows the sign-in screen with a working Google button.

**Custom domain:** In Vercel **Project Settings → Domains**, add `sta_ai.vercel.com` only if you control that domain, then update `TRUSTED_HOSTS` and the OAuth origins above to include it.

**Vercel notes**

- **Database**: Use a managed Postgres with enough connections/storage for your expected traffic. Add `?sslmode=require` to `DATABASE_URL`. The app uses a serverless-friendly null connection pool on Vercel.
- **Timeouts**: `vercel.json` sets `maxDuration` to 60s for `app.py`. Long Gemini/tool responses may still hit plan limits; upgrade/configure Vercel plan limits as needed.
- **State**: Chat history/files are persisted in Postgres. ADK in-memory session cache is per serverless instance and may be rebuilt from DB on cold starts.
- **Uploads**: Files are stored in Postgres BYTEA (no local disk needed), but keep Vercel request body limits in mind.
- **Security**: Session cookies are HttpOnly, SameSite=Lax and Secure; HSTS is added on HTTPS responses. `TRUSTED_HOSTS` rejects unexpected Host headers. The CI workflow fails if a `.env` file or obvious credential is committed.

## Deploying to Render

The repository includes a [Render Blueprint](https://render.com/docs/blueprint-spec) that provisions both the web service and a managed PostgreSQL database.

1. Push your changes to GitHub (the Blueprint is read from the repository root).
2. In Render, choose **New → Blueprint** and select `WesongaGodfrey254/AI_Agent`.
3. Name the Blueprint and click **Apply**. Render will prompt for `GOOGLE_API_KEY` and `GOOGLE_CLIENT_ID`; enter them in the Dashboard, **never in the repository**.
4. Render injects `DATABASE_URL` automatically from the managed database and sets `COOKIE_SECURE=true`.
5. Add the service's HTTPS URL to the authorised JavaScript origins of your Google OAuth client (see above).
6. Check `https://<your-service>.onrender.com/api/health` — it should return `{"status":"ok"}`.

The Docker image listens on `$PORT` (set by Render), runs as a non-root user, and contains no credentials. Free plans spin down when idle and the free Postgres instance is limited to 1 GB; upgrade both for always-on production traffic and more upload storage.

### Migrating existing SQLite data

If you have an old `data/weai.db`, run this once against a **new, empty** PostgreSQL database before starting the app for the first time:

```bash
export DATABASE_URL='postgresql://user:password@host:5432/dbname'
python migrate_sqlite_to_postgres.py
```

The script copies users, sessions (re-hashing the tokens), conversations, messages and uploaded file bytes from the old filesystem paths into PostgreSQL. Review the output, then keep the SQLite file only as a backup.

## Security notes

- `.env`, `.env.*` (except `.env.example`), `data/`, virtualenvs and Docker secrets are gitignored; a CI check fails if a `.env` file is ever committed.
- No API keys, client IDs, passwords or database URLs are hardcoded in source code or in `render.yaml`.
- Session cookies are HttpOnly, SameSite=Lax and Secure in production; only a SHA-256 hash of each token is stored in the database.
- Set `TRUSTED_HOSTS` to your production hostname to reject requests with unexpected Host headers.
- Uploaded files are stored as database bytes, so they survive container restarts and redeploys.
- Rotate `GOOGLE_API_KEY` and any OAuth client secret in Google Cloud Console if they were ever exposed. The OAuth client ID itself is public and cannot be kept secret.

## Troubleshooting

| Problem | What to check |
|---|---|
| Google button does not appear | `GOOGLE_CLIENT_ID` is set, and the exact URL you are using is an authorised JavaScript origin. |
| "Google sign-in failed" | Client ID matches the origin; browser clock is correct. |
| "GOOGLE_API_KEY is missing" | Add a valid Gemini API key to `.env` / Render environment. |
| "DATABASE_URL is missing" | Add the PostgreSQL connection string, or deploy with the Blueprint so Render injects it. |
| `/api/health` fails on Vercel | `DATABASE_URL` is unreachable from Vercel; use an external Postgres URL with `?sslmode=require`, not the Docker `db` host. |
| `400 Invalid host header` on Vercel | Add the exact hostname to `TRUSTED_HOSTS`, or leave it unset so Vercel's `VERCEL_URL` is trusted. |
| Google button missing on Vercel | The exact HTTPS origin is in `GOOGLE_CLIENT_ID`'s authorised JavaScript origins and Vercel env vars were set for Production. |
| Uploads fail | Each file must be 20 MB or smaller, and the database must have enough free storage. |
| No answer is streamed | Check the application logs; the ADK/Gemini request may have failed. |
| Old chat history is missing | Run `migrate_sqlite_to_postgres.py` against the new database. |

## License

No license has been specified yet.
