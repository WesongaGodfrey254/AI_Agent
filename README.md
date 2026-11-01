# Wesonga AI Research Assistant

**A personal AI assistant for research, Python programming, cybersecurity, and general knowledge.**

## 1. Overview

Wesonga AI Research Assistant is a Python-based artificial intelligence project designed to answer questions, support research, assist with programming, and provide information about cybersecurity and other technical subjects.

The project uses Google's Agent Development Kit (ADK), a Gemini language model, and Google Search for supported web research. A FastAPI web application provides a browser-based interface for text conversations and voice interaction.

The long-term goal is to develop Wesonga into a practical AI assistant that can help with coding tasks, inspect files in an approved workspace, perform basic project checks, and interact with Visual Studio Code through controlled actions.

## 2. Features

- **AI conversations:** Answers questions in natural language.
- **Python programming:** Explains Python concepts and helps with coding tasks.
- **Cybersecurity learning:** Supports security education, technical cresearch, and defensive security concepts.
- **Web research:** Uses Google Search when current information is needed and the search tool is available.
- **Voice interaction:** Supports speech input and spoken responses through the web interface, subject to browser and microphone support.
- **Personalized identity:** Uses the name Wesonga and can reference documented biography information.
- **Workspace file tools:** Supports listing, reading, and writing files in a configured workspace.
- **Project checks:** Can run supported syntax checks and configured tests.
- **VS Code integration:** Can request VS Code to open the approved workspace and send a limited set of keyboard shortcuts.

Some capabilities depend on the installed dependencies, API access, browser support, and the coding tools configured in the project.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| Google ADK | Agent creation and orchestration |
| Gemini | AI language model |
| Google Search | Web research |
| FastAPI | Backend web application |
| Uvicorn | ASGI development server |
| HTML, CSS and JavaScript | Browser interface |
| Speech Recognition API | Voice input where supported |
| Speech Synthesis API | Spoken responses where supported |
| Visual Studio Code | Code editing and development |

## 4. Project Structure

The project is organized around the following files:

```text
AI_Agent1/
├── agent.py
├── voice_app.py
├── coding_tools.py
├── life_history.md
├── requirements.txt
├── README.md
├── .env
├── venv/
└── web/
    └── index.html
```

**File descriptions**

- `agent.py` — Defines the AI agent, its instructions, model, and tools.
- `voice_app.py` — Runs the FastAPI application and handles browser chat requests.
- `coding_tools.py` — Contains workspace file operations, project checks, and limited VS Code controls.
- `life_history.md` — Stores biography information used to answer relevant questions.
- `requirements.txt` — Lists Python dependencies.
- `.env` — Stores local environment variables, including the Google API key.
- `web/index.html` — Provides the browser interface.
- `venv/` — Holds the Python virtual environment when configured.

The structure above describes the intended project layout; some optional files may not exist until they are created.

## 5. Requirements

Before running the application, make sure you have:

- Python installed.
- A working Python virtual environment.
- A Google AI API key with access to the configured Gemini model.
- The project dependencies installed.
- A modern web browser.
- Internet connectivity for Gemini requests and online search.
- `xdotool` and VS Code installed if using the desktop-control functions on Linux.

## 6. Installation

### Step 1: Open the project directory

```bash
cd ~/Desktop/AI_Agent1
```

### Step 2: Activate the virtual environment

If your virtual environment already exists:

```bash
source venv/bin/activate
```

### Step 3: Install dependencies

```bash
python -m pip install -r requirements.txt
```

If `requirements.txt` does not include a required package, add the appropriate dependency before running the application.

### Step 4: Configure the API key

Create or edit the `.env` file:

```bash
nano .env
```

Add your own valid API key:

```dotenv
GOOGLE_API_KEY=your_google_api_key_here
```

Replace the placeholder with your actual key. Never publish your API key in GitHub, screenshots, or public documentation.

### Step 5: Check the Python files

```bash
python -m py_compile agent.py voice_app.py coding_tools.py
```

This checks syntax; it does not guarantee that the API, model, or every tool will work.

## 7. Running the Application

Start the web server from the project directory:

```bash
uvicorn voice_app:app --reload
```

Open the following address in your browser:

```text
http://127.0.0.1:8000
```

To stop the development server, press `Ctrl+C` in the terminal.

The `--reload` option is intended for development, not production deployment.

## 8. Using Wesonga

You can use natural-language questions such as:

- "What is your name?"
- "Explain Python functions with examples."
- "Explain how DNS works."
- "Help me debug this Python function."
- "Research recent developments in defensive cybersecurity."
- "List the files in my approved coding workspace."
- "Create a Python file in my approved workspace."
- "Run a syntax check on my workspace."
- "Open my workspace in VS Code."

The assistant's actual abilities depend on the tools configured and the permissions granted to the running application.

## 9. Workspace and File Safety

Workspace tools are designed to operate inside an approved project directory rather than freely access the whole computer.

Recommended practices:

1. Keep experimental projects in a dedicated workspace.
2. Back up existing files before modifying them.
3. Never expose `.env` files, passwords, API keys, or other secrets to the AI.
4. Review generated code before executing it.
5. Run tests only in projects whose code you trust.
6. Ask for confirmation before destructive or privileged operations.
7. Do not give an AI agent unrestricted shell or administrator access.

Workspace restrictions are application-level safeguards and should be tested before relying on them for sensitive projects.

## 10. Troubleshooting

### API key error

Check that `.env` exists, contains `GOOGLE_API_KEY`, and is loaded by the application. Verify that the key is valid and has the required API access.

### Gemini returns HTTP 400

Review the error message and check whether the configured model supports the selected combination of built-in tools and function-calling tools.

### Workspace appears empty

Check the configured workspace path and list its contents:

```bash
ls -la ~/WesongaWorkspace/projects/default
```

Files in `~/Desktop/AI_Agent1` will not automatically appear in a separate workspace directory.

### Web application does not start

Check that the virtual environment is activated and dependencies are installed:

```bash
python -c "import fastapi, google.adk; print('Imports successful')"
```

### Voice input does not work

Check microphone permissions, browser compatibility, and whether the browser supports the speech recognition features used by the interface.

## 11. Security and Privacy

Wesonga is a development project. Do not assume that conversations, local files, or API requests are automatically private or encrypted end-to-end.

- Keep API keys and credentials private.
- Avoid storing personal or confidential information unnecessarily.
- Use access controls when exposing the application to other devices.
- Do not expose the development server directly to the public internet.
- Inspect generated code and search results before using them.
- Apply appropriate authentication and authorization before deploying the application for multiple users.

## 12. Future Improvements

Potential future development includes:

- More reliable speech input and spoken responses.
- Streaming AI responses.
- Improved error handling and API retry logic.
- Better workspace browsing and file-editing workflows.
- Automated tests and code-quality checks.
- A project history and change-review interface.
- Authentication and user-specific sessions.
- Secure deployment and monitoring.
- Support for additional approved development tools.

## 13. License

No license has been specified yet. Add a license file before distributing the project if you intend to make it open source.

## 14. Author and Project

**Project:** Wesonga AI Research Assistant  
**Language:** Python  
**Primary purpose:** AI-assisted research, programming, and cybersecurity education  
**Status:** Under development
