# README.md — DocBot v3

> **Documentation Automation System for Professional User Manuals**

---

## What Is DocBot?

DocBot v3 is a **Python desktop application** that automates the production of professional user-manual Word documents (`.docx`). A documentation writer navigates a target web application in a browser, triggers screen captures with a single mouse gesture, and DocBot handles the rest:

- **Captures** screenshots and extracts DOM structure from the browser
- **Detects** semantic regions (forms, tables, navigation bars, buttons)
- **Compiles** user action steps from recorded browser events
- **Generates** screen names, purpose statements, field descriptions, and procedure steps using a configured LLM
- **Annotates** screenshots with numbered callout bubbles
- **Assembles** a fully-branded, numbered, QA-validated `.docx` manual

All document styling, client branding, and writing voice are driven by YAML configuration — no code changes are needed to onboard a new client.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Windows (Tkinter UI is desktop-native; Playwright supports all platforms)
- A configured LLM provider (Anthropic, Groq, Ollama, or use browser copy-paste mode)

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd doc_automation_v2

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Copy and configure environment variables
copy .env.example .env
# Edit .env and add your API key(s)
```

### Configuration

Edit `config.yaml` to set:

```yaml
provider: anthropic          # or: openai_compat, ollama, browser
current_client: ncd          # client folder name under clients/
```

### Run the Application

```bash
python ui/launcher.py
```

---

## How to Use

### Step 1: Launch the Control Panel

```bash
python ui/launcher.py
```

The Launcher window opens. Select:
- **Client** — the project/client to document (dropdown)
- **Provider** — the LLM backend to use
- **Start URL** — the URL of the application to document
- **Module Name / Number** — the section name for this recording

### Step 2: Record a Module

Click **Start Recording**. A headed Chromium browser opens and navigates to the Start URL.

| Gesture | Action |
|---|---|
| **Middle-click** | Capture the current screen |
| **Double middle-click** | End the session and proceed to AI generation |

Navigate the application, capture each screen you want documented, then double middle-click to finish.

### Step 3: AI Generation

DocBot automatically:
1. Detects semantic regions in each captured screen
2. Compiles user actions into steps
3. Calls the LLM once per screen to generate documentation content
4. Saves results to `sessions/<session_dir>/session.json`

A progress window shows generation status.

### Step 4: Review & Edit

The **Review UI** opens automatically after generation. Here you can:
- Edit screen names, purpose text, field descriptions, and steps
- Drag callout bubbles to better positions
- Resize/move annotation boxes
- Regenerate individual screens

Close the Review UI when satisfied.

### Step 5: Assemble the Module

DocBot automatically assembles a single-module preview document saved to:

```
Final_Manuals/<CLIENT>_<SYSTEM>_User_Manual_v<version>_<timestamp>.docx
```

### Step 6: Assemble the Master Manual

After recording all modules, return to the Launcher and use the **Assemble Master** section:
1. Select the sessions you want to include (in order)
2. Click **Assemble Master Manual**

The full client manual (cover, revision history, TOC, all modules) is saved to `Final_Manuals/`.

---

## Project Structure

```
doc_automation_v2/
├── ui/launcher.py              # Application entry point (run this)
├── main.py                     # Pipeline orchestration
├── config.yaml                 # Runtime configuration
├── .env                        # API keys (never commit)
├── requirements.txt            # Python dependencies
├── docbot/                     # Core library
│   ├── models.py               # Data models (SessionModel, Screen, Region…)
│   ├── recorder/capture.py     # Playwright browser capture
│   ├── processing/             # Region detection, step compilation, AI generation, annotation
│   └── export/qa.py            # Quality assurance
├── manual_builder/             # Word document builder
│   ├── generic_builder.py      # Main builder class
│   └── renderers/              # Per-section renderers
├── providers/                  # LLM provider adapters
├── clients/                    # Per-client configuration (YAML)
│   ├── _default/               # Default/fallback configuration
│   └── <client_key>/           # Client-specific configuration
├── prompts/v3/                 # LLM prompt templates
├── sessions/                   # Captured session data (runtime)
└── Final_Manuals/              # Generated Word documents (output)
```

---

## Client Configuration

Each client is configured via four YAML files in `clients/<client_key>/`:

| File | Purpose |
|---|---|
| `manifest.yaml` | Client name, system name, document version, sections |
| `style.yaml` | Fonts, colors, page margins, annotation style |
| `voice.yaml` | LLM tone rules, example sentences, writing templates |
| `glossary.yaml` | Domain-specific terminology |

To add a new client:
1. `mkdir clients/<new_client_key>`
2. Copy files from `clients/_default/` as a starting point
3. Edit the four YAML files
4. Set `current_client: <new_client_key>` in `config.yaml`

---

## LLM Providers

| Provider | Config Value | Requirements |
|---|---|---|
| Anthropic Claude | `provider: anthropic` | `ANTHROPIC_API_KEY` in `.env` |
| OpenAI-compatible (Groq, Together AI) | `provider: openai_compat` | `OPENAI_API_KEY` in `.env` |
| Ollama (local/cloud) | `provider: ollama` | `OLLAMA_API_KEY` in `.env` (cloud only) |
| Browser copy-paste | `provider: browser` | None — manual interaction |

The **browser** provider opens a Notepad window with the formatted prompt. Paste the response back to continue. No API key required — useful for testing or API-rate-limited situations.

---

## Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=gsk_...
OLLAMA_API_KEY=...
```

> [!CAUTION]
> Never commit `.env` to version control. The `.gitignore` should exclude it.

---

## Running Tests

```bash
pytest tests/ -v
```

Test coverage includes:
- Region detection (IoU merge, parenthesis operator precedence)
- Step compilation (input grouping, click+navigate, change events)
- Figure/table numbering (continuous and module-prefixed modes)
- Provider `chat_json()` fence stripping and retry logic

---

## Troubleshooting

### Browser does not open

Ensure Playwright Chromium is installed:
```bash
playwright install chromium
```

### AI generation produces empty or placeholder content

1. Verify your API key is set correctly in `.env`.
2. Check `sessions/<dir>/run.log` for LLM error messages.
3. Try `provider: browser` to test with manual copy-paste.

### Word document won't open in Microsoft Word

The OOXML validation check should catch this. Check `sessions/<dir>/run.log` for `[QA T5.6]` messages. If OOXML violations are reported, open an issue with the log details.

### Font not found / poor annotation quality

DocBot probes Windows font paths. On non-Windows systems, callout text may use a bitmap fallback font. This does not affect document content, only annotation aesthetics.

### LibreOffice PDF not generated

Install [LibreOffice](https://www.libreoffice.org/) and ensure `soffice` is in your PATH. PDF generation is optional — the `.docx` output is always produced regardless.

---

## Security Notes

- API keys are loaded from environment variables at runtime and are never stored in session data or logs.
- Playwright saves browser authentication state (cookies) to `sessions/state/<client>.json`. Treat this file as sensitive — it can authenticate to the documented application.
- If you have access to the git history, check for any previously committed API keys and rotate them immediately.

---

## License

See [LICENSE](LICENSE) in the repository root.
