# Tests Ruff Fix Plan

## Error Analysis
Total errors to fix: 209 errors across tests/ directory

**Top error types by frequency:**
1. **ANN201** (50): Missing return type annotation for test functions
2. **W291** (19): Trailing whitespace  
3. **S108** (15): Insecure temp file usage (/tmp)
4. **D103** (13): Missing docstring in public function
5. **PTH123/PTH110/PTH118** (17 total): Path operation issues
6. **ANN001** (12): Missing type annotation for function arguments
7. **PT017/PT015/B011** (33 total): Pytest idiom violations
8. **B007** (10): Unused loop control variables

## Strategy
Building on lessons from scripts/ fixes:
- **Maximize automation** with --unsafe-fixes
- **Use semantic commands** for easier analysis
- **Batch similar patterns** for parallel processing  
- **Respect test code patterns** (different from production)
- **Focus on real improvements** not pedantic fixes

## Semantic Commands Available
Use the global ruff tools for easy analysis:
```bash
source ~/.claude/ruff_tools.sh  # Load commands (always available)

# Analysis commands
ruff_analyze tests              # Generate .ruff_errors.jsonl
ruff_summary                    # Show error count summary
ruff_by_file                    # Show files with most errors
ruff_hot_files                  # Top 10 files by error count
ruff_show ANN201                # Show examples of specific error
ruff_find_pattern "assert False"  # Find specific patterns

# Fix commands  
ruff_autofix tests              # Run safe auto-fixes
ruff_unsafe_fix tests           # Run all auto-fixes including unsafe
ruff_preview tests              # Preview what would be fixed
```

## Execution Plan

### Phase 1: Analysis & Automated Fixes (Target: 5 minutes)
```bash
# Setup
source ~/.claude/ruff_tools.sh

# Analyze current state
ruff_analyze tests
ruff_summary
ruff_by_file

# Run automated fixes
ruff_unsafe_fix tests
```
**Expected automated fixes: ~80-90 errors**
- W291: All trailing whitespace (19)
- ANN201: Return type annotations (50) 
- Some PTH* path operations
- Some simple pattern replacements

### Phase 2: Bulk Pattern Fixes (Target: 10 minutes)
**Parallel processing of common patterns:**

**Task 1: Fix S108 temp file usage (15 errors)**
- Replace `/tmp/file` → `tmp_path / "file"`
- Ensure pytest fixture is imported and used

**Task 2: Fix B007 unused loop variables (10 errors)**
- Replace `for i in range(n):` → `for _ in range(n):`
- Replace `for i, item in enumerate(items):` → `for _, item in enumerate(items):`

**Task 3: Fix pytest assertion patterns (33 errors)**
- PT015/B011: `assert False` → `pytest.fail()`
- Simple PT017: Move assertions out of except blocks

### Phase 3: Path Operations (Target: 8 minutes)
**Fix remaining PTH* errors:**
- PTH123: `open(path)` → `Path(path).open()`
- PTH110: `os.path.exists()` → `Path().exists()`
- PTH118: `os.path.join()` → `Path() / component`

### Phase 4: Complex Pytest Patterns (Target: 7 minutes)
**Sequential work for context-aware fixes:**

**PT017 conversions:**
```python
# Before
try:
    something()
    assert False
except Exception as e:
    assert "expected" in str(e)

# After  
with pytest.raises(Exception, match="expected"):
    something()
```

**Fixture type annotations:**
- Add proper types for pytest fixtures like `tmp_path: Path`
- Import types from pytest as needed

## Special Considerations for Tests

### Patterns to Preserve
- Test function names are self-documenting (D103 often redundant)
- Hardcoded test data is acceptable (S106 passwords, S104 bind all)
- Private member access for testing internals (SLF001)

### Test-Specific Best Practices
- Always use `tmp_path` fixture instead of `/tmp`
- Prefer `pytest.fail()` over `assert False`
- Use `_` for intentionally unused variables
- Add `-> None` to all test functions
- Use `pytest.raises()` for exception testing

## Time Estimation
- Phase 1 (Analysis & Auto): 5 minutes
- Phase 2 (Pattern fixes): 10 minutes
- Phase 3 (Path operations): 8 minutes  
- Phase 4 (Complex pytest): 7 minutes
- **Total Target: 30 minutes**

## Success Criteria
- All 209 ruff errors resolved
- No test functionality broken
- Improved pytest idiom usage
- Better type safety in tests
- Cleaner, more maintainable test code

## Validation
After completion:
```bash
# Verify all fixes
ruff_check tests

# Run tests to ensure nothing broke
pt

# Check specific error types are gone
ruff_count tests | grep "ANN201\|PT015\|S108"
```

---

**Start Time:** [To be filled during execution]  
**Completion Time:** [To be filled during execution]  
**Total Duration:** [To be filled during execution]