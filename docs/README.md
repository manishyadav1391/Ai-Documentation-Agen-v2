# docs/README.md

# DocBot v3 — Documentation Index

This directory contains all technical documentation for the DocBot v3 project.

---

## Documents

| # | File | Description |
|---|---|---|
| 01 | [Codebase Analysis Report](01_codebase_analysis_report.md) | Full Phase 1 analysis: architecture, folder structure, dependency graph, import graph, call graph, runtime flow, data flow, config files, environment variables, third-party integrations, auth flow, background jobs |
| 02 | [Dead Code Report](02_dead_code_report.md) | Phase 2 dead code detection: deprecated shims, orphaned files, duplicates, unused imports, missing dependencies |
| 03 | [Architectural Review](03_architectural_review.md) | Phase 3 architecture review: strengths, critical issues, high/medium/low priority issues, refactoring roadmap |
| 04 | [Module Reference](04_module_reference.md) | API reference for all public modules: docbot.*, manual_builder.*, providers.*, config |
| 05 | [Client Configuration Reference](05_client_configuration_reference.md) | Complete YAML configuration reference: manifest.yaml, style.yaml, voice.yaml, glossary.yaml, revision_history.yaml |
| 06 | [Phase 7 Cleanup Plan](06_phase7_cleanup_plan.md) | Step-by-step implementation plan for removing deprecated shims and dead code |

---

## Root Documentation

| File | Description |
|---|---|
| [README.md](../README.md) | User-facing quick start guide |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Technical architecture reference for contributors |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Developer guide: setup, style, testing, PR checklist |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and notable changes |
