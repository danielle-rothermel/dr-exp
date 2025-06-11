# Improved Job Submission Scripts

## Quick Start

The new submission scripts include critical safety features for stressed PhD students:

### 🎯 Unified Script (Recommended)

```bash
# Preview what would be submitted (DRY RUN)
./submit_jobs.py --experiment-type chrono --dry-run

# Submit chronological experiments (with confirmation)
./submit_jobs.py --experiment-type chrono

# Submit high-reg experiments
./submit_jobs.py --experiment-type high-reg

# Submit both experiment types
./submit_jobs.py --experiment-type both

# Retry failed jobs from last run
./submit_jobs.py --retry-failed

# Submit specific configs with default seeds
./submit_jobs.py --configs step00_baseline step01_sgd

# Submit specific configs with custom seeds  
./submit_jobs.py --configs step00_baseline step01_sgd --seeds 0 1 2

# Skip confirmation prompts (for scripts)
./submit_jobs.py --experiment-type chrono --no-confirm

# Force resubmit even if jobs exist
./submit_jobs.py --experiment-type chrono --force
```

### 🛡️ Safety Features

1. **Dry Run Mode** (`--dry-run`)
   - See exactly what would be submitted
   - No actual submission happens
   - Perfect for verification

2. **Duplicate Detection** (`--skip-existing`)
   - Checks for existing jobs before submission
   - Prevents accidental duplicates
   - On by default!

3. **Transaction Logging**
   - All submissions logged to `submission_logs/submission_YYYYMMDD_HHMMSS.json`
   - Track what was submitted, when, and whether it succeeded
   - Use logs to retry failed submissions

4. **Config Validation**
   - Validates all config files exist BEFORE submitting anything
   - No partial submissions due to missing configs

5. **Clear Failure Summary**
   - Shows exactly which jobs failed and why
   - Provides rerun command for failed jobs
   - Points to log file for full details

### 📝 Individual Scripts

If you prefer the original scripts, use the v2 versions:

```bash
# Chronological experiments
./submit_experiments_v2.py --dry-run
./submit_experiments_v2.py

# High regularization experiments  
./submit_high_reg_v2.py --dry-run
./submit_high_reg_v2.py
```

### 🚨 Common Scenarios

**"Did my submission work?"**
Check the submission logs:
```bash
ls submission_logs/
cat submission_logs/submission_20240115_143022.json
```

**"I think some jobs failed"**
```bash
# Retry failed jobs from most recent submission
./submit_jobs.py --retry-failed
```

**"I accidentally Ctrl+C'd during submission"**
```bash
# Check what was already submitted
dr_exp --experiment test list --status all

# Submit remaining jobs (will skip existing)
./submit_jobs.py --experiment-type chrono
```

**"I want to test one config first"**
```bash
# Submit just one config with one seed
./submit_jobs.py --configs step00_baseline --seeds 0

# Submit multiple configs with specific seeds
./submit_jobs.py --configs step00_baseline step01_sgd --seeds 0 1

# If it works, submit the rest
./submit_jobs.py --experiment-type chrono
```

### 🔧 Advanced Options

```bash
# Submit specific configs - cleaner syntax!
./submit_jobs.py --configs step00_baseline step07_no_residual step17_no_hflip
# (Uses default seeds: 0,1,2 for regular configs, 0-4 for high_reg configs)

# Custom seeds for experiment types
./submit_jobs.py --experiment-type chrono --seeds 42 43 44

# Mix and match
./submit_jobs.py --configs step00_baseline step00_baseline_high_reg --seeds 10 20 30

# Submit with custom priority (higher = run first)
./submit_jobs.py --configs step00_baseline --priority 999

# Submit urgent test job
./submit_jobs.py --configs step00_baseline --seeds 0 --priority 1000

# Different experiment directory
./submit_jobs.py --base-path /path/to/exp --experiment my_exp --experiment-type chrono

# Force resubmit (ignores existing jobs)
./submit_jobs.py --experiment-type chrono --force
```

### ⚠️ Important Notes

1. **Always use `--dry-run` first** when unsure
2. **Check existing jobs** with `dr_exp list` before bulk submissions
3. **Keep submission logs** - they're your safety net
4. **Default is safe** - scripts skip existing jobs by default

### 🆘 Troubleshooting

**"Script says config files are missing"**
- Check you're in the right directory
- Verify `exp_configs/` directory exists
- Check config file names match

**"Submission seems slow"**
- Scripts add small delays (0.1s) between submissions
- This prevents overwhelming the job system
- Total time: ~5 seconds for 54 jobs

**"How do I know what jobs are running?"**
```bash
# Check job status
dr_exp --experiment test status

# List all jobs
dr_exp --experiment test list --status all

# Monitor in real-time
watch -n 5 "dr_exp --experiment test status"
```