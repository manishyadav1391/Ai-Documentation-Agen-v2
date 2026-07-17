# DocBot v3 User Guide

Welcome to **DocBot v3**! This guide is designed for technical writers and documentation specialists to quickly capture, refine, and compile professional, fully-branded software user manuals.

---

## Table of Contents
1. [Recording a Session](#1-recording-a-session)
2. [Reviewing and Editing Content](#2-reviewing-and-editing-content)
3. [Managing Client Profiles and Styles](#3-managing-client-profiles-and-styles)
4. [Assembling the Final Manual](#4-assembling-the-final-manual)
5. [Troubleshooting and Common Failure Cases](#5-troubleshooting-and-common-failure-cases)

---

## 1. Recording a Session

To document a feature or module:
1. **Launch a Recording**: On the DocBot Control Launcher:
   - Enter the **Start URL** of the web page where your capture begins.
   - Specify the **Module Name** (e.g., "User Profile Management").
   - Click **Record New Module**.
2. **Browser Recording Mode**:
   - A browser window will open. Perform the clicks and actions you wish to document.
   - **Important**: To capture a screen state and draw attention to elements:
     - Perform a normal action, and DocBot will automatically log user events.
     - Playwright monitors the pages. If you wish to capture multi-tab activities, DocBot will automatically track events across all open tabs.
3. **Finish Recording**:
   - Close the browser window to complete the capture run.
   - DocBot will automatically process layout structures and elements, and save the session.

---

## 2. Reviewing and Editing Content

Once a session is recorded, it is loaded in the **Review UI**:
- **Screens List**: The left panel lists all captured screens in order.
- **Form Fields (Middle Panel)**:
  - **Screen Name**: Give the screen a descriptive name.
  - **Purpose**: Add a 1-2 sentence description explaining the screen's role.
  - **Steps List**: Bulleted procedural steps. You can double-click any step to refine it, or click **Regenerate Steps** to have AI rewrite them cleanly.
  - **Notes / Callouts**: Critical tips or warnings.
- **Visual Annotations (Right Panel)**:
  - You can draw attention callouts by clicking on any element in the screenshot.
  - Adjust callout coordinates manually if the candidate scoring needs adjustment.
- **AI Regeneration**:
  - Click **Regenerate Page** to re-compile layout, screenshots, and steps with LLM suggestions.

---

## 3. Managing Client Profiles and Styles

DocBot is multi-tenant and supports completely customized branding:
1. **Client Selector**:
   - Select a client key from the dropdown (e.g. `ncb`) to apply branding.
   - Use **New Client...** to create a new profile from defaults.
2. **Settings Panel**: Click **Branding Settings...** (⚙ icon) to modify:
   - **Identity**: System name, author signatures, document version.
   - **Branding**: Font face, font size, primary/secondary colors, and logo file path (which is automatically copied into the client assets to ensure portability).
   - **Writing Voice**: LLM instruction guidelines and tone rules.
   - **Glossary**: Define custom terms and definitions to be automatically included in compiled manuals.

---

## 4. Assembling the Final Manual

To build a professional user manual:
1. Select one or more modules in the launcher session list.
2. Click **Assemble Master Manual**.
3. DocBot will stitch all selected modules together, insert standard table of contents, glossary, revision histories, and export a `.docx` document to the `Final_Manuals/` directory.

---

## 5. Troubleshooting and Common Failure Cases

### Unresponsive Playwright Browser
- **Symptom**: Clicking "Record New Module" shows an error or nothing happens.
- **Cause**: Playwright browser driver was not installed or is corrupted.
- **Fix**: Check your internet connection. DocBot installs browser files on first run. If this fails, configure a custom browser path under the settings panel pointing to Chrome or Microsoft Edge.

### PDF Conversion Failure (LibreOffice missing)
- **Symptom**: The `.docx` builds successfully but no PDF is generated.
- **Cause**: LibreOffice `soffice` is not installed or not in system PATH.
- **Fix**: DocBot builds Word documents. Converting to PDF is an optional visual QA feature. Install LibreOffice or turn on the `skip_libreoffice_qa` flag inside config to skip the PDF pass.

### Unhandled Exception popup
- **Symptom**: A dialog says "Something went wrong" and points to a log file.
- **Cause**: An unexpected code exception occurred.
- **Fix**: Open the logs directory in `%LOCALAPPDATA%\DocBot\logs` and send the traceback inside `docbot.log` to support.
