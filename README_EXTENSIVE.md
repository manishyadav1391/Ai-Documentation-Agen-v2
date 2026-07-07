# Documentation Automation Bot — Extensive Project README

## 1) What this project does (high-level)
This repository automates the creation of user manuals (in **.docx**) from recorded UI workflows.

The workflow is:
1. **Capture**: Open a browser and capture each UI “screen” the user navigates through. For every screen, the bot saves:
   - a full-page screenshot (`screen_N.png`)
   - an extracted DOM-element inventory (`screen_N_elements.json`)
   - extracted page context (`screen_N_meta.json`)
2. **Detect regions**: Heuristically group DOM elements into **semantic regions** (headers, navigation bars, filter forms, table headers, action buttons, section headings, etc.).
3. **LLM labeling**: Use an LLM provider to assign meaningful **labels** to those semantic regions and suggest a **screen name/title**.
4. **Human review (UI)**: A Tkinter window shows the screenshot and labeled regions. You can edit region bounding boxes/labels and provide the final **screen name**.
5. **Render annotations**: Generate an annotated screenshot (`screen_N_annotated.png`) by drawing region boxes + callouts.
6. **Generate content**: Use the LLM to produce:
   - **field descriptions** for form fields
   - **procedure prose** (step-by-step instructions) for the screen workflow
7. **Assemble docx**:
   - assemble a per-session module draft (`module_draft.docx`)
   - optionally assemble all modules into a **final client manual** (`Final_Client_Manual.docx`) 

You can run the full experience through the Tkinter **Launcher UI**.

---

## 2) Key files and responsibilities (quick map)

### Entry points
- **`main.py`**: Runs the core capture → detect → label → review → render → generate content → assemble module pipeline for the latest session.
- **`ui/launcher.py`**: Provides the interactive launcher UI:
  - start recording a new module
  - assemble the master manual from multiple recorded sessions
- **`review_ui.py`**: The Tkinter editor for region labels and bounding boxes, with navigation controls (prev/next/quit).

### Capture + region detection
- **`capture.py`**: Browser automation + DOM extraction + screenshot capture.
- **`detect_regions.py`**: Heuristic region grouping from `screen_N_elements.json`.

### LLM orchestration + content generation
- **`labeler.py`**: Orchestrates provider calls to label regions and generate screen content.
- **`providers/base.py`**: Provider abstraction (common methods for labeling, field descriptions, procedure prose).
- **`providers/browser.py`**: “Copy-paste” provider (writes prompts to disk; user pastes LLM output back into a file).
- **`providers/anthropic_api.py`**: Native Anthropic API provider.
- **`providers/openai_compat.py`**: OpenAI-compatible provider (Groq/Together/etc.).
- **`providers/ollama.py`**: Ollama local/remote provider.
- **`llm_ui.py`**: Tkinter tool to run a prompt through the selected provider (or copy-paste prompt in browser mode).

### Rendering + docx assembly
- **`annotate.py`**: Draws callouts and region boxes on screenshots → `screen_N_annotated.png`.
- **`assemble.py`**: Builds a single-session module draft (`module_draft.docx`).
- **`master_assembler.py`**: Combines multiple modules into `Final_Client_Manual.docx`.
- **`templates/`**:
  - **`templates/base.py`**: shared DocumentBuilder utilities (Word headers/footers, borders, TOC field, etc.)
  - **`templates/corporate/builder.py`**: Corporate-styled docx layout.

### Configuration
- **`config.py`**: Loads `config.yaml` + environment variables for API keys.
- **`config.yaml`**: Default configuration (provider choice, model names, render styling, brand theme).

---

## 3) End-to-end workflow (the actual runtime flow)

### 3.1 Launching
Run the launcher UI:
- It lets you **configure brand styling** and **start a new recording**.

Under the hood:
- `ui/launcher.py` imports `run_pipeline` from `main.py`.

### 3.2 Capture phase (`main.py` → `capture.py`)
`main.py` loads configuration and constructs the selected provider.
Then it calls:
- `capture.run_capture_session()`

#### Capture controls
When Playwright opens Chromium:
- **Single middle-click**: capture current screen
- **Double middle-click**: quit capture session and start processing

#### What `capture.py` saves per screen
For `screen_index = 1, 2, ...`:
- `screen_{i}.png`: full-page screenshot (`page.screenshot(full_page=True)`)
- `screen_{i}_elements.json`: extracted DOM elements via injected JS
- `screen_{i}_meta.json`: page metadata (title, H1, breadcrumb, active tab, URL)

The DOM inventory includes:
- interactive controls (buttons/inputs/selects/etc.) with bounding boxes
- navigation links
- headings/labels
- table column headers

### 3.3 Region detection (`main.py` → `detect_regions.py`)
For each captured screen:
- `process_screen_regions(latest_session, screen_index)`

This reads:
- `screen_{i}_elements.json`

And produces:
- `screen_{i}_regions.json`

Regions are created using heuristics such as:
- `detect_page_header`
- `detect_navigation_bar`
- `detect_filter_regions`
- `detect_table_headers`
- `detect_action_columns`
- `detect_standalone_actions`
- `detect_section_labels`

If heuristics find nothing, it falls back to an **element-level region** strategy.

### 3.4 Region labeling + screen title suggestion (`main.py` → `labeler.py`)
For each screen:
- `Labeler.label_screen_regions(session_dir, screen_index)`

This reads:
- `screen_{i}_regions.json`

Creates provider input objects and calls:
- `provider.label_regions_with_title(...)`

Results:
- `screen_{i}_labeled.json`: regions with a `label` per region
- (optional) `screen_{i}_meta.json.screen_name`: suggested by LLM when missing

### 3.5 Human review editor (`main.py` → `review_ui.py`)
`open_review_ui(session_dir, screen_index, total_screens=N)` opens the Tkinter editor.

The editor:
- shows the screenshot `screen_{i}.png`
- shows detected regions with their current labels
- lets the user:
  - double-click a region to edit label/role + bbox coords
  - delete a region
  - add a new region
  - fine-tune bbox via nudge/resize buttons
  - enter the final **Screen Name** in the top bar

Navigation buttons:
- Previous, Next, Quit Session

When you press Next/Prev/Quit, the editor saves:
- `screen_{i}_final.json`: filtered region list (deleted removed)
- updates `screen_{i}_meta.json.screen_name` with your entered Screen Name

### 3.6 Rendering annotations (`main.py` → `annotate.py`)
After review for each screen:
- `render_annotations(session_dir, screen_index)`

This reads:
- `screen_{i}_final.json`
- `screen_{i}.png`

Then draws:
- region bounding boxes (stroke color depends on role)
- callout bubbles + leader lines (overlap-aware placement)

It writes:
- `screen_{i}_annotated.png`

### 3.7 Content generation (`labeler.generate_screen_content`)
When moving forward in the multi-screen loop:
- `Labeler.generate_screen_content(session_dir, screen_index)`

This produces `screen_{i}_content.json` containing:
- `field_descriptions`: a list of `{field_name, description}`
- `procedure_prose`: rendered narrative with structured markers
- `screen_name`, `page_title`

#### Field description generation
It builds a field list from DOM elements:
- interactive inputs (input/select/textarea)
- skips password fields and `[REDACTED]` values
- determines which region bbox contains each field (center point containment test)

Then it calls provider:
- `provider.describe_fields(...)`

#### Procedure prose generation
It converts region list into a simplified **action sequence**.
Then it calls:
- `provider.procedure_prose(...)`

### 3.8 Docx assembly

#### Per-session module draft (`assemble.py`)
After all screens are processed:
- `assemble_module(latest_session)`

It uses the configured template:
- `templates/corporate/builder.py` (default)

And writes:
- `sessions/session_*/module_draft.docx`

For each screen, it injects:
- annotated screenshot
- procedure prose
- interface element dictionary table

#### Master client manual (`master_assembler.py`)
From the launcher UI:
- select multiple session folders
- click assemble

Then:
- `assemble_master_manual(ordered_session_dirs, Final_Client_Manual.docx)`

It adds global cover, revision history, TOC placeholder, then:
- inserts module divider pages
- injects each screen section into the master document using a **global screen counter**

---

## 4) How configuration works

### `config.yaml`
Example keys:
- `provider`: `browser | anthropic | openai_compat | ollama`
- `default_template`: currently `corporate`
- `sessions_dir`: default `sessions`
- `providers.*`: model names and API key environment variable names
- `render.*`: label font size and stroke widths for annotation rendering
- `theme.*`: Word doc styling + logo path + brand colors

### `config.py`
- `load_config()` loads and validates `config.yaml`
- it also loads `.env` if present (via `python-dotenv`)
- `Config.get_api_key(provider_name)` resolves the API key from environment variables

Important behavior:
- in browser mode, no API keys are needed.
- in API modes, provider must have the relevant env var set.

---

## 5) Provider behavior details

### 5.1 `providers/base.py`
Defines the provider interface.
Common methods:
- `label_regions_with_title` → labels regions + suggests screen title
- `describe_fields` → returns descriptions for field list
- `procedure_prose` → creates procedure prose from action sequence

It also defines how prompt templates are loaded:
- `load_prompt(template_name)` loads `providers/prompts/{template_name}.txt`
- prompt templates are parameterized using `{placeholder}` replacement

### 5.2 `providers/browser.py` (copy/paste)
Workflow:
1. Write prompt to a prompt file.
2. Open configured editor (default `notepad`).
3. Wait for user to save/paste LLM response into a response file.
4. Parse JSON (supports raw JSON or fenced JSON-like content).

This provider is ideal for reliability when API keys are unavailable.

### 5.3 `providers/anthropic_api.py`
- Uses Anthropic native endpoint: `POST https://api.anthropic.com/v1/messages`
- Sends user content as a single message.
- Extracts `data["content"][0]["text"]`.

### 5.4 `providers/openai_compat.py`
- Generic OpenAI-like endpoint: `/chat/completions`
- Uses httpx with a base URL configured in `config.yaml`

### 5.5 `providers/ollama.py`
- Uses the `ollama` Python package
- Streams response chunks and concatenates them

---

## 6) UI components

### 6.1 `ui/launcher.py`
Main launcher window:
- Configure Brand: opens `StyleConfigDialog`
- Record New Module: calls `run_pipeline()`
- Assemble Client Manual: collects selected sessions and calls `assemble_master_manual()`

### 6.2 `review_ui.py`
Tkinter review editor with:
- left region list (role + label)
- nudge/resize tools
- right canvas with zoom/pan
- editing dialog for label/role/bbox

When leaving each screen, it saves:
- `screen_{i}_final.json`
- updates `screen_{i}_meta.json.screen_name`

---

## 7) How annotated screenshots are generated (`annotate.py`)

`render_annotations()`:
1. Loads screenshot (`screen_i.png`).
2. Loads final regions (`screen_i_final.json`).
3. For each region:
   - draw rectangle outline with role-dependent stroke color
   - create callout bubble with label text wrapped to limited line width
   - place callout bubble using overlap-aware candidate anchors
   - draw curved bezier leader line
4. Alpha composites overlay on the original image
5. Saves `screen_i_annotated.png`

---

## 8) Docx generation (`templates/`)

### 8.1 `templates/base.py`
Shared Word document utilities:
- margins & header/footer setup
- table borders & cell background shading
- TOC field insertion
- callout rendering helper

### 8.2 `templates/corporate/builder.py`
Provides the corporate manual styling:
- cover page with accent bar + optional logo
- revision history table
- module divider pages
- per-screen sections:
  - Heading: `"{index}. {screen_name}"`
  - annotated figure + caption
  - procedure section rendered from structured markers
  - interface dictionary table

The procedure prose renderer expects markers like:
- `PURPOSE:`
- `PREREQUISITES:`
- `STEPS:`
- `EXPECTED OUTCOME:`
- `NOTES:`

These are used to structure headings and lists/bullets in the docx.

---

## 9) Setup / Installation (full)

### Prerequisites
- Python 3.10+ (recommended)
- Microsoft Word (to view resulting `.docx` files). Not required to generate, but recommended.
- Windows browser environment supported by Playwright (Chromium).

### Install dependencies
1. Create/activate a virtual environment (recommended).
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers (needed by Playwright capture):
   ```bash
   playwright install
   ```

### Configure `config.yaml`
Edit `config.yaml`:
- Set `provider` to `browser` or one of:
  - `anthropic`
  - `openai_compat`
  - `ollama`

If using API providers, set environment variables (or create an `.env` file):
- `ANTHROPIC_API_KEY` for Anthropic
- `OPENAI_API_KEY` for openai-compatible providers
- `OLLAMA_API_KEY` for Ollama (optional depending on your endpoint)

### Brand styling
- Use Launcher UI → **Configure Brand...**
- Save settings updates `config.yaml`

---

## 10) Running the project

### Option A: Launch the GUI
Run `ui/launcher.py` (from your Python environment):
- Use the launcher to:
  - record a new module
  - assemble the final master manual

### Option B: Run pipeline directly
Run `main.py`:
- captures latest session
- processes it end-to-end
- assembles module draft docx

Example:
```bash
python main.py
```

---

## 11) Output artifacts (where to find files)

Sessions are stored under:
- `sessions/session_YYYYMMDD_HHMMSS/`

Per screen `N` you will typically find:
- `screen_N.png`
- `screen_N_elements.json`
- `screen_N_meta.json`
- `screen_N_regions.json`
- `screen_N_labeled.json`
- `screen_N_final.json`
- `screen_N_annotated.png`
- `screen_N_content.json`

Per session:
- `module_draft.docx`

Master assembly output:
- `Final_Manuals/Final_Client_Manual.docx`

---

## 12) Troubleshooting

### Playwright browser won’t open
- Ensure Playwright is installed and browsers are installed:
  - `playwright install`

### LLM parsing errors
- Providers expect JSON arrays for labels/field descriptions.
- If your model returns invalid JSON, you may need to:
  - fix the pasted content in browser mode
  - adjust prompts in the prompt templates under `providers/prompts/`

### Annotation callouts overlap regions
- `annotate.py` has an overlap-aware placement algorithm.
- If labels are too large, consider:
  - adjusting `render.label_font_size`
  - adjusting wrap length by editing `_wrap_text` (in annotate.py)

---

## 13) Extending the project

### Add a new document template
Implement a new template builder:
- create a class similar to `CorporateBuilder` that extends `DocumentBuilder`
- update `assemble.py` / `master_assembler.py` if you want to select it by config

### Add a new LLM provider
Implement a new provider class that extends `Provider`:
- required methods: implement a transport to return `_chat(prompt)`
- wire into `main.py`’s `get_provider_instance` and any UI provider mapping

---

## 14) References to prompt templates
LLM prompt templates are in:
- `providers/prompts/describe_fields.txt`
- `providers/prompts/label_regions.txt`
- `providers/prompts/procedure_prose.txt`

These templates are loaded and filled by the provider base layer.

---

## Appendix A: Current dependencies (`requirements.txt`)
From repository:
- playwright
- python-docx
- pyautogui
- loguru
- rich
- ollama

(Other indirect dependencies come from transitive requirements.)

