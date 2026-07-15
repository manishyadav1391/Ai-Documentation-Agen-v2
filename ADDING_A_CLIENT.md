# DocBot v3 — Adding a Client Profile

DocBot v3 uses a zero-code per-client data model. All branding, voice rules, page formats, and glossary definitions are externalised.

To create or customize a client profile, add a folder under the `clients/` directory matching the client's acronym or key (e.g., `clients/ncd/`).

---

## 1. Directory Structure

A complete client profile consists of the following structure:

```
clients/
  <client_key>/
    assets/
      banner.png          # Required if using header mode = banner
      logo.png            # Optional logo
    manifest.yaml         # Preamble section layouts & numbering mode
    style.yaml            # Font sizes, color palette, header & layout style
    voice.yaml            # Tone guidelines, prompt voice examples
    glossary.yaml         # Verbatim terminology definitions
```

---

## 2. Configuration Schemas

### `manifest.yaml`
Controls the document preamble layout structure and numbering mode.
```yaml
client_key: ncd
client_display_name: "NCD System"
system_name: "National NCD Portal"
system_acronym: "NCD"
role_name: "User"
manual_title: "User Operations Manual"
version: "1.0"
numbering_mode: continuous  # continuous (e.g. 1, 2, 3) OR module_prefixed (e.g. 10-1, 10-2)

sections:
  - id: cover
    type: cover
    source: cover.yaml
  - id: revision_history
    type: revision_history
    source: revision_history.yaml
  - id: toc
    type: table_of_contents
  - id: table_of_figures
    type: table_of_figures
  - id: modules
    type: modules
```

### `style.yaml`
Controls word formatting, colors, headers, tables, bullets, and layout spacing.
```yaml
page:
  size: A4                       # LETTER or A4
  margin_top_cm: 2.54
  margin_bottom_cm: 2.54
  margin_left_cm: 2.54
  margin_right_cm: 2.54

fonts:
  body_family: Segoe UI
  body_size_pt: 10.5
  heading_family: Segoe UI

colors:
  primary: "1B365D"              # Hex without # prefix
  secondary: "D97706"
  tertiary: "C00000"
  accent: "3B82F6"
  table_header_bg: "1B365D"
  table_header_fg: "FFFFFF"
  table_zebra: "F8FAFC"
  body_text: "333333"
  muted: "828282"

numbering:
  figure_prefix: "Figure"
  figure_format: "{fig}"         # Use "{fig}" for continuous, or "{module}-{fig}" for module prefixed
  table_prefix: "Table"
  table_format: "{tbl}"          # Use "{tbl}" for continuous, or "{module}-{tbl}" for module prefixed

fields:
  style: bullets                 # "bullets" (e.g. Name — utility) OR "table" (4-column Word table)
  bullet_format: "{name} — {utility}"

header:
  mode: banner                   # "banner" (full-width banner image) OR "table" (logo left, title right)
  banner_path: assets/banner.png # Path relative to clients/<client_key>/

revision_history:
  columns:                       # Variable columns lists
    - Version
    - Date
    - Description of Change
    - Author
    - Reviewed By
    - Approved By

annotations:
  mode: boxes_only               # "callouts" (bubbles + lines) OR "boxes_only" (clean boxes) OR "numbered_badges"
```

### `voice.yaml`
Used during LLM generation. Customizes voice guidelines and template structures.
```yaml
app_name: NCD System
tone_rules:
  - Use formal, professional, third-person imperative.
  - Avoid contractions.
  - Keep sentences short.

examples:
  purpose:
    - "The Login screen enables users to access the system securely."
  step:
    - "Click on the Login button."
  field:
    - "Username — Enter the assigned user identifier."

navigation_template: "Select {screen_name} option from main menu;"
```

### `glossary.yaml`
Glossary mapping to enforce terminology rules verbatim.
```yaml
"HMIS": "Health Management Information System"
"ART": "Antiretroviral Therapy"
"NCD": "Non-Communicable Disease"
```
