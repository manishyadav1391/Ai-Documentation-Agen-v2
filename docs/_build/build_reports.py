"""Build docs/DocBot_Testing_Report.docx from UI scenario results and the defect register.

Usage:  python docs/_build/build_reports.py <results_dir> [pytest_summary]
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from manual_lib import Manual, TEXT_W_IN, build_with_page_numbers       # noqa: E402
from report_data import DEFECTS, LIMITATIONS, TC_ISSUES, UNTESTED   # noqa: E402

ROOT = HERE.parent.parent
TODAY = date.today().strftime("%d-%m-%Y")

SCENARIOS = [
    ("s01.json", "First launch and Welcome Wizard (empty workspace)"),
    ("s02.json", "Fresh install; Record validation, Settings, Clients, Recordings, Manuals"),
    ("s03.json", "End-to-end: record AssetDesk, AI generation, Review, Compile Module, Assemble Master Manual"),
    ("s04.json", "Review window layout and documentation screenshots"),
    ("s05.json", "Review window: Apply to All Screens (remove red boxes and callouts from every screen)"),
]


def load_results(results_dir: Path):
    out = []
    for fname, title in SCENARIOS:
        p = results_dir / fname
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append((fname, title, [r for r in data["results"] if r["tc"] != "HARNESS" or r["status"] == "Fail"]))
    return out


def short(s, n=160):
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    results_dir = Path(sys.argv[1])
    pytest_summary = sys.argv[2] if len(sys.argv) > 2 else ""
    scen = load_results(results_dir)
    all_rows = [r for _, _, rows in scen for r in rows]
    passed = sum(r["status"] == "Pass" for r in all_rows)
    out, pdf = build_with_page_numbers(lambda pages: build(scen, all_rows, passed, pytest_summary, pages),
                                       ROOT / "docs" / "DocBot_Testing_Report.docx", results_dir.parent / "pdf")
    print("wrote", out, "pdf:", pdf, f"({passed}/{len(all_rows)} UI checks passed)")


def build(scen, all_rows, passed, pytest_summary, pages):
    m = Manual("Testing Report for DocBot v3")
    m.cover("Silver Touch Technologies Ltd.", "DocBot v3", "Testing and Bug-Fix Report", "1.0",
            date.today().strftime("%d %B %Y"))
    m.revision_history([["1.0", TODAY, "DocBot QA (automated)", "", "", "Audit, fixes and retest of DocBot v3"]])
    m.toc_placeholder()

    # 1 Summary
    m.heading("Summary", 1)
    m.para("This report records the audit, testing and defect fixing of DocBot v3 carried out in November 2026. "
           "The application was exercised through its real launcher window in an isolated workspace, with a scripted "
           "harness that drives the widgets, answers message boxes and captures screenshots. Recording was tested end to "
           "end against a demo web application (AssetDesk) with live AI generation through OpenRouter.")
    m.table(["Item", "Result"], [
        ["UI scenario test cases", f"{passed} of {len(all_rows)} passed"],
        ["Unit tests", pytest_summary or "see section 4"],
        ["Defects fixed", f"{len(DEFECTS)} (register in section 3)"],
        ["Code committed", "No - all changes are left uncommitted for review"],
    ], widths=[2.2, 4.0])
    m.heading("Test Environment", 2)
    for label, text in [
        ("Operating system", "Windows 11 Pro"),
        ("Python", "3.14 (system interpreter), Playwright 1.58 with Chromium 1208"),
        ("Workspace", "Isolated data directory per scenario through the DOCBOT_DATA_DIR override"),
        ("AI provider", "OpenRouter (key from the developer's .env; never printed or captured)"),
        ("Target application", "AssetDesk demo site served locally on 127.0.0.1:8765"),
    ]:
        m.bullet(label, text)

    # 2 Test cases
    m.heading("Test Cases", 1)
    m.para("Each row is one automated check. Issue and Resolution name the defect a check guards against when it was "
           "found during the audit; Retest records the result after all fixes were applied.")
    for fname, title, rows in scen:
        m.heading(title, 2)
        table_rows = []
        for r in rows:
            issue, res = TC_ISSUES.get(r["tc"], ("", ""))
            if r["status"] == "Fail":
                issue = issue or (r.get("issue") or "See actual result")
            table_rows.append([
                r["module"], f"{r['tc']}: {r['case']}", short(r["expected"], 110), short(r["actual"], 140),
                r["status"], issue or "-", res or "-", f"{r['status']} ({TODAY})",
            ])
        t = m.table(["Module", "Test Case", "Expected", "Actual", "Status", "Issue", "Resolution", "Retest"],
                    table_rows, widths=[0.7, 1.05, 0.95, 1.05, 0.45, 0.8, 0.8, 0.5], size=7)

    # 3 Defect register
    m.heading("Bug-Fix Report", 1)
    m.para("Defects found by the audit, grouped by origin: SEC/INF (infrastructure and UI, this round), CFG/UI/MOD "
           "(UI round committed as 'bug fix'), BE (processing, providers, models) and WB (Word builder). Every BE and WB "
           "item was reproduced before it was fixed and has a regression test.")
    m.table(["ID", "Area", "Location", "Defect", "Impact", "Fix", "Verification"],
            [list(d) for d in DEFECTS], widths=[0.45, 0.65, 0.95, 1.25, 0.9, 1.15, 0.92], size=7)
    m.note("The Ollama API key that was committed in secrets.yaml remains in git history. Rotate it with the provider.")

    # 4 Unit tests
    m.heading("Automated Unit Tests", 1)
    m.para(f"Command: python -m pytest -q tests. Result: {pytest_summary or 'not recorded'}.")
    m.table(["Test file", "Covers"], [
        ["test_backend_session.py", "Session load errors and backups (BE-02)"],
        ["test_backend_generator.py", "LLM reply validation, merge safety, max_tokens, module intro (BE-03..09)"],
        ["test_backend_regions_steps.py", "Region detection and fallback step wording (BE-10..13)"],
        ["test_backend_providers_config.py", "Reply parsing, providers, config tolerance, annotation robustness (BE-01, 06, 07, 14..17)"],
        ["test_builder_numbering.py", "Captions, Table of Figures, numbering modes, chapter numbers (WB-01, 03..05)"],
        ["test_builder_content.py", "Placeholder filter, figures, markdown, control characters, bad images (WB-08..12)"],
        ["test_builder_config.py", "Header colours, manifests, notes, locked output, tolerance, layout (WB-02, 06, 07, 13..17)"],
        ["test_ui_infra.py", "First-run seeding, Chromium lookup, Recordings filter, Review styles (INF-02, 04, 06, 07)"],
        ["earlier files", "chat_json, numbering, regions, steps, writer layout, annotation flags (baseline 24 tests)"],
    ], widths=[2.3, 3.9])

    # 5 Known limitations / untested
    m.heading("Known Limitations", 1)
    for s in LIMITATIONS:
        m.bullet(None, s)
    m.heading("Untested Items", 1)
    for s in UNTESTED:
        m.bullet(None, s)

    m.finalize_toc(pages)
    return m


if __name__ == "__main__":
    main()
