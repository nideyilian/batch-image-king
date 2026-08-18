# QML Full Parity Design

## Goal

Make the QML workbench the default production UI while preserving every existing QWidget workflow except AI generation and AI provider configuration.

## Approach

Use a compatibility-first hybrid architecture. High-frequency editing remains native QML. Advanced workflows that already have mature QWidget implementations are exposed through a small `LegacyFeatureBridge` owned by the QML engine. The bridge always resolves the active `Document` at invocation time, keeps non-modal windows alive, updates the advanced properties panel when tabs change, and hides AI-specific controls.

This avoids duplicating batch export, clone layout, advanced stroke, preset import/export, binding, size matching, and multi-tab export behavior. Each bridged workflow continues to operate on the same `Document` instances used by QML, so history, serialization, preview, and export remain consistent.

## Components

- `LegacyFeatureBridge`: opens and tracks advanced QWidget tools, adapts QML sessions to legacy document-manager contracts, and provides cross-document layer clipboard commands.
- `WorkspaceSessionViewModel`: adds duplicate, rename, close-other, reorder, and application-close coordination.
- `WorkspaceViewModel`: adds per-document zoom state and the complete legacy blend-mode list.
- `Main.qml`: replaces placeholder menus with real commands, restores the legacy shortcut set, and intercepts application close until every modified document is resolved.
- `qml_main.py`: uses `QApplication`, registers the bridge, and performs the same global resource cleanup as the classic entry.
- `main.py`, `build.py`, and `批图王.spec`: make QML the default packaged entry while retaining `--classic` as a recovery path.

## Error Handling

The bridge reports failures through the existing QML toast channel and never changes the active document implicitly. A legacy dialog is reused when already open for the same document. Application close is a state machine: modified documents are handled one at a time; cancel aborts shutdown; save failures keep the application open.

## Verification

Add contract tests for the bridge, session commands, close coordination, QML menu wiring, default-entry dispatch, and packaging data. Run QML tests, relevant QWidget tests, the full pytest suite, and offscreen screenshots at 1280x760 and 1600x960.
