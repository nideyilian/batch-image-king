# AI素材工坊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version layer-level AI image generation flow that uses global API settings, saves local assets, optionally performs lightweight cutout/segmentation, and writes the output folder back to the selected image layer.

**Architecture:** Keep AI generation outside the existing export pipeline. Add a pure service for API response parsing and local image processing, use the toolbar dialog only for shared API settings, and run generation from each image layer's property panel so the result updates that layer's `image_source`.

**Tech Stack:** Python stdlib `urllib`, Pillow, NumPy, OpenCV, PySide6, `unittest`.

---

### File Structure

- Create `app/services/ai_asset_service.py`: API request/response parsing, image downloading, asset folder creation, cutout, segmentation, metadata.
- Create `app/services/ai_provider_config.py`: persistent multi-interface profiles with endpoints, authentication mode, model field, and model IDs.
- Create `app/ui/ai_asset_studio_dialog.py`: non-modal PySide6 dialog for managing interface profiles, manually adding models, and fetching model lists.
- Modify `app/ui/layer_properties.py`: add the per-layer `AI生图` module and background generation worker.
- Modify `app/main_window.py`: add toolbar/menu action for global API settings.
- Create `tests/test_ai_asset_service.py`: pure service tests that do not require PySide6 or network.

### Task 1: Service Tests

- [ ] Create `tests/test_ai_asset_service.py` with tests for extracting image sources from OpenAI-style responses, creating safe asset directories, and segmenting a black-background image into components.

Run:

```powershell
python -m unittest tests.test_ai_asset_service -v
```

Expected before implementation: import failure for `app.services.ai_asset_service`.

### Task 2: Service Implementation

- [ ] Create `app/services/ai_asset_service.py`.
- [ ] Implement `AIAssetRequest`, `AIAssetResult`, `AIAssetService.extract_image_sources()`, `create_asset_workspace()`, `process_local_image()`, and `generate_assets()`.
- [ ] Support common response shapes: `{"data":[{"url":"..."},{"b64_json":"..."}]}`, `{"url":"..."}`, `{"image_url":"..."}`, `{"images":[...]}`.
- [ ] Save outputs under app data `批图王/ai_assets`.

Run:

```powershell
python -m unittest tests.test_ai_asset_service -v
```

Expected after implementation: all service tests pass.

### Task 3: UI Dialog

- [ ] Create `app/ui/ai_asset_studio_dialog.py`.
- [ ] Add fields for Base URL, Endpoint, API Key, model, prompt, negative prompt, count, size, group name, and processing mode.
- [ ] Add generate button, import button, progress/status label, and result list.
- [ ] Run generation in `QThreadPool.globalInstance().start(QRunnable)`.
- [ ] Store local settings in `QSettings("批图王", "AIAssetStudio")`.
- [ ] Import selected output folder by calling `document.add_layer(name, 0, 0, width, height, folder, False, True)`.

Verification:

```powershell
python -m py_compile app/ui/ai_asset_studio_dialog.py
```

### Task 4: Main Window Integration

- [ ] Modify `app/main_window.py` to add `AI素材` action near add-layer actions.
- [ ] Add the action to the toolbar and layer menu.
- [ ] Add `open_ai_asset_studio()` that opens or raises one dialog per main window.

Verification:

```powershell
python -m py_compile app/main_window.py
```

### Task 5: Final Verification

- [ ] Run service tests.
- [ ] Compile changed Python files.
- [ ] Check git diff for only intended files.
- [ ] Commit only files changed for this feature.
