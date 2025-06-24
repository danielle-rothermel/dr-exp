# Test Lint Fix Task Prompt

## Your Mission
Fix all 189 ruff linting errors in the tests/ directory following the plan in `docs/tests-ruff-fix-plan.md`.

## IMPORTANT: Test Commands First!
Before starting any fixes, verify all your tools work correctly:

```bash
# 1. Test ruff tools are available
source ~/.claude/ruff_tools.sh
ruff_help

# 2. Verify current error count
ruff_analyze tests
ruff_summary | head -10
ruff_hot_files

# 3. Test pytest works
pt tests/test_doc_fixes.py -v

# 4. Check that error file was created
ls -la .ruff_errors.jsonl

# 5. Test a sample ruff_show command
ruff_show ANN201 | head -5
```

If any of these fail, STOP and debug before proceeding!

## Key Context You Need

### 1. **Pyproject.toml Already Updated**
The user has already added test-specific suppressions:
- D103 (docstrings) - ignored for tests
- S106 (hardcoded passwords) - ignored for tests  
- SLF001 (private access) - ignored for tests
- S101 (asserts) - already globally ignored

This means **Phase 4 suppressions are NOT needed** - focus on real fixes!

### 2. **Test-Specific Patterns**
- **pytest fixtures**: `tmp_path` is a Path object, use it instead of `/tmp`
- **Return types**: All test functions should have `-> None`
- **Loop variables**: Use `_` for intentionally unused variables
- **Assertions**: Use `pytest.fail()` not `assert False`
- **Exception testing**: Use `pytest.raises()` context manager

### 3. **Priority Strategy**
Based on the analysis, focus on these high-impact files first:
- `test_step_3_1.py` (33 errors)
- `test_step_2_2.py` (14 errors)
- `test_step_1_1.py` (13 errors)

## Execution Instructions

### Phase 1: Auto-fixes (5 min)
```bash
# First capture baseline
ruff_analyze tests
cp .ruff_errors.jsonl .ruff_errors_baseline.jsonl

# Run maximum auto-fixes
ruff_unsafe_fix tests

# Check what was fixed
ruff_count tests
```

### Phase 2: Parallel Pattern Fixes (10 min)
Use Task agents for these parallel fixes:

**Task 1 - S108 temp files (15 errors)**:
- Find all `/tmp/` usage
- Replace with `tmp_path / "filename"`
- Ensure fixtures are properly typed

**Task 2 - B007 unused loops (10 errors)**:
- Replace `for i in range(n):` with `for _ in range(n):`
- Check if variable is actually used before renaming

**Task 3 - PT015/B011 assert False (22 errors)**:
- Replace `assert False` with `pytest.fail()`
- Include meaningful error messages

### Phase 3: Path Operations (8 min)
Fix remaining path issues sequentially:
- PTH123: `open()` → `Path().open()`
- PTH110: `os.path.exists()` → `Path().exists()`
- PTH118: `os.path.join()` → Path with `/`

### Phase 4: Complex Pytest Patterns (7 min)
Handle PT017 carefully - these require understanding the test logic:
```python
# Pattern to look for:
try:
    something()
except Exception as e:
    assert "expected" in str(e)  # PT017

# Convert to:
with pytest.raises(Exception, match="expected"):
    something()
```

## Critical Warnings

1. **Run tests after each phase!** Don't break functionality:
   ```bash
   pt tests/ -x  # Stop on first failure
   ```

2. **Use TodoWrite** to track your phases - the user values visibility

3. **Commit after each successful phase** to avoid losing work

4. **Check error counts** between phases:
   ```bash
   ruff_count tests
   ```

5. **If you see new errors** after fixes, investigate why

## Success Criteria
- All 189 errors resolved
- All tests still pass
- No new errors introduced
- Clean commits after each phase
- Completed plan moved to `docs/completed-plans/` with retrospective

## Reference Material
- See `docs/completed-plans/scripts-ruff-fix-plan-COMPLETED.md` for lessons learned
- Key insight: Complex refactoring takes longer than simple fixes
- The scripts/ fix succeeded by being thorough rather than fast

## Start Now!
1. First test all commands work
2. Use TodoWrite to plan your phases
3. Execute Phase 1 auto-fixes
4. Report initial progress

Good luck! The scripts/ fix took 42 minutes for 88 errors, you should aim for 30 minutes for these 189 errors by leveraging maximum automation and parallelization.