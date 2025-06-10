# Step 2.2: Sync Queue Implementation

## Goal
Create a SyncQueue class that manages pending file uploads with persistence and retry logic.

## Prerequisites
- Step 2.1 completed and validated
- Required files exist: src/dr_exp/worker/base.py
- test_step_2_1.py passes

## Overview

This step implements a file-based queue system for managing artifact uploads:
- **Persistent queue**: Each sync item stored as a separate JSON file
- **Retry logic**: Exponential backoff with configurable max attempts
- **Batch processing**: Process multiple items with single function call
- **History tracking**: Completed items moved to JSONL history file
- **File integrity**: Automatic checksum calculation for uploads

## Key Components

### SyncItem Dataclass
Represents a file to be synced with metadata:
- Core fields: `id`, `job_id`, `file_path`, `file_type`
- Status tracking: `status`, `attempts`, `last_attempt`, `error`
- File metadata: `checksum`, `size_bytes` (auto-calculated)
- Timestamps: `created_at`, `completed_at`

### SyncQueue Class
Main queue manager with methods:
1. **`add_item()`** - Queue new file with microsecond timestamp prefix
2. **`get_pending_items()`** - Retrieve items ready for processing
3. **`process_queue()`** - Batch process with provided sync function
4. **`mark_attempt()`** - Record success/failure with retry logic
5. **`complete_item()`** - Move successful items to history
6. **`get_stats()`** - Queue statistics by status

### Design Decisions
- **File-per-item**: Each queue item is a separate JSON file for robustness
- **Microsecond timestamps**: Filename prefix ensures natural ordering and uniqueness
- **Exponential backoff**: 60s × 2^(attempts-1) delay between retries
- **History file**: Append-only JSONL for completed items

## Validation

Test coverage includes:
- Basic queue operations (add, get, stats)
- Batch processing with mock sync function
- Retry logic with exponential backoff
- Item completion and history tracking
- FIFO ordering verification
- Error handling and partial batch failures

Run: `pt tests/implementation/test_step_2_2.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Implementation uses `datetime.utcnow()` throughout
   - **Type**: Consistency issue
   - **Impact**: Minor - should use `datetime.now(UTC)` for consistency with other steps
   - **Note**: Both test and implementation use deprecated `utcnow()`

2. **Error handling in mark_attempt**: Implementation structure differs from instructions
   - **Type**: Positive improvement
   - **Reason**: Cleaner logic for incrementing attempts and checking max retries

3. **Missing import in test**: Test file missing `import json`
   - **Type**: Documentation error
   - **Resolution**: Actual test file includes the import correctly

### Implementation Quality Notes
- Excellent separation of concerns (queue management vs sync logic)
- Good use of dataclasses for type safety
- Robust error handling with corrupted file skipping
- Clean batch processing abstraction
- Proper file cleanup after completion

### Lessons Learned
1. Microsecond timestamps prevent collisions even with rapid additions
2. File-based queues are simple and crash-resistant
3. Exponential backoff prevents overwhelming failed services
4. History files provide audit trail without cluttering queue
5. Batch processing API enables flexible sync strategies

### Dependencies for Later Steps
- Worker will use SyncQueue for artifact uploads (Step 2.3)
- CLI will display sync queue stats (Step 2.5)
- History file enables upload verification
- Retry logic patterns reused in other components

### Technical Decisions
1. **No locking**: Queue operations are naturally atomic at file level
2. **No index**: Directory listing is fast enough for reasonable queue sizes
3. **JSONL history**: Append-only format prevents corruption
4. **Status in filename**: Could have used filename prefix for faster filtering
5. **Manual checksum**: Ensures file integrity before upload attempts

### Testing Insights
- Time delays necessary to ensure timestamp uniqueness
- Mocking sync functions allows testing without real uploads
- Manual time manipulation needed to test backoff logic
- History file verification confirms completion
- Error injection tests partial failure scenarios

### Performance Considerations
- O(n) directory scan for each `get_pending_items()` call
- No pagination or streaming for large queues
- History file grows unbounded without cleanup
- Checksum calculation adds overhead for large files
- Could benefit from status-based subdirectories

### Future Enhancement Opportunities
1. Move completed items to archive directory
2. Add queue size limits or age-based expiry
3. Implement priority levels for sync items
4. Support chunked uploads for large files
5. Add compression before upload
6. Create status-based subdirectories for faster queries
7. Implement sync queue garbage collection

### Cross-Step Patterns
- File-per-item pattern (similar to JobDB)
- Timestamped filenames for ordering
- Status-based filtering during iteration
- Graceful handling of corrupted files
- Comprehensive test scenarios

### Risk Areas
1. **Timestamp collisions**: Microsecond precision might not be enough at scale
2. **Queue growth**: No automatic cleanup could fill disk
3. **Large file checksums**: Could block queue operations
4. **Corrupted queue files**: Accumulate without cleanup
5. **History file size**: Unbounded growth needs rotation

## Common Mistakes to Avoid
- Using a database for the queue (files are simpler and sufficient)
- Implementing complex state machines (keep status simple)
- Adding transaction support (single file operations are atomic)
- Forgetting exponential backoff (prevents hammering failed endpoints)
- Keeping completed items in queue directory (move to history)
- Not handling corrupted queue files gracefully

## Next Step
Proceed to Step 2.3: Worker Threading Integration