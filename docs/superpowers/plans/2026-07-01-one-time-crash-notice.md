# One-Time Crash Notice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a Chinese, one-time explanation on the first launch after an abnormal termination.

**Architecture:** A Qt-free `crash_session` module owns atomic run-state persistence and bounded log parsing. `main.py` starts the session only after the export-worker early exit, schedules the notice after the main window appears, and marks controlled exits clean.

**Tech Stack:** Python 3.11 standard library, PySide6 QMessageBox, unittest.

---

### Task 1: Run-state persistence and one-time consumption

**Files:**
- Create: `app/utils/crash_session.py`
- Create: `tests/test_crash_session.py`

- [ ] Write failing tests for `begin_crash_session()` and `mark_clean_exit()`:
  - prior `running` state returns one notice;
  - after the new session is marked clean, the next begin returns no notice;
  - prior `clean_exit` returns no notice;
  - mismatched session IDs cannot mark another run clean.
- [ ] Run `python -m unittest tests.test_crash_session.CrashSessionStateTests -v` and verify RED.
- [ ] Implement UTF-8 JSON reads, atomic writes, unique session IDs, `running` creation, and guarded `clean_exit` updates.
- [ ] Re-run the state tests and verify GREEN.

### Task 2: Chinese crash-reason extraction

**Files:**
- Modify: `app/utils/crash_session.py`
- Modify: `tests/test_crash_session.py`

- [ ] Write failing parser tests using temporary logs:
  - `Windows fatal exception: access violation` produces the Chinese invalid-memory explanation and `app/ui/layer_panel.py:201`;
  - `MemoryError` produces the Chinese memory explanation;
  - absent logs produce the force-close/power-loss/resource-shortage explanation;
  - technical details include the source log paths.
- [ ] Run `python -m unittest tests.test_crash_session.CrashReasonTests -v` and verify RED.
- [ ] Implement bounded tail reads, fatal/Python error matching, business-frame extraction, timestamp formatting, and `CrashNotice` text fields.
- [ ] Re-run parser tests and verify GREEN.

### Task 3: Startup integration and one-time QMessageBox

**Files:**
- Modify: `main.py`
- Modify: `tests/test_crash_session.py`

- [ ] Write failing source/integration tests asserting:
  - the `--export-worker` branch occurs before crash-session startup;
  - main startup records the exact crash/app log paths;
  - notice display uses title `检测到上次异常退出`;
  - all controlled return paths mark the session clean.
- [ ] Run `python -m unittest tests.test_crash_session.MainCrashNoticeIntegrationTests -v` and verify RED.
- [ ] Add helpers in `main.py` to obtain the file logger path and display a warning QMessageBox with colloquial text plus detailed technical information.
- [ ] Start the crash session after `install_crash_reporter()`, schedule the notice after `window.show()`, and mark normal/handled exits clean.
- [ ] Re-run integration tests and verify GREEN.

### Task 4: Verification and commit

- [ ] Run:

```powershell
python -m unittest tests.test_crash_session tests.test_preview_crash_safety tests.test_export_worker_reliability -v
python -m py_compile main.py app/utils/crash_session.py tests/test_crash_session.py
git diff --check
```

- [ ] Review the exact diff and commit only:

```powershell
git add -- main.py app/utils/crash_session.py tests/test_crash_session.py
git commit -m "feat: show one-time crash reason notice"
```
