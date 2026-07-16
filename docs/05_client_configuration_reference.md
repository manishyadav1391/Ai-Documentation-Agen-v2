# Client Configuration Reference

> How to configure a client (branding, style, voice, and content) for DocBot v3.

---

## Overview

Each client is defined by a directory under `clients/<client_key>/` containing four YAML files. DocBot falls back to `clients/_default/` for any file that is missing.

```
clients/
├── _default/           # Fallback defaults
│   ├── manifest.yaml
│   ├── style.yaml
│   ├── voice.yaml
│   └── glossary.yaml
└── ncd/                # Example: NCD client
    ├── manifest.yaml
    ├── style.yaml
    ├── voice.yaml
    ├── glossary.yaml
    └── content/
        └── revision_history.yaml
```

---

## `manifest.yaml`

Defines document metadata and the table of contents structure.

```yaml
# Required fields
client_key: ncd
client_display_name: "National Cooperative Database"
system_name: "NCD State Nodal Portal"
system_acronym: "NCD"
role_name: "State Nodal Officer"
manual_title: "User Manual"
version: "1.0"
document_version: "1.0"

# Optional fields
audience: "State Nodal Officers"
confidentiality: "CONFIDENTIAL"
prepared_by: ""
reviewed_by: ""
approved_by: ""
cover_enabled: false          # false = skip cover page
numbering_mode: continuous    # "continuous" or "module_prefixed"

# Document sections (determines page order and types)
sections:
  - id: revision_history
    type: revision_history
    source: revision_history.yaml     # path relative to content/ or clients/<key>/content/

  - id: toc
    type: table_of_contents

  - id: table_of_figures
    type: table_of_figures

  - id: introduction
    type: prose
    heading: "Introduction"
    source: introduction.md           # plain text or markdown source

  - id: modules
    type: modules                     # Placeholder — replaced by session modules
```

### Numbering Modes

| Value | Effect |
|---|---|
| `continuous` | Figures numbered 1, 2, 3… across the entire document |
| `module_prefixed` | Figures numbered M-1, M-2… per module (e.g., 10-1, 10-2) |

### Section Types

| Type | Source Required? | Description |
|---|---|---|
| `cover` | No | Generated from manifest metadata |
| `revision_history` | Yes (YAML) | Revision history table |
| `table_of_contents` | No | Auto-generated TOC |
| `table_of_figures` | No | Auto-generated (skipped if 0 figures) |
| `table_of_tables` | No | Auto-generated (skipped if 0 tables) |
| `prose` | Yes (`.md` or `.txt`) | Free-text paragraphs |
| `bullet_list` | Yes (YAML list) | Bulleted list of items |
| `icon_table` | Yes (YAML) | Icon + description table |
| `group` | Yes (YAML with subsections) | Nested sections |
| `modules` | No | Replaced by session modules at build time |

---

## `style.yaml`

Controls all visual appearance: fonts, colors, page layout, annotation rendering.

```yaml
# Fonts
body_font: "Calibri"
heading_font: "Calibri"
body_size: 11               # Body text size in pt

# Color palette (hex values without #)
colors:
  primary: "1B365D"         # Dark navy — headings
  secondary: "2E6DA4"       # Medium blue — subheadings, labels
  tertiary: "C0392B"        # Red — note labels
  muted: "7F7F7F"           # Gray — captions, metadata
  accent: "1ABC9C"          # Teal — highlights
  body_text: "2C2C2C"       # Near-black — body text
  table_header_bg: "1B365D"
  table_header_text: "FFFFFF"
  table_alt_row: "F2F7FB"

# Headings (per level)
headings:
  1:
    size_pt: 16
    bold: true
    color: "primary"        # Resolved from colors palette
    before_pt: 18
    after_pt: 6
  2:
    size_pt: 13
    bold: true
    color: "secondary"
    before_pt: 12
    after_pt: 4
  3:
    size_pt: 11
    bold: true
    color: "secondary"
    before_pt: 8
    after_pt: 3

# Page layout
layout:
  body_justified: true
  body_left_indent_twips: 0      # Left indent for body text (0 = none)
  page_break_per_screen: false    # Insert page break after each screen

# Figure settings
figures:
  max_width_inches: 6.2
  max_height_inches: 7.5
  border_enabled: true
  border_color: "AAAAAA"
  border_pt: 0.5
  caption_size_pt: 9
  caption_color: "muted"
  figure_prefix: "Figure"

# Table settings
tables:
  caption_prefix: "Table"
  header_bold: true

# Field details rendering
fields:
  style: "table"            # "table" or "bullets"
  lead_in: "Enter the following details:"

# Numbering format strings
numbering:
  figure_prefix: "Figure"
  table_prefix: "Table"
  figure_format: "{fig}"           # continuous: just the number
  # figure_format: "{module}-{fig}" # module_prefixed: M-N

# Annotation (callout) settings
annotations:
  mode: "callouts"          # "callouts" or "boxes_only"
  callout_font_size: 20
  region_stroke_width: 3
  callout_border_width: 2

# Cover page (when cover_enabled: true)
cover:
  logo_path: "logo.png"    # Relative to client content dir
  bg_color: "1B365D"
  title_color: "FFFFFF"
  subtitle_color: "CCE3F5"

# Footer
footer:
  left_text: "{client_display_name} — {system_name}"
  right_text: "Page {page} of {numpages}"
  font_size: 9
  color: "muted"
```

---

## `voice.yaml`

Controls the LLM writing style injected into generation prompts.

```yaml
# Application name used in generated text
app_name: NCD System

# Tone and style rules (injected as bullet list into the LLM prompt)
tone_rules:
  - Use formal, professional, third-person imperative.
  - Sentences should be concise and direct.
  - Do not use contractions.
  - Field names must match labels shown on screen exactly.
  - Use active voice throughout.
  - Navigation instructions should name the exact menu path.

# Example sentences shown to the LLM for few-shot guidance
examples:
  purpose:
    - "The Login screen enables users to securely access the NCD System using their assigned credentials."
    - "The Dashboard screen displays a summary of registered patients and active cases."
  step:
    - "Click on the Login button to proceed."
    - "Enter the following details:"
    - "  Username — Enter the assigned user login name."
  field:
    - "Facility — Select the health facility from the dropdown list."
    - "Date of Visit — Enter the date of the patient's visit in DD/MM/YYYY format."

# Navigation sentence template
# Variables: {screen_name}, {parent_menu}
navigation_template: "Select {screen_name} option from {parent_menu} as shown in the image below;"

# Notes block appended to each screen's notes section
notes_block: |
  Note: The system requires a stable internet connection. If you experience any issues
  accessing the system, contact your system administrator.
```

---

## `glossary.yaml`

Domain-specific terminology injected into the LLM prompt as context.

```yaml
# Format: "term": "definition"
NCD: "Non-Communicable Disease"
HMIS: "Health Management Information System"
SNO: "State Nodal Officer"
ANM: "Auxiliary Nurse Midwife"
```

Can also be a list-of-dicts format (automatically normalized):

```yaml
- term: NCD
  definition: Non-Communicable Disease
- term: HMIS
  definition: Health Management Information System
```

---

## `content/revision_history.yaml`

Document revision history entries.

```yaml
entries:
  - version: "1.0"
    date: "2026-07-01"
    author: "Documentation Team"
    description: "Initial release"
  - version: "1.1"
    date: "2026-07-15"
    author: "Documentation Team"
    description: "Added NCD Records module"
```

---

## Adding a New Client

```bash
# 1. Create the directory
mkdir clients\my_client

# 2. Copy defaults as a starting point
xcopy clients\_default\* clients\my_client\

# 3. Create content directory
mkdir clients\my_client\content

# 4. Edit the four YAML files
notepad clients\my_client\manifest.yaml
notepad clients\my_client\style.yaml
notepad clients\my_client\voice.yaml
notepad clients\my_client\glossary.yaml

# 5. Create revision history
notepad clients\my_client\content\revision_history.yaml

# 6. Set as active client
# Edit config.yaml: current_client: my_client
```

---

## Fallback Resolution Order

For each file, DocBot checks in this order:

1. `clients/<key>/<file>.yaml`
2. `clients/_default/<file>.yaml`
3. `styles/<key>.yaml` (style only, legacy)
4. `styles/_default.yaml` (style only, legacy)
5. Empty dict `{}` (non-fatal — features requiring the file are skipped)

---

## Color Aliases

Colors in `style.yaml` can reference other color names:

```yaml
colors:
  primary: "1B365D"
  heading_color: "primary"   # Resolved to "1B365D"
```

The resolver in `StyleConfig.get_color()` does one level of alias resolution. Circular aliases are not detected.

---

## Validation

DocBot performs minimal validation of YAML configuration at load time. The following are checked:

- YAML must be parseable (otherwise the file is skipped silently with a warning)
- YAML root must be a dict (lists are rejected)
- `manifest.yaml::sections` must be a list

Field-level validation (e.g., valid color hex values, valid numbering_mode) is not enforced at load time — errors will manifest during document assembly with descriptive error messages.

> [!TIP]
> Use the `validate_deliverable()` function in `docbot.export.qa` after assembly to catch common configuration problems (missing revision history, placeholder strings, etc.).
