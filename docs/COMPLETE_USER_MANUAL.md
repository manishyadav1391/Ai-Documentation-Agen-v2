# DocBot v3 — Complete User Manual

This document is the complete operating guide for the DocBot desktop application. It covers the product features, launcher pages, configuration dialogs, end-to-end workflows, and all supported shortcuts and interactions.

---

## 1. What DocBot does

DocBot is a desktop documentation automation tool for producing professional user manuals from web applications.

It can:

- Launch a browser and record a user journey from a target application.
- Capture screenshots and store screen state for later review.
- Detect page regions and structure from captured screens.
- Generate documentation content such as screen names, purpose text, field descriptions, and procedural steps.
- Let the user refine the generated content in a visual review editor.
- Assemble module manuals and full client manuals as Word documents.
- Apply client branding, style, voice, and glossary rules from YAML-based client profiles.

---

## 2. Feature inventory

### Core features

- Desktop launcher with a multi-page workspace for recording, reviewing, assembling, and managing clients.
- Browser-based recording using Playwright.
- Screen capture with middle-click and session finalization with double middle-click.
- Automatic session processing after recording.
- AI-assisted content generation using multiple providers:
  - Anthropic
  - OpenAI-compatible APIs
  - Ollama
  - Browser copy-paste mode
- Review editor with:
  - screen-level editing
  - step editing
  - field reference editing
  - figure attachment handling
  - region editing and callouts
- Annotation editing on screenshots with movable callouts and resize handles.
- Multi-client support with separate branding, voice, and glossary settings.
- Manual assembly into module-level and master manuals.
- Client settings management from a dedicated settings dialog.
- Session and output management from the launcher.
- Optional QA/validation and output export behavior.

### Supported documentation outputs

- Module manual output as a Word document.
- Master client manual output as a Word document.
- Output files are stored in the Final_Manuals directory.

### Supported configuration areas

- Client identity and document metadata.
- Branding colors, fonts, logo, cover page text, and annotation style.
- Writing voice and guidance rules.
- Glossary terms and definitions.

---

## 3. Launcher overview

The launcher is the main control panel for DocBot. It is the place to:

- choose the active client
- configure provider settings
- start a new recording
- review saved sessions
- manage generated manuals
- manage client profiles

### Top bar

At the top of the launcher you will see:

- Client dropdown: switch the active client profile.
- Settings button: open the provider/API settings dialog.
- Provider status indicator: shows whether the currently selected provider is ready.

### Sidebar pages

The left sidebar contains four main pages.

#### 1. Record

Purpose: Start a new recording session.

What it shows:

- Start URL field
- Module Name field
- Module Number field
- Start Recording button
- A short instruction area explaining capture gestures

How to use it:

1. Enter the start URL of the target web application.
2. Enter a module name.
3. Optionally enter a module number.
4. Click Start Recording.
5. Use middle-click to capture each screen.
6. Use double middle-click to finish the capture session.

#### 2. Recordings

Purpose: Manage saved recording sessions.

What it shows:

- A table/list of sessions with:
  - module number
  - module name
  - captured time
  - screen count
  - review status
- Buttons for:
  - Refresh Sessions
  - Open Review UI
  - Delete Selected
  - Assemble Master Manual

How to use it:

- Select one or more sessions.
- Double-click a row to open the review UI.
- Use the assembly button to create a master manual from selected modules.

#### 3. Manuals

Purpose: Manage generated manual output files.

What it shows:

- A list of generated Word files and PDFs if present.
- Columns for:
  - manual name
  - type
  - date modified
  - size
- Buttons for:
  - Open Manual
  - Open Folder
  - Delete
  - Refresh

How to use it:

- Select a generated manual and open it directly.
- Open the output folder to inspect generated files.

#### 4. Clients

Purpose: Manage client profiles.

What it shows:

- A list of available client profiles.
- Columns for:
  - client key
  - display name
  - version
- Buttons for:
  - Client Settings
  - New Client
  - Open Content Folder
  - Refresh

How to use it:

- Select a client to edit its branding and documentation settings.
- Create a new client profile from the default template.

---

## 4. Settings and configuration dialogs

### Settings dialog: Settings & API Keys

This dialog is opened from the launcher top bar.

It contains fields for:

- Anthropic API key
- OpenAI API key
- Ollama API key
- Show/hide key toggles
- Test Connection buttons
- Save action

Use this dialog when:

- configuring AI provider access
- switching between providers
- testing provider connectivity

### Client Settings dialog

This dialog is opened from the Clients page or when creating a new client.

It has four tabs.

#### Identity (manifest)

Fields:

- Client display name
- System name
- System acronym
- Manual title
- Document version
- Revision prepared by
- Revision reviewed by
- Revision approved by
- Numbering mode

#### Branding (style)

Fields:

- Font family
- Body font size
- Primary color
- Secondary color
- Company logo file
- Cover title text
- Cover subtitle text
- Callout style
- Callout color
- Pointer tail toggle
- Region style
- Connecting line toggle

#### Voice (rules)

Fields:

- App name in prose
- Field styling mode
- Navigation sentence template
- Tone and writing rules (one per line)

#### Glossary terms

Fields:

- Term list
- Definition list
- Add/Update button
- Remove Selected button

---

## 5. Complete workflow

### A. First-time setup

1. Launch the application.
2. Choose or create a client profile.
3. Configure the AI provider and API keys if needed.
4. If no API key is available, select browser copy-paste mode.
5. Save the initial configuration.

### B. Record a module

1. Go to the Record page.
2. Enter the start URL.
3. Enter the module name and optional module number.
4. Click Start Recording.
5. A browser opens and loads the target URL.
6. Navigate the application as needed.
7. Use middle-click to capture screens.
8. Use double middle-click when the module is complete.
9. DocBot processes the session and prepares it for review.

### C. Review and edit the captured content

After recording, the review UI opens.

In the review window you can:

- review each captured screen
- edit the screen name
- edit the purpose statement
- edit navigation text
- edit procedural steps
- edit field reference rows
- manage figure attachments
- edit detected regions
- reposition or resize annotation boxes
- place callout labels manually

The review editor saves changes and supports undo/redo for editing operations.

### D. Assemble a single module manual

Once the content is reviewed:

1. Use the review window or the launcher flow to compile the module.
2. DocBot generates the manual output.
3. The output is saved to the Final_Manuals folder.

### E. Assemble a master manual

To build a master document across several modules:

1. Go to the Recordings page.
2. Select the relevant session modules.
3. Click Assemble Master Manual.
4. DocBot compiles the selected modules in the correct order.
5. The finished manual is saved to the output folder.

---

## 6. Step-by-step user manual

### Step 1: Install and start the application

Requirements:

- Python 3.10 or newer
- A working Windows desktop environment
- A configured AI provider or browser copy-paste mode

Run:

```bash
python ui/launcher.py
```

### Step 2: Choose a client profile

- Use the client dropdown in the launcher.
- Or create a new client from the Clients page.
- New clients are created from the default template and can be styled for a specific organization.

### Step 3: Configure provider settings

- Open Settings.
- Enter the appropriate API key for Anthropic, OpenAI-compatible, or Ollama.
- Use browser mode if you do not want to use an API key.

### Step 4: Record content

- Open the Record page.
- Enter the application URL and module name.
- Start recording.
- Capture screens while you perform the workflow.
- Finish with double middle-click.

### Step 5: Review the generated session

- The review UI opens automatically after processing.
- Edit names, purposes, steps, fields, and annotations until the content is correct.
- Save the session regularly.

### Step 6: Assemble output

- Use the module assembly or master assembly flow.
- Open the resulting Word document from the Manuals page.

---

## 7. Shortcut keys and interaction reference

### Launcher shortcuts

- Ctrl+R: switch to the Record page.
- F5: refresh the active view.
- Delete: delete the currently selected item in the active view.
- Ctrl+, : open the settings dialog.

### Review editor shortcuts

- Ctrl+S: save the current session.
- Ctrl+Left / Ctrl+Right: move to the previous or next screen.
- Arrow keys: nudge the selected region.
- Shift+Arrow keys: resize the selected region.
- Delete: delete the active region.
- Esc: deselect the current region.
- Ctrl+Z: undo the most recent editing action.
- Ctrl+MouseWheel: zoom in or out on the canvas.

### Review editor mouse interactions

- Drag empty canvas area to draw a new region.
- Drag inside a selected region to move it.
- Drag a resize handle to change region size.
- Drag a callout bubble to reposition the callout.
- Right-click a region to open context actions.
- Right-click empty space to pan.

### Recording gestures

- Middle-click: capture the current screen.
- Double middle-click: finish the recording session.

---

## 8. Practical tips

- Use clear module names and numbers so assembled manuals stay ordered correctly.
- Review each screen before assembly; the review editor is where most quality issues are corrected.
- Keep client branding consistent by updating the client settings instead of editing generated documents manually.
- If a provider is not reachable, test the connection from the settings dialog before recording.
- Use browser mode for testing or when API access is unavailable.

---

## 9. Common scenarios

### Recording fails to start

- Check that the browser was installed successfully.
- Confirm the target URL is valid.
- Make sure the selected provider is configured properly.

### Generation output looks weak

- Improve the screen descriptions and step content in review mode.
- Refine client voice and glossary settings.
- Regenerate specific screen content from the review UI if needed.

### Manual does not open

- Check the output folder from the Manuals page.
- Confirm the file was generated successfully.
- Re-run assembly if the earlier output was incomplete.
