# Phase 4 Agent Prompt - Test Performance Optimization

## Task Overview
Optimize test suite performance and maintainability. Current issue: 18 edge case tests take 13s (target: <5s total).

## Immediate Actions
1. **Install pytest-xdist**: `uv add pytest-xdist` and implement parallel execution
2. **Add test markers**: Categorize tests as fast/slow/concurrency/integration  
3. **Optimize fixtures**: Reduce database setup overhead with better scoping
4. **Deduplicate code**: Extract common patterns from test files

## Context
- **Status**: All 29 tests passing (11 integration + 18 edge case)
- **Coverage**: Complete database errors, concurrency, recovery mechanisms
- **Infrastructure**: Robust fixtures available in `tests/conftest.py`

## Reference Files
- `test_refactor_plan.md` - Complete Phase 4 requirements
- `PHASE4_HANDOFF.md` - Detailed implementation guidance  
- `tests/PHASE3_PATTERNS.md` - Testing patterns documentation
- `tests/manage/test_phase3_edge_cases.py` - Current slow tests to optimize

## Success Criteria
- Full test suite execution < 10 seconds
- Working parallel execution with pytest-xdist
- Comprehensive test categorization markers
- Reduced code duplication

**Key constraint**: Maintain all existing test coverage while optimizing performance.