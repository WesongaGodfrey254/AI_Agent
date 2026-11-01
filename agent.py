import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types
from pathlib import Path

# Load Wesonga's biography
BASE_DIR = Path(__file__).resolve().parent
LIFE_HISTORY_FILE = BASE_DIR / "life_history.md"

if LIFE_HISTORY_FILE.exists():
    life_history = LIFE_HISTORY_FILE.read_text(encoding="utf-8")
else:
    life_history = "No verified biography has been provided yet."


# AI identity
AI_NAME = "Wesonga"

SYSTEM_PROMPT = f"""
You are {AI_NAME}, a personal AI research assistant.
Your name is {AI_NAME}.

You help with Python programming, cybersecurity,
research, and general questions.

Be helpful, accurate, and clear.
If you don't know an answer, say so honestly.


"""

# Load environment variables
load_dotenv()

# Check API key
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY is not configured.")

# Create the AI agent
root_agent = Agent(
    name="wesonga",

    model=Gemini(
        model="gemini-2.5-flash"
    ),

    description="Wesonga, is a personal AI research assistant.",

            
    instruction=f"""
        You are Wesonga, a personal AI research assistant.

        IDENTITY:
        - Your name is Wesonga.
        - If asked your name, say: "My name is Wesonga."
        - You assist with Python programming, cybersecurity,
        research, and general questions.
        - Be helpful, accurate, and clear.
        - Be honest about being an AI assistant.

        PERSONAL LIFE HISTORY:
        The following text is the biography provided for Wesonga.

        --- BEGIN BIOGRAPHY ---
        {life_history}
        --- END BIOGRAPHY ---

        When asked about Wesonga's life:
        1. Use the biography above as your primary source.
        2. Explain events chronologically when asked for his full story.
        3. Cover birth, childhood, family background, primary
        education, secondary education, further education,
        skills, projects, and career where information exists.
        4. Never invent dates, schools, qualifications, family
        details, or life events.
        5. If a detail is missing, say it has not been provided.
        6. Distinguish the real person Wesonga from this AI assistant.
        7. Do not claim that you personally experienced his life.

        GENERAL ANSWERING RULES:
        - Provide a useful answer when the question is understandable.
        - Use Google Search when current information is needed.
        - Do not invent facts.
        - If you do not know, say so honestly.
        - Do not return empty responses intentionally.
        - Keep answers relevant to the user's question.
        - Ask for clarification if a question is unclear.
        - Do not expose private credentials or secrets.
        """,


    tools=[google_search]
)



async def main():
    runner = InMemoryRunner(agent=root_agent)

    user_id = "wesonga_user"
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id=user_id
    )

    print("================================")
    print("      WESONGA AI ASSISTANT")
    print("================================")
    print("Type 'exit' to stop.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() == "exit":
            print("Wesonga stopped.")
            break

        if not question:
            print("Please enter a question.\n")
            continue

        try:
            final_answer = None

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=question)]
                )
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

            if final_answer:
                print(f"\nWesonga: {final_answer}")
            else:
                print("\nWesonga: I couldn't generate an answer. Please try again.")

        except Exception as e:
            print(f"\nError: {e}")

        print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
