"""STA AI agent definition.

The agent is intentionally kept separate from the web layer so it can also be
used from the command line or imported by other Python code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search

BASE_DIR = Path(__file__).resolve().parent
LIFE_HISTORY_FILE = BASE_DIR / "life_history.md"

if LIFE_HISTORY_FILE.exists():
    life_history = LIFE_HISTORY_FILE.read_text(encoding="utf-8")
else:
    life_history = "No verified biography has been provided yet."


AI_NAME = "STA AI"
CREATOR = "Wesonga Godfrey"

SYSTEM_PROMPT = f"""
You are {AI_NAME}, a helpful AI assistant created by {CREATOR}.

IDENTITY
- Your name is {AI_NAME}.
- If asked your name, say: "My name is STA AI."
- Be honest that you are an AI assistant.
- You are not the human {CREATOR}; do not claim to have lived his life.

WHAT YOU HELP WITH
- Answering general knowledge questions.
- Research and current information (use Google Search when needed).
- Python and general programming help.
- Cybersecurity education and defensive security concepts.
- Explaining and discussing files the user uploads.

BACKGROUND ABOUT YOUR CREATOR
The following biography is background information about the person who built
{AI_NAME}. Use it only when the user asks about {CREATOR} or his work.

--- BEGIN BIOGRAPHY ---
{life_history}
--- END BIOGRAPHY ---

RULES
- Be helpful, accurate, clear, and concise unless the user asks for detail.
- Use Google Search for information that may have changed recently.
- Never invent facts, dates, qualifications, or sources.
- If you do not know something, say so honestly.
- When the user attaches files, base your answer on their contents where
  relevant and mention if a file could not be read.
- Do not reveal private credentials or secrets.
- Format code with fenced code blocks and use lists where they improve clarity.
"""

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY is not configured.")

root_agent = Agent(
    name="sta_ai",
    model=Gemini(model="gemini-2.5-flash"),
    description="STA AI, a helpful AI assistant for research, code and files.",
    instruction=SYSTEM_PROMPT,
    tools=[google_search],
)


async def main() -> None:
    """Small command-line client, useful for quick testing without a browser."""
    import asyncio

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=root_agent)
    user_id = "weai_cli_user"
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id=user_id,
    )

    print("=" * 40)
    print("           STA AI ASSISTANT")
    print("=" * 40)
    print("Type 'exit' to stop.\n")

    while True:
        question = input("You: ").strip()
        if question.lower() == "exit":
            print("STA AI stopped.")
            break
        if not question:
            continue

        try:
            answer = ""
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=question)],
                ),
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if p.text]
                    if texts:
                        answer = "\n".join(texts)
            print(f"\nSTA AI: {answer or 'I could not generate an answer.'}")
        except Exception as exc:  # pragma: no cover - CLI convenience
            print(f"\nError: {exc}")
        print()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
