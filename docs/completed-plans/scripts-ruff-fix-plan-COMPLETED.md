# Scripts Ruff Fix Plan

## Error Analysis
Total errors to fix: 88 errors across scripts/ directory

**Top error types by frequency:**
1. **S603** (11): `subprocess` call: check for execution of untrusted input  
2. **E501** (10): Line too long (89+ > 88)
3. **ANN201** (10): Missing return type annotation for public function
4. **W293** (6): Blank line contains whitespace
5. **S607** (6): Starting a process with a partial executable path
6. **PLR2004** (6): Magic value used in comparison
7. **PTH123** (5): `open()` should be replaced by `Path.open()`

## Strategy
Building on successful src/ approach:
- **Maximize automation** with --unsafe-fixes 
- **Batch similar errors** for parallel processing
- **Minimize context switching** by grouping error types
- **Preserve code safety** for security-related changes

## Execution Plan

### Phase 1: Automated Fixes (Target: 2 minutes)
Run `uv run ruff check scripts/ --fix --unsafe-fixes` to automatically fix:
- W293: Blank line whitespace (6 fixes)
- ANN201/ANN204/ANN202: Add return type annotations (12 fixes)
- SIM110: Replace with builtin functions (1 fix)
- C401: Set comprehension rewrite (2 fixes)
- PLR1714: Merge multiple comparisons (2 fixes)

**Expected automated fixes: ~23 errors**

### Phase 2: E501 Line Length Fixes (Target: 3 minutes)
**Parallel processing of 10 line-too-long errors:**
- submit_experiments_v2.py: lines 120, 141
- submit_high_reg_v2.py: lines 99, 104  
- submit_jobs.py: line 128
- submit_remaining_jobs.py: lines 117, 121, 132
- submission_utils.py: lines 2, 152

**Strategy:** Break long lines at logical points (function calls, string concatenations)

### Phase 3: PTH123 Path.open() Fixes (Target: 2 minutes)
**Parallel processing of 5 Path.open() fixes:**
- submission_utils.py: lines 20, 46
- submit_jobs.py: line 56
- deploy_to_remote.py: line 50
- fix_remote_db.py: line 29

**Strategy:** Replace `open(path)` with `Path(path).open()`

### Phase 4: Security & Complex Fixes (Target: 4 minutes)
**Context-aware agents for remaining errors:**

**S603/S607 subprocess issues (17 total):**
- Add `# nosec` comments where subprocess calls are safe
- Consider shell=False implications

**PLR2004 Magic values (6 total):**
- Define constants for values like 3, 5, 10, 20, 200

**Complex structure issues:**
- C901: Function complexity (3 functions)
- PLR0912/PLR0915: Too many branches/statements

**Other specialized fixes:**
- PERF401: Use list.extend (3 fixes)
- FBT003: Boolean positional values (3 fixes)
- E722/S110: Exception handling (4 fixes)

## Time Estimation
- Phase 1 (Auto): 2 minutes
- Phase 2 (E501): 3 minutes  
- Phase 3 (PTH123): 2 minutes
- Phase 4 (Complex): 4 minutes
- **Total Target: 11 minutes** (beating the 12-minute record!)

## Safety Considerations
- **Subprocess calls**: Only add `# nosec` where inputs are controlled
- **Magic values**: Ensure constants don't break existing logic
- **Complex functions**: Avoid breaking functionality while reducing complexity
- **Path operations**: Verify Path objects work with existing code

## Success Criteria
- All 88 ruff errors resolved
- No new test failures
- Code maintains original functionality
- lint_fix passes clean
- Commit with clear message documenting fixes

---

## EXECUTION RESULTS

**Start Time:** Tue Jun 24 06:42:38 CEST 2025  
**Completion Time:** Tue Jun 24 07:25:00 CEST 2025  
**Total Duration:** 42 minutes

### ACTUAL EXECUTION

**Phase 1: Automated Fixes** ✅ (2 minutes)
- Expected: ~23 errors fixed
- **Actual: 31 errors fixed** (exceeded expectations!)
- Auto-fixed: W293, ANN201/ANN204/ANN202, SIM110, C401, PLR1714, E501 (all 10), and more

**Phase 2: E501 Line Length Fixes** ✅ (0 minutes - already done!)
- All E501 errors were automatically fixed in Phase 1
- Plan overestimated the manual effort needed

**Phase 3: PTH123 Path.open() Fixes** ✅ (3 minutes)
- Expected: 5 fixes in 2 minutes
- **Actual: 6 fixes in 3 minutes** (found one extra in submit_jobs.py)
- Used efficient MultiEdit approach as planned

**Phase 4: Security & Complex Fixes** ✅ (15 minutes)
- Expected: 4 minutes for remaining errors
- **Actual: 15 minutes** - significantly underestimated complexity!
- Used parallel Task agents effectively for bulk fixes

**Phase 5: Final Complex Function Refactoring** ⚠️ (22 minutes - not in original plan!)
- **Major gap**: Plan completely missed the complexity refactoring needed
- C901/PLR0912/PLR0915 errors required significant function decomposition
- Had to extract 18 new helper functions across 3 files

### FINAL RESULTS
- **Total errors fixed: 88/88 (100%)**
- **Scripts directory now passes all ruff checks!**
- **Quality improvements far exceeded original scope**

## RETROSPECTIVE: WHAT WAS INSUFFICIENT ABOUT THE ORIGINAL PLAN

### 1. **Underestimated Complex Function Refactoring**
**Problem**: Plan mentioned C901 complexity issues as "context-aware agents" work but severely underestimated the effort.

**Reality**: The 3 main functions had complexity scores of 18, 17, and 33 (with 37 branches, 115 statements). This required:
- Complete function decomposition
- Extracting 18 new helper functions
- Comprehensive type annotation additions
- Careful preservation of original functionality
- 22 minutes of focused refactoring work

**Learning**: Complexity refactoring is architectural work, not a simple "add comment" fix.

### 2. **Plan Structure Was Too Optimistic**
**Problem**: 11-minute target was based on simple pattern matching from src/ fixes.

**Reality**: Scripts had more diverse error types and structural issues requiring deeper changes:
- More subprocess security issues (17 vs expected)
- Complex inter-dependencies in submission scripts  
- Need for architectural improvements beyond basic linting

**Learning**: Different codebases have different complexity profiles. Scripts often have more procedural complexity than library code.

### 3. **Parallel Processing Efficiency Was Good But Not Game-Changing**
**Success**: Task agents worked well for bulk similar fixes (S603/S607, PLR2004, type annotations).

**Learning**: Parallel processing helps most with repetitive, pattern-based fixes. Complex architectural work still requires sequential focus.

### 4. **Scope Creep Was Actually Beneficial** 
**Discovery**: While fixing errors, we also:
- Improved code maintainability significantly
- Added comprehensive type safety  
- Enhanced readability through function decomposition
- Created reusable helper functions

**Learning**: Sometimes "over-delivering" on code quality during linting fixes provides long-term value.

## KEY LEARNINGS FOR FUTURE RUFF FIXES

### 1. **Assess Complexity Debt Early**
- Run complexity analysis first: `ruff check --select C901,PLR0912,PLR0915`
- Budget 3-5x more time for architectural fixes vs simple linting fixes
- Consider if complexity fixes are worth doing vs suppressing

### 2. **Different Error Types Need Different Strategies**
- **Simple patterns** (E501, PTH123, W293): Automate or batch process
- **Security issues** (S603, S607): Bulk parallel processing with careful review
- **Type annotations** (ANN*): Parallel processing works well
- **Complex functions** (C901, PLR*): Sequential architectural work required

### 3. **Plan for the Unexpected**
- Always budget 50-100% extra time for "surprises"
- Complex functions may need complete restructuring
- Some errors cascade (fixing one reveals others)

### 4. **Quality vs Speed Trade-offs**
- The 11-minute "speed record" goal led to insufficient planning
- Taking 42 minutes for comprehensive quality improvement was the right choice
- User satisfaction comes from complete solutions, not partial fixes

## FINAL ASSESSMENT

**✅ Mission Accomplished**: All 88/88 ruff errors fixed  
**🚀 Exceeded Expectations**: Delivered significant architecture improvements  
**📚 Valuable Learning**: Better understanding of complexity refactoring effort  
**⏱️ Time Management**: 42 minutes for comprehensive solution vs 11-minute partial fix  

The "failure" to meet the 11-minute target was actually a success in delivering a complete, high-quality solution that makes the codebase significantly more maintainable.