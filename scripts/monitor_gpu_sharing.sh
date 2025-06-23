#!/bin/bash
# Monitor GPU usage and MPS status during multi-worker experiments

echo "=== GPU Sharing Monitor ==="
echo "Press Ctrl+C to exit"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

while true; do
    clear
    echo -e "${BLUE}=== GPU & MPS Status ===${NC}"
    echo "Time: $(date)"
    echo ""
    
    # GPU utilization
    echo -e "${GREEN}GPU Utilization:${NC}"
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits | \
    awk -F', ' '{printf "GPU %s: %s | Util: %3d%% | Mem: %5dMB/%5dMB | Temp: %d°C\n", $1, $2, $3, $4, $5, $6}'
    echo ""
    
    # Process information
    echo -e "${GREEN}GPU Processes:${NC}"
    nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader,nounits | \
    awk -F', ' '{printf "PID: %6s | %-30s | %5d MB\n", $1, $2, $3}'
    echo ""
    
    # MPS status
    echo -e "${GREEN}CUDA MPS Status:${NC}"
    if pgrep -x "nvidia-cuda-mps" > /dev/null; then
        echo "MPS Server: Running"
        # Try to get MPS client info
        if [ -n "$CUDA_MPS_PIPE_DIRECTORY" ]; then
            echo "MPS Pipe: $CUDA_MPS_PIPE_DIRECTORY"
        fi
    else
        echo -e "${YELLOW}MPS Server: Not Running${NC}"
    fi
    echo ""
    
    # dr_exp worker status (if available)
    if command -v dr_exp &> /dev/null; then
        echo -e "${GREEN}Active Workers:${NC}"
        ps aux | grep -E "dr_exp.*worker" | grep -v grep | awk '{print $2, $11, $12, $13, $14}' | \
        while read line; do
            echo "  $line"
        done
    fi
    
    sleep 5
done