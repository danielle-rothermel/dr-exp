#!/bin/bash
# Monitor high regularization experiment progress

export EXP_DIR=/scratch/ddr8143/repos/dr_exp/high_regularization_ablation

echo "=== High Regularization Experiment Monitor ==="
echo "Experiment directory: $EXP_DIR"
echo "Time: $(date)"
echo ""

# Overall status
echo "=== Experiment Status ==="
uv run dr_exp --base-path $EXP_DIR --experiment main status
echo ""

# Worker status
echo "=== Active Workers ==="
ps aux | grep "worker_" | grep "high_regularization_ablation" | grep -v grep | awk '{print $2, $11, $12, $13, $14}'
echo ""

# Running jobs
echo "=== Currently Running Jobs ==="
uv run dr_exp --base-path $EXP_DIR --experiment main job list --status running | head -20
echo ""

# Check latest metrics from running jobs
echo "=== Latest Training Progress ==="
for job_dir in $EXP_DIR/main/storage/run_*/; do
    if [ -d "$job_dir" ] && [ -f "$job_dir/metrics.jsonl" ]; then
        job_id=$(basename $job_dir | sed 's/run_//')
        
        # Check if job is in running state
        if [ -f "$EXP_DIR/main/jobs/$job_id.json" ] && grep -q '"status": "running"' "$EXP_DIR/main/jobs/$job_id.json"; then
            # Get config name
            config_name=$(grep -o '"config_name": "[^"]*"' "$EXP_DIR/main/jobs/$job_id.json" | cut -d'"' -f4)
            seed=$(grep -o '"seed": [0-9]*' "$EXP_DIR/main/jobs/$job_id.json" | cut -d' ' -f2)
            
            # Get last metric
            last_metric=$(tail -1 "$job_dir/metrics.jsonl" 2>/dev/null)
            if [ ! -z "$last_metric" ]; then
                epoch=$(echo "$last_metric" | grep -o '"epoch": [0-9]*' | cut -d' ' -f2)
                val_loss=$(echo "$last_metric" | grep -o '"val_loss": [0-9.]*' | cut -d' ' -f2)
                val_acc=$(echo "$last_metric" | grep -o '"val_acc": [0-9.]*' | cut -d' ' -f2)
                
                echo "Job: $job_id"
                echo "  Config: $config_name (seed=$seed)"
                echo "  Epoch: $epoch, Val Loss: $val_loss, Val Acc: $val_acc"
                echo ""
            fi
        fi
    fi
done

# Summary by config
echo "=== Progress Summary by Config ==="
for config in step00_baseline_high_reg step01_sgd_high_reg step02_no_randaug_high_reg step03_no_cutmix_high_reg step04_no_mixup_high_reg; do
    completed=$(uv run dr_exp --base-path $EXP_DIR --experiment main job list --status completed 2>/dev/null | grep -c "$config")
    running=$(uv run dr_exp --base-path $EXP_DIR --experiment main job list --status running 2>/dev/null | grep -c "$config")
    queued=$(uv run dr_exp --base-path $EXP_DIR --experiment main job list --status queued 2>/dev/null | grep -c "$config")
    echo "$config: Completed=$completed, Running=$running, Queued=$queued"
done

echo ""
echo "=== Worker Logs (last 5 lines each) ==="
for i in {0..3}; do
    if [ -f "$EXP_DIR/worker_$i.log" ]; then
        echo "--- Worker $i ---"
        tail -5 "$EXP_DIR/worker_$i.log" | grep -E "Epoch|val_loss|Claiming|Complete" || tail -3 "$EXP_DIR/worker_$i.log"
        echo ""
    fi
done