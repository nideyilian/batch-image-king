# Dialog A2 Phase 2 Plan

## Goal

Unify the remaining visible modal dialogs from the user's screenshots under the Dialog A2 system:

- `AddTextLayerDialog` (`文字突出`)
- `LayerBindingManagerDialog` (`图层绑定管理器`)
- `LayerSizeMatchDialog` (`图层大小匹配管理器`)

## Assumptions

- Keep business behavior and model calls unchanged.
- Do not touch export dialogs in this phase because the workspace already contains unrelated dirty edits there.
- Use `DialogA2` tokens as the source of truth for margins, cards, control heights, footer buttons, and typography.

## Steps

1. Add focused regression tests for Dialog A2 ownership, card roles, footer roles, button sizing, and removal of the old text-dialog rail.
   Verify: `python -m unittest discover -s tests -p "test_dialog_a2_phase2.py" -v`
2. Refactor the text creation dialog into a title + content card + core parameter card + footer structure.
   Verify: tests pass and `get_text_layer()` still reads the same fields.
3. Refactor the binding and size-match managers into consistent two-column manager layouts with stable card backgrounds and footer buttons.
   Verify: tests pass with fake documents/managers.
4. Update the Dialog A2 spec with Phase 2 rules for creation dialogs and manager dialogs.
   Verify: doc mentions the covered dialogs and no longer describes them as deferred.
5. Run focused checks and commit only files changed for this phase.
