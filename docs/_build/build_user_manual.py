"""Build docs/DocBot_User_Manual_v1.1.docx from the documentation screenshots.

Usage:  python docs/_build/build_user_manual.py <manual_shots_dir> <work_dir>
  manual_shots_dir: PNGs + geom.json written by the s04 screenshot scenario
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from manual_lib import Manual, annotate, build_with_page_numbers   # noqa: E402

ROOT = HERE.parent.parent
OUT_DOCX = ROOT / "docs" / "DocBot_User_Manual_v1.1.docx"
IMG_DIR = ROOT / "docs" / "manual_images"

# Callouts per screenshot: (geometry key, bubble text, side, dx, dy)
CALLOUTS = {
    "wizard_1": [("client", "Select active client", "r", 0, 0), ("create", "Create a new client", "r", 0, 0),
                 ("next", "Go to next step", "t", -60, 0)],
    "wizard_2": [("provider", "Choose AI provider", "r", 0, 0), ("key", "Enter API key", "b", 0, 10),
                 ("test", "Check the key", "r", 0, 0), ("next", "Save and continue", "t", -60, 0)],
    "wizard_3": [("finish", "Finish setup", "t", -60, 0)],
    "new_client_prompt": [],
    "record_view": [("client", "Active client", "r", 0, 0), ("dot", "Provider status", "l", 0, 0),
                    ("settings", "AI settings", "l", 0, 45), ("sidebar", "Navigation menu", "r", 30, 160),
                    ("url", "Start address", "b", 250, 70), ("num", "Module number", "r", 0, 0),
                    ("start", "Launch the browser", "r", 0, 0)],
    "record_active": [("counter", "Screens captured", "r", 0, 0), ("stop", "Stop and cancel", "r", 0, 0)],
    "recordings_view": [("tree", "Recorded sessions", "in", 0, 120), ("review", "Edit selected session", "t", 0, 0),
                        ("showall", "Other clients", "t", 0, 0), ("assemble", "Build master manual", "t", -40, 0)],
    "review_main": [("screens", "Screens in session", "r", 0, 120), ("canvas", "Screenshot editor", "in", 320, 420),
                    (("next", "prev", "compile", "finish", "save"), "Move, compile and save", "l", 0, 0),
                    ("preview", "Preview annotations", "b", -60, 230),
                    ("applyall", "Same for all screens", "b", -200, 330),
                    (("name", "purpose", "nav"), "Screen text", "l", 0, 130),
                    (("regen", "regen_steps"), "Ask AI again", "b", 0, 0)],
    "review_steps": [("steps", "Steps for this screen", "l", 0, 0), (("add", "edit", "del"), "Add, edit, delete", "l", 0, 0)],
    "review_regions": [("regions", "Detected regions", "l", 0, 0)],
    "review_region_selected": [(("boxes", "callouts"), "Print boxes / callouts", "b", -120, 230),
                               ("applyall", "Same for all screens", "b", -60, 330),
                               ("label", "Callout text", "l", 0, 0),
                               (("delete", "reset"), "Delete or reset", "l", 0, 0)],
    "region_add_dialog": [("label", "Text shown in callout", "r", 0, 0), ("ok", "Add the callout", "b", 0, 0)],
    "review_preview": [("canvas", "As it will print", "in", 320, 420), ("preview", "Back to editing", "b", -260, 0)],
    "manuals_view": [("tree", "Generated manuals", "in", 0, 120), ("open", "Open in Word", "t", 0, 0),
                     ("delete", "Delete file", "t", 0, 0)],
    "clients_view": [("tree", "Client profiles", "in", 0, 150), ("settings", "Edit profile", "t", 0, 0),
                     ("new", "Add a client", "t", 0, 0)],
    "client_settings_identity": [("display", "Shown on cover", "r", -40, 0), ("version", "Document version", "r", 0, 0),
                                 ("numbering", "Figure numbering", "r", 0, 0), ("save", "Save profile", "t", -40, 0)],
    "client_settings_branding": [("font", "Body font", "r", 0, 0), ("primary", "Brand colour", "r", 40, 0),
                                 ("logo", "Pick logo file", "r", 0, 0)],
    "client_settings_voice": [],
    "client_settings_glossary": [],
    "settings_openrouter": [("provider", "Active provider", "r", 0, 0), ("test", "Test the key", "l", 0, 0),
                            ("save", "Save settings", "l", 0, 0)],
    "settings_anthropic": [("key", "Anthropic key", "b", 0, 0), ("tokens", "Reply length limit", "b", 0, 0)],
}


def prepare_images(shots: Path) -> dict:
    geom = json.loads((shots / "geom.json").read_text(encoding="utf-8"))
    out = {}
    for name, marks in CALLOUTS.items():
        src = shots / f"{name}.png"
        if not src.exists():
            print("[warn] missing shot", name)
            continue
        g = geom.get(name, {})
        spec = []
        for key, text, side, dx, dy in marks:
            keys = key if isinstance(key, tuple) else (key,)
            boxes = [g[k] for k in keys if k in g and g[k][2] > 4 and g[k][3] > 4]
            if not boxes:
                continue
            x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
            x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
            spec.append(dict(box=[x0, y0, x1 - x0, y1 - y0], text=text, side=side, dx=dx, dy=dy))
        out[name] = annotate(src, IMG_DIR / f"{name}.png", spec)
    # unannotated message-box shots
    return out


def build(img: dict, pages: dict) -> Manual:
    m = Manual("User Manual for DocBot v3")
    m.cover("Silver Touch Technologies Ltd.", "DocBot v3", "User Manual", "1.1", date.today().strftime("%d %B %Y"))
    m.revision_history([
        ["1.0", "16-07-2026", "DocBot Team", "", "", "Initial text-only manual"],
        ["1.1", date.today().strftime("%d-%m-%Y"), "DocBot Team", "", "",
         "Rewritten with annotated screenshots; covers client filter, validation and fixes of Nov 2026"],
    ])
    m.toc_placeholder()

    def fig(name, alt=""):
        if name in img:
            return m.figure(img[name], alt=alt)
        m.para(f"[Screenshot '{name}' not available]")
        return ""

    # ------------------------------------------------------------------ 1
    m.heading("Introduction", 1)
    m.para("DocBot is a desktop application that produces Word user manuals for web applications. You open the target "
           "application in a browser controlled by DocBot, capture each screen with a mouse gesture, and DocBot asks an AI "
           "model to describe every screen. You then review the screenshots and text, and DocBot assembles a formatted "
           "manual with a cover page, revision history, table of contents, annotated figures and numbered captions.")
    m.heading("Who This Manual Is For", 2)
    m.para("This manual is for documentation writers and business analysts who prepare user manuals. No programming "
           "knowledge is needed. Each chapter describes one screen of DocBot, in the order you normally use them.")
    m.heading("Workflow at a Glance", 2)
    m.steps([
        "**Set up** a client profile (branding, document details) and an AI provider. See chapters 2, 8 and 9.",
        "**Record** a module: open the start page, capture screens with a middle-click. See chapter 3.",
        "**Review** the captured screens: correct names, purpose text, steps and callout boxes. See chapter 4.",
        "**Assemble** one or more modules into the master manual. See chapter 5.",
        "**Open** the finished manual from the Manuals page. See chapter 6.",
    ])
    m.heading("Main Window", 2)
    m.para("The main window has a top bar, a navigation menu on the left, the working area and a status bar.")
    m.bullet("Client", "the client profile whose branding and front matter are used.", "Drop-down list")
    m.bullet("Provider status", "green when the configured AI provider is ready, red when a key or endpoint is missing.", "Indicator")
    m.bullet("Settings", "opens the AI provider settings and API keys.", "Button")
    m.bullet("Navigation menu", "switches between Record, Recordings, Manuals and Clients.", "Buttons")
    m.bullet("Status bar", "shows the active client, the provider and the current activity.", "Label")

    # ------------------------------------------------------------------ 2
    m.heading("Getting Started", 1)
    m.para("Start DocBot from the Start menu shortcut or by running **DocBot.exe**. Only one copy can run at a time; "
           "if DocBot is already open, a message tells you so.")
    m.heading("Welcome Wizard", 2)
    m.para("The first time DocBot starts on a computer, the Welcome Wizard guides you through three steps.")
    m.heading("Step 1: Choose Active Client Profile", 3)
    fig("wizard_1", "Welcome Wizard step 1")
    m.bullet("Active Client", "the profile used for new recordings and manuals.", "Drop-down list")
    m.bullet("Create New Client...", "creates a profile when none exists yet (see 2.2).", "Button")
    m.bullet("Next >", "continues to step 2.", "Button")
    m.note("You cannot continue without a client profile. If the list is empty, click Create New Client... first.")
    m.heading("Step 2: Configure AI Provider", 3)
    fig("wizard_2", "Welcome Wizard step 2")
    m.bullet("Provider", "browser (copy and paste, no key needed), anthropic, openai_compat, openrouter or ollama.", "Drop-down list")
    m.bullet("API Key", "the key issued by the provider. Characters are hidden unless Show is ticked.", "Text box")
    m.bullet("Test Connection", "sends a short request to check the key.", "Button")
    m.bullet("< Back / Next >", "move between steps. Next saves the provider and key.", "Buttons")
    m.note("Leaving the key empty keeps any key that is already stored or supplied through the .env file.")
    m.heading("Step 3: Ready to Document", 3)
    fig("wizard_3", "Welcome Wizard step 3")
    m.para("The last step summarises how to record a manual. Click **Finish** to open the main window. The wizard is "
           "not shown again.")
    m.heading("Creating a Client Profile", 2)
    m.para("Navigation: **Clients > New Client...** or **Welcome Wizard > Create New Client...**")
    fig("new_client_prompt", "New client key prompt")
    m.steps([
        "Enter a short key, for example **ncb**. Use letters, digits and underscores; up to 40 characters.",
        "Click **OK**. DocBot copies the default template and confirms the new profile.",
        "The Client Settings window opens. Fill in the details described in chapter 8 and click **Save Settings**.",
    ])
    m.note("A key that is already in use, or that contains spaces or other symbols, is rejected with a message.")

    # ------------------------------------------------------------------ 3
    m.heading("Record", 1)
    m.para("Navigation: **Record** in the navigation menu. This is the page shown when DocBot starts. Use it to "
           "record one module, which is one chapter of the final manual.")
    fig("record_view", "Record page")
    m.heading("Fields", 2)
    m.bullet("Start URL", "address of the first page to open. Must start with http:// or https://.", "Text box")
    m.bullet("Module Name", "chapter title for this module, for example Asset Management.", "Text box")
    m.bullet("Module Number", "chapter order in the master manual; a whole number of 1 or more, or blank.", "Text box")
    m.bullet("Start Recording", "checks the fields, then opens the recording browser.", "Button")
    m.heading("Recording a Module", 2)
    m.steps([
        "Select the client in the top bar.",
        "Enter the Start URL, Module Name and Module Number, then click **Start Recording**.",
        "In the browser that opens, log in and move to the first screen you want to document.",
        "**Middle-click** anywhere on the page to capture it. The counter in DocBot increases.",
        "Continue through the application, capturing each screen.",
        "**Double middle-click** to finish. DocBot processes the screens and generates the text with AI.",
        "The Review window opens (chapter 4). When you close it, DocBot confirms that the module was recorded.",
    ])
    fig("record_active", "Recording in progress")
    m.heading("Capture Gestures", 2)
    m.table(["Gesture", "Keyboard alternative", "Result"], [
        ["Middle-click", "Alt+C or Ctrl+Shift+1", "Capture the visible part of the page"],
        ["Ctrl + middle-click", "Alt+F or Ctrl+Shift+2", "Capture the full scrolling page"],
        ["Shift + middle-click", "Alt+S or Ctrl+Shift+3", "Capture the current state (for example an open drop-down)"],
        ["Double middle-click", "Alt+Q or Ctrl+Shift+4", "Finish the recording"],
    ], widths=[1.6, 1.9, 2.7])
    m.bullet("Stop & Cancel", "ends the recording without saving. The button shows Stopping... until the browser has closed.", "Button")
    m.note("Closing the browser window also ends the session. If no screen was captured, DocBot shows Nothing Recorded "
           "and no module is created.")

    # ------------------------------------------------------------------ 4
    m.heading("Review Window", 1)
    m.para("The Review window opens automatically after a recording and from **Recordings > Open Review UI**. Use it "
           "to check every screen before it goes into the manual.")
    m.heading("Layout", 2)
    fig("review_main", "Review window")
    m.para("Lists every captured screen. Click a screen, or use **Prev** and **Next** (Ctrl+Left / Ctrl+Right), to move between them.", bold_lead="Screens in Session:")
    m.para("Shows the screenshot with its red boxes and callouts.", bold_lead="Screenshot editor:")
    m.bullet(None, "Drag an empty area to draw a new region box.")
    m.bullet(None, "Drag a box to move it; drag its handles to resize it.")
    m.bullet(None, "Drag a callout bubble to reposition it.")
    m.bullet("Zoom / Fit / 100% / 200%", "change the magnification.", "Buttons")
    m.bullet("Red boxes / Callouts", "choose whether boxes and bubbles are printed for this screen.", "Check boxes")
    m.bullet("Default", "returns this screen to the client's standard setting.", "Button")
    m.bullet("Apply to All Screens", "copies the current Red boxes / Callouts choice to every screen in the session. "
             "To print clean screenshots throughout, untick both check boxes and click this button.", "Button")
    m.para("The right-hand panel holds the text for the selected screen.", bold_lead="Screen Documentation:")
    m.bullet("Screen Name", "heading used for this screen in the manual.", "Text box")
    m.bullet("Screen Purpose", "introductory paragraph.", "Text area")
    m.bullet("Navigation path", "sentence describing how to reach the screen.", "Text box")
    m.bullet("Regenerate All Content / Regenerate Steps Only", "ask the AI to write the text again, optionally with your guidance.", "Buttons")
    m.heading("User Steps", 2)
    fig("review_steps", "User Steps tab")
    m.para("The steps describe what the user does on the screen. Select a step, then use **Add Step**, **Edit Step**, "
           "**Delete Step**, **Move Up** or **Move Down**.")
    m.heading("Region Structure", 2)
    fig("review_regions", "Region Structure tab")
    m.para("Lists the regions detected on the screen. Each region becomes a red box with a callout. Double-click a "
           "region to change its label, position or size; width and height must be at least 8 pixels.")

    m.heading("Adding and Removing Callouts", 2)
    m.para("Every region on a screenshot is printed as a **red box** around the area and a **callout** (the white "
           "speech bubble with red text) that names it. The callout text is the region's label. You can add your own "
           "callouts, change or move them, remove single callouts, or print a screen, or the whole module, without them. "
           "All of this is done in **Edit mode** (the Preview button shows Preview, not Edit Mode).")
    fig("review_region_selected", "A selected region with its controls")
    m.heading("Add a Callout", 3)
    m.steps([
        "Move to the screen with **Prev** / **Next** or by clicking it in **Screens in Session**.",
        "Drag with the left mouse button across an **empty area** of the screenshot to draw a box around the part you "
        "want to point out.",
        "In the **Add Region Details** window, type the **Region Label** (this is the text shown in the callout) and "
        "choose the **Semantic Role**.",
        "Click **Add Region**. The red box and its callout appear on the screenshot.",
    ])
    fig("region_add_dialog", "Add Region Details window")
    m.note("Click Cancel in the Add Region Details window to discard the box you have just drawn.")
    m.heading("Change or Move a Callout", 3)
    m.bullet("Change the text", "click the box, then edit **Region Label** in the **Region Structure** tab; or "
             "double-click the box and change the label in **Edit Region Details**.")
    m.bullet("Move the box", "drag inside the box, or use the arrow keys.")
    m.bullet("Resize the box", "drag one of the eight handles of the selected box, or use Shift + arrow keys.")
    m.bullet("Move the bubble", "drag the callout bubble to any position. **Reset Callout to Auto** (or right-click the "
             "bubble) puts it back to automatic placement.")
    m.heading("Remove a Callout", 3)
    m.para("To remove one callout together with its red box:")
    m.steps([
        "Click the box (or its bubble) on the screenshot, or select it in the **Region Structure** list.",
        "Press the **Delete** key, click **Delete Region**, or right-click the box and choose **Delete region**.",
    ])
    m.note("Press Ctrl+Z to undo a deletion, move or resize.")
    m.heading("Show or Hide Callouts and Red Boxes", 3)
    m.para("The **In manual** check boxes above the screenshot decide what is printed for the current screen, without "
           "deleting any region:")
    m.table(["To do this", "Do this"], [
        ["Print red boxes and callouts (normal)", "Tick **Red boxes** and **Callouts**."],
        ["Print red boxes only, no callout bubbles", "Tick **Red boxes**, untick **Callouts**."],
        ["Print a clean screenshot on this screen", "Untick **Red boxes** and **Callouts**."],
        ["Remove callouts and red boxes from **every** screen of the module",
         "Untick both check boxes, click **Apply to All Screens**, click **Yes**, then click **Save Session**."],
        ["Put callouts back on every screen", "Tick both check boxes, click **Apply to All Screens**, **Yes**, **Save Session**."],
        ["Return one screen to the client's standard setting", "Click **Default**."],
    ], widths=[2.9, 3.3])
    m.para("Use **Preview** to check the result before saving. Screens printed without annotations are marked **[no annotations]** in "
           "the Screens in Session list.")
    m.note("Hiding callouts does not delete the regions, so you can switch them back on at any time. Click Save Session "
           "(or Save & Finish) so the images in the manual are updated.")

    m.heading("Preview and Saving", 2)
    fig("review_preview", "Preview mode")
    m.bullet("Preview", "shows the screenshot exactly as it will appear in the manual. Click Edit Mode to return.", "Button")
    m.bullet("Save Session (Ctrl+S)", "saves all screens and re-renders every annotated image.", "Button")
    m.bullet("Compile Module", "builds a draft Word file for this module only and saves it in Final_Manuals.", "Button")
    m.bullet("Save & Finish", "saves and closes the window; the recording then completes.", "Button")
    m.note("Changes made on any screen are saved together, so you can edit several screens before saving. "
           "After Apply to All Screens, click Save Session so that every image is updated.")

    # ------------------------------------------------------------------ 5
    m.heading("Recordings", 1)
    m.para("Navigation: **Recordings** in the navigation menu. The page lists recorded modules and builds the master manual.")
    fig("recordings_view", "Recordings page")
    m.bullet("No. / Module Name / Client / Captured Time / Screens / Status", "details of each session. Status is Reviewed when every screen has been reviewed, otherwise Draft.", "Table")
    m.bullet("Refresh Sessions", "reloads the list.", "Button")
    m.bullet("Open Review UI", "opens the selected session in the Review window. Double-clicking a row does the same.", "Button")
    m.bullet("Delete Selected", "deletes the selected sessions after confirmation.", "Button")
    m.bullet("Show all clients", "also lists sessions recorded for other clients. Off by default.", "Check box")
    m.bullet("Assemble Master Manual", "builds one manual from the selected sessions.", "Button")
    m.heading("Assembling the Master Manual", 2)
    m.steps([
        "Select the modules to include (Ctrl+click for several).",
        "Click **Assemble Master Manual**. DocBot lists the modules in module-number order; click **Yes** to continue.",
        "When the build finishes, DocBot shows where the file was saved and opens the Manuals page.",
    ])
    m.note("If a selected session belongs to another client, DocBot asks before continuing, because the manual uses the "
           "branding and front matter of the current client.")

    # ------------------------------------------------------------------ 6
    m.heading("Manuals", 1)
    m.para("Navigation: **Manuals** in the navigation menu. Lists the Word and PDF files in the Final_Manuals folder.")
    fig("manuals_view", "Manuals page")
    m.bullet("Manual Name / Type / Date Modified / Size", "Type is Module Manual for drafts from Compile Module and Final Manual for assembled manuals.", "Table")
    m.bullet("Open Manual", "opens the selected file in Word.", "Button")
    m.bullet("Open Folder", "opens the Final_Manuals folder.", "Button")
    m.bullet("Delete", "deletes the selected file after confirmation.", "Button")
    m.bullet("Refresh", "reloads the list.", "Button")
    m.note("When the manual opens in Word, accept the prompt to update fields so that the table of contents and page "
           "numbers are refreshed.")

    # ------------------------------------------------------------------ 7
    m.heading("Clients", 1)
    m.para("Navigation: **Clients** in the navigation menu. Lists the client profiles in the workspace.")
    fig("clients_view", "Clients page")
    m.bullet("Client Key / Display Name / Version", "profile details.", "Table")
    m.bullet("Client Settings...", "opens the selected profile for editing (chapter 8).", "Button")
    m.bullet("New Client...", "creates a profile (section 2.2).", "Button")
    m.bullet("Open Content Folder", "opens the profile's folder with its manifest, style and content files.", "Button")
    m.bullet("Refresh", "reloads the list.", "Button")

    # ------------------------------------------------------------------ 8
    m.heading("Client Settings", 1)
    m.para("Navigation: **Clients > select a client > Client Settings...** The settings are grouped in four tabs. "
           "Click **Save Settings** to store them; DocBot checks the values first.")
    m.heading("Identity", 2)
    fig("client_settings_identity", "Client Settings - Identity")
    for lbl, d in [("Client Display Name", "organisation name on the cover. Required."),
                   ("System Name / System Acronym", "name of the documented application."),
                   ("Manual Title", "title on the cover and in the header."),
                   ("Document Version", "version shown on the cover. Required."),
                   ("Revision Prepared / Reviewed / Approved By", "names for the Revision History table."),
                   ("Numbering Mode", "module_prefixed (Figure 3-1) or continuous (Figure 12).")]:
        m.bullet(lbl, d, "Drop-down list" if lbl == "Numbering Mode" else "Text box")
    m.heading("Branding", 2)
    fig("client_settings_branding", "Client Settings - Branding")
    for lbl, d, c in [("Font Family / Body Font Size", "body text font; size between 6 and 36 points.", "Drop-down list, Spin box"),
                      ("Primary / Secondary Color", "six-digit hex colours such as #1B365D. Pick... opens a colour chooser.", "Text box"),
                      ("Company Logo File", "image used on the cover and header. Browse... selects the file.", "Text box"),
                      ("Cover Title / Subtitle text", "extra lines on the cover page.", "Text box"),
                      ("Callout Style, Callout color, Pointer tail, Region style, Connecting line", "appearance of red boxes and callouts in the screenshots.", "Drop-down lists, Check boxes")]:
        m.bullet(lbl, d, c)
    m.heading("Voice", 2)
    fig("client_settings_voice", "Client Settings - Voice")
    m.bullet("App Name in Prose", "how the application is named in the generated text.", "Text box")
    m.bullet("Navigation Sentence", "template for navigation paths.", "Text box")
    m.bullet("Tone/Writing Rules", "one rule per line; passed to the AI with every screen.", "Text area")
    m.heading("Glossary", 2)
    fig("client_settings_glossary", "Client Settings - Glossary")
    m.para("Terms and acronyms used by the AI and printed in the glossary. Enter a **Term** and **Definition**, then "
           "click **Add / Update**; select a row and click **Remove Selected** to delete it.")

    # ------------------------------------------------------------------ 9
    m.heading("Settings", 1)
    m.para("Navigation: **Settings** in the top bar. Choose the AI provider and enter its API key and model.")
    fig("settings_openrouter", "Settings - OpenRouter")
    m.bullet("Active AI provider", "the provider used for generation.", "Drop-down list")
    m.bullet("Provider tabs", "Anthropic, OpenAI Compat, Ollama and OpenRouter, each with its own key and options.", "Tabs")
    m.bullet("API Key", "hidden by default; tick Show to see it.", "Text box")
    m.bullet("Model / Max Tokens", "model name and the maximum length of each AI reply (a whole number above zero).", "Text boxes")
    m.bullet("Base URL / Host URL", "for OpenAI-compatible and Ollama servers; must start with http:// or https://.", "Text box")
    m.bullet("Test Connection", "checks the key and model with a short request.", "Button")
    m.bullet("Save Settings", "validates and saves. Keys are stored in secrets.yaml in the workspace.", "Button")
    fig("settings_anthropic", "Settings - Anthropic")
    m.note("Keys for a local Ollama or OpenAI-compatible server on your own computer or network are optional.")

    # ------------------------------------------------------------------ 10
    m.heading("Messages and Troubleshooting", 1)
    m.para("The table lists the messages you may see and what to do.")
    m.table(["Message", "Cause", "What to do"], [
        ["Client Required", "No client profile selected in the Welcome Wizard.", "Click Create New Client... first."],
        ["Start URL must start with http:// or https://", "Address typed without the scheme.", "Add http:// or https://."],
        ["Module Number must be 1 or greater (or blank)", "0, a negative number or text entered.", "Enter a whole number from 1, or leave it blank."],
        ["Browser Download Required", "The recording browser is not installed.", "Click Yes to download it once (about 150 MB)."],
        ["Nothing Recorded", "The session ended before any capture.", "Middle-click on each page before finishing."],
        ["Different Client", "Selected sessions belong to another client.", "Switch client, or confirm to continue."],
        ["Session Could Not Be Opened", "session.json is damaged. A backup named session.json.corrupt is kept.", "Restore the session folder or record again."],
        ["Connection Failed", "Wrong key, model or address, or no internet access.", "Check the Settings tab for the provider and test again."],
        ["Another copy of DocBot is already running", "DocBot is already open.", "Switch to the open window."],
    ], widths=[2.0, 2.1, 2.1])
    m.note("If AI generation fails for a screen, DocBot keeps the screen with a short note so that you can write or "
           "regenerate the text in the Review window.")

    m.finalize_toc(pages)
    return m


def main():
    shots = Path(sys.argv[1])
    work = Path(sys.argv[2])
    img = prepare_images(shots)
    out, pdf = build_with_page_numbers(lambda pages: build(img, pages), OUT_DOCX, work)
    print("wrote", out, "pdf:", pdf)


if __name__ == "__main__":
    main()
