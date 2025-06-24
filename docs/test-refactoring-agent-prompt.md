# Test Refactoring Agent Prompt

## Task Overview
You are continuing a test refactoring effort for the dr_exp project. The goal is to reorganize tests from step-based naming (test_step_X_Y.py) to a functional structure organized by test type and component.

## Your Mission
1. Open and read `/docs/test-refactoring-plan.md`
2. Find the first commit marked as "TODO"
3. Implement that commit exactly as specified
4. Mark the commit as "DONE" in the plan document
5. Commit your changes with the exact commit message specified
6. Continue with the next TODO commit

## Important Context

### Project Structure
- This is a deep learning experiment manager
- Tests are currently named after implementation steps (test_step_1_1.py, etc.)
- Goal is to reorganize into unit/, integration/, and validation/ directories
- Must preserve all test functionality while improving organization

### Key Guidelines
1. **Commit Size**: Keep commits small (15-30 lines of changes)
2. **Commit Messages**: Use the exact commit message specified in the plan
3. **File History**: Use `git mv` when moving files to preserve history
4. **Test Execution**: Run relevant tests after each commit to ensure nothing breaks
5. **Progress Tracking**: Update the plan document immediately after completing each commit

### Working with the Plan
- Each commit in the plan shows "TODO" or "DONE"
- Start with the first "TODO" you find
- Change "TODO" to "DONE" after completing the commit
- Save the plan document after each update

### Handling Missing Files
If a test file mentioned in the plan doesn't exist:
1. Note it in a comment after the commit entry
2. Continue with the next commit
3. Don't create placeholder files

### Test Markers
When you see test markers in the plan:
- `@pytest.mark.slow` - For tests that take a long time
- `@pytest.mark.supabase` - For tests requiring Supabase
- `@pytest.mark.gpu` - For tests requiring GPU

### Verification Steps
After completing a phase:
1. Run `pytest tests/unit` (after unit test phase)
2. Run `pytest tests/integration` (after integration test phase)
3. Run `pytest tests/validation` (after validation test phase)
4. Fix any import errors before proceeding

## Example Workflow

1. Read the plan:
```bash
cat docs/test-refactoring-plan.md
```

2. Find first TODO (e.g., Commit 1):
```
**Commit 1:** `test: create new test directory structure` - TODO
```

3. Execute the specified commands:
```bash
mkdir -p tests/unit tests/integration tests/validation tests/fixtures tests/utils
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
touch tests/validation/__init__.py tests/fixtures/__init__.py tests/utils/__init__.py
```

4. Update the plan to mark as DONE:
```
**Commit 1:** `test: create new test directory structure` - DONE
```

5. Commit with the exact message:
```bash
git add tests/
git commit -m "test: create new test directory structure"
```

6. Continue with next TODO commit

## Error Handling
If you encounter errors:
1. Don't skip the commit
2. Fix the issue (missing imports, syntax errors, etc.)
3. Ensure tests pass before marking as DONE
4. If blocked, add a note in the plan and continue

Remember: The goal is systematic, incremental progress. Each commit should leave the codebase in a working state.