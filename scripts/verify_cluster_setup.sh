#!/bin/bash
# Verification script for dr_exp cluster setup

echo "🔍 Verifying dr_exp Cluster Setup"
echo "================================="
echo "Hostname: $(hostname)"
echo "Date: $(date)"
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check status
check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
        return 0
    else
        echo -e "${RED}❌ $2${NC}"
        return 1
    fi
}

# 1. Check Python and uv
echo "1. Python Environment:"
echo "   Python: $(which python || echo 'Not found')"
echo "   uv: $(which uv || echo 'Not found')"

# 2. Check environment variables
echo -e "\n2. Environment Variables:"
if [ -n "$SUPABASE_URL" ]; then
    echo -e "   ${GREEN}✅ SUPABASE_URL is set: ${SUPABASE_URL:0:30}...${NC}"
else
    echo -e "   ${RED}❌ SUPABASE_URL is not set${NC}"
fi

if [ -n "$SUPABASE_KEY" ]; then
    echo -e "   ${GREEN}✅ SUPABASE_KEY is set: ${SUPABASE_KEY:0:20}...${NC}"
else
    echo -e "   ${RED}❌ SUPABASE_KEY is not set${NC}"
fi

# 3. Check .env file
echo -e "\n3. Configuration Files:"
if [ -f .env ]; then
    echo -e "   ${GREEN}✅ .env file exists${NC}"
    # Check permissions
    perms=$(stat -c %a .env 2>/dev/null || stat -f %A .env 2>/dev/null)
    if [ "$perms" = "600" ]; then
        echo -e "   ${GREEN}✅ .env has secure permissions (600)${NC}"
    else
        echo -e "   ${YELLOW}⚠️  .env has permissions $perms (recommend 600)${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  No .env file found${NC}"
fi

# 4. Check network connectivity
echo -e "\n4. Network Connectivity:"

# Test general internet
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Internet connectivity OK${NC}"
else
    echo -e "   ${RED}❌ No internet connectivity${NC}"
fi

# Test HTTPS
if curl -s -o /dev/null -m 5 -w "%{http_code}" https://supabase.co | grep -q "200\|301\|302"; then
    echo -e "   ${GREEN}✅ HTTPS to supabase.co works${NC}"
else
    echo -e "   ${YELLOW}⚠️  Cannot reach supabase.co (may need proxy)${NC}"
fi

# Test specific Supabase instance
if [ -n "$SUPABASE_URL" ]; then
    if curl -s -o /dev/null -m 5 -w "%{http_code}" "$SUPABASE_URL" | grep -q "200\|301\|302\|401"; then
        echo -e "   ${GREEN}✅ Can reach your Supabase instance${NC}"
    else
        echo -e "   ${RED}❌ Cannot reach your Supabase instance${NC}"
    fi
fi

# 5. Check proxy settings
echo -e "\n5. Proxy Settings:"
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo "   HTTP_PROXY: ${HTTP_PROXY:-Not set}"
    echo "   HTTPS_PROXY: ${HTTPS_PROXY:-Not set}"
    echo "   NO_PROXY: ${NO_PROXY:-Not set}"
else
    echo "   No proxy configured"
fi

# 6. Check dr_exp installation
echo -e "\n6. dr_exp Installation:"
if uv run python -c "import dr_exp" 2>/dev/null; then
    echo -e "   ${GREEN}✅ dr_exp package is installed${NC}"
    
    # Check if CLI works
    if uv run dr_exp --help >/dev/null 2>&1; then
        echo -e "   ${GREEN}✅ dr_exp CLI is working${NC}"
    else
        echo -e "   ${RED}❌ dr_exp CLI not working${NC}"
    fi
else
    echo -e "   ${RED}❌ dr_exp package not installed${NC}"
    echo "   Run: uv sync"
fi

# 7. Test Supabase connection
echo -e "\n7. Supabase Connection Test:"
if [ -f scripts/test_remote_supabase.py ]; then
    # Run test and capture result
    if uv run python scripts/test_remote_supabase.py >/tmp/supabase_test.log 2>&1; then
        echo -e "   ${GREEN}✅ Supabase connection test PASSED${NC}"
        grep "✓" /tmp/supabase_test.log | head -5 | sed 's/^/   /'
    else
        echo -e "   ${RED}❌ Supabase connection test FAILED${NC}"
        echo "   Check /tmp/supabase_test.log for details"
    fi
else
    echo -e "   ${YELLOW}⚠️  test_remote_supabase.py not found${NC}"
fi

# 8. Check for GPU (if on compute node)
echo -e "\n8. GPU Availability:"
if command -v nvidia-smi >/dev/null 2>&1; then
    gpu_count=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    if [ $gpu_count -gt 0 ]; then
        echo -e "   ${GREEN}✅ Found $gpu_count GPU(s)${NC}"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | sed 's/^/      /'
    else
        echo -e "   ${YELLOW}⚠️  nvidia-smi found but no GPUs detected${NC}"
    fi
else
    echo "   No nvidia-smi found (OK if on login node)"
fi

# 9. Check disk space
echo -e "\n9. Disk Space:"
df -h . | grep -v Filesystem | awk '{print "   Current directory: " $4 " available (" $5 " used)"}'

# Summary
echo -e "\n================================="
echo "Summary:"
all_good=true

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
    echo -e "${RED}❌ Missing Supabase credentials${NC}"
    all_good=false
fi

if ! uv run python -c "import dr_exp" 2>/dev/null; then
    echo -e "${RED}❌ dr_exp not properly installed${NC}"
    all_good=false
fi

if $all_good; then
    echo -e "${GREEN}✅ Basic setup looks good!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run a test job:"
    echo "   uv run dr_exp --base-path ./test --experiment cluster_test job submit --config-name test_trainer"
    echo ""
    echo "2. Start a worker:"
    echo "   uv run dr_exp --base-path ./test --experiment cluster_test worker --worker-id test_01"
else
    echo -e "${YELLOW}⚠️  Please fix the issues above${NC}"
fi

# Clean up
rm -f /tmp/supabase_test.log