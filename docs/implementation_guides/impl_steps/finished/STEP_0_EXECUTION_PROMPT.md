# Prompt for Step 0 Execution

Please implement Step 0: Clean Slate Preparation by:

1. First reading: docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md
2. Then reading: docs/implementation_guides/impl_steps/step_0_clean_slate_preparation.md
3. Following the implementation guide exactly as written
4. Running all validation commands before considering the task complete

## Critical Requirements

- **Create the new branch FIRST** before deleting anything
- **Execute deletions exactly as specified** - do not keep any files that should be deleted
- **Create all new directories** including tests/implementation/
- **Ensure testing tools are installed** (pytest, mypy, ruff)
- **Run the pytest validation** and ensure all 4 tests pass
- **Run ckdr** and ensure it passes

## Expected Final State

After completion:
- You should be on branch `architecture-redesign` (not main/master)
- All specified directories and files should be deleted
- New directory structure should exist with __init__.py files
- Test file `tests/implementation/test_step_0_cleanup.py` should pass
- The `ckdr` command should show "All checks passed!"

## What NOT to Do

- Do NOT skip the branch creation
- Do NOT read other documentation files unless specifically referenced
- Do NOT modify the test if it fails - ensure deletions were done correctly
- Do NOT proceed if any validation fails

## Validation Checklist

Before marking this complete, verify:
- [ ] On correct branch: `git branch --show-current` shows `architecture-redesign`
- [ ] All old code deleted: The pytest test has 4 passing tests
- [ ] Code quality passes: `ckdr` shows "All checks passed!"
- [ ] Changes committed with proper message

Report any issues or uncertainties rather than making assumptions.