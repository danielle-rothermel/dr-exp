# Cluster Setup Checklist for dr_exp with Supabase Sync

This guide helps you set up dr_exp on a new machine (cluster/server) to sync with remote Supabase.

## Prerequisites

### 1. Clone the Repository
```bash
git clone <your-repo-url> dr_exp
cd dr_exp
```

### 2. Install uv (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or ~/.zshrc
```

### 3. Install Dependencies
```bash
uv sync
```

## Essential Configuration

### 1. Create `.env` File

Create a `.env` file in the project root with your Supabase credentials:

```bash
cat > .env << 'EOF'
# Supabase Configuration
SUPABASE_URL="https://yfawygsfsuwrqvohsayp.supabase.co"
SUPABASE_KEY="your-service-role-key-here"

# Optional: Set base path for experiments
DR_EXP_BASE_PATH=/path/to/experiments

# Optional: Debug mode
DEBUG=False
EOF
```

**Security Note**: 
- Use the service role key (not anon key) for full access
- Never commit `.env` to git
- Set restrictive permissions: `chmod 600 .env`

**Important**: The `.env` file is NOT automatically loaded by shell scripts. You have three options:

1. **Source it manually before running commands**:
   ```bash
   source .env  # or `. .env`
   uv run dr_exp --base-path ./exp --experiment test worker --worker-id w1
   ```

2. **Export in your shell session**:
   ```bash
   export $(cat .env | grep -v '^#' | xargs)
   ```

3. **Let Python load it** (dr_exp uses python-dotenv automatically):
   ```bash
   # Python scripts will load .env automatically
   uv run python scripts/test_remote_supabase.py
   
   # dr_exp CLI also loads .env automatically
   uv run dr_exp --base-path ./exp --experiment test worker --worker-id w1
   ```

### 2. Verify Network Connectivity

Clusters often have restricted internet access. Test connectivity:

```bash
# Test DNS resolution
nslookup supabase.co

# Test HTTPS connectivity
curl -I https://supabase.co

# Test your specific Supabase instance
curl -I $SUPABASE_URL
```

If blocked, you may need to:
- Request firewall exceptions for `*.supabase.co`
- Use proxy settings (see below)

## Verification Steps

### 1. Test Supabase Connection

Run the connection test script:

```bash
uv run python scripts/test_remote_supabase.py
```

Expected output:
```
✓ Found SUPABASE_URL: https://yfawygsfsuwrqvohsayp.supabase.co
✓ Found SUPABASE_KEY: eyJhbGciOiJIUzI1NiIs... (hidden)
✓ Supabase package imported successfully
✓ Connected! Found X storage buckets
✓ Database working! Found X experiments
✅ Remote Supabase connection test PASSED!
```

### 2. Test Database Access

Check if you can read from the remote database:

```bash
uv run python scripts/check_remote_db.py
```

### 3. Test Full Sync Pipeline

Run a minimal test job with sync:

```bash
# Initialize test experiment
uv run dr_exp --base-path ./cluster_test --experiment verify_sync init

# Submit a test job
uv run dr_exp --base-path ./cluster_test --experiment verify_sync job submit \
  --config-name test_trainer --priority 100

# Run worker with sync (for just 1 job)
uv run dr_exp --base-path ./cluster_test --experiment verify_sync worker \
  --worker-id cluster_test_01 --max-jobs 1
```

## Cluster-Specific Considerations

### 1. SLURM Integration

For SLURM clusters, use the launcher with proper module loading:

```bash
#!/bin/bash
#SBATCH --job-name=dr_exp_worker
#SBATCH --gres=gpu:1
#SBATCH --time=48:00:00

# Load required modules (adjust for your cluster)
module load python/3.10
module load cuda/11.8

# Change to project directory
cd /path/to/dr_exp

# Load environment variables from .env file
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# OR explicitly export credentials
# export SUPABASE_URL="https://yfawygsfsuwrqvohsayp.supabase.co"
# export SUPABASE_KEY="your-key-here"

# Run worker
uv run dr_exp --base-path /scratch/experiments --experiment my_exp \
  system launcher --workers-per-gpu 2
```

### 2. Proxy Configuration

If your cluster uses a proxy:

```bash
# Add to .env or export before running
export HTTP_PROXY=http://proxy.cluster.edu:8080
export HTTPS_PROXY=http://proxy.cluster.edu:8080
export NO_PROXY=localhost,127.0.0.1
```

### 3. Storage Considerations

- **Scratch vs Home**: Use scratch for experiments, home for code
- **Shared Filesystems**: Ensure all workers can access the experiment path
- **Quotas**: Monitor disk usage, especially for model checkpoints

### 4. Multi-Node Setup

For multi-node jobs, ensure:
- All nodes can access the shared experiment directory
- Environment variables are propagated to all nodes
- Use unique worker IDs per node/GPU

## Troubleshooting

### Connection Issues

1. **"Failed to connect to Supabase"**
   - Check internet connectivity
   - Verify SUPABASE_URL format
   - Ensure using service role key

2. **"SSL certificate verification failed"**
   - Try: `export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`
   - Or disable (not recommended): `export CURL_CA_BUNDLE=""`

3. **"Connection timeout"**
   - Check firewall rules
   - Test with curl: `curl -v $SUPABASE_URL`
   - May need proxy configuration

### Authentication Issues

1. **"Invalid API key"**
   - Verify you're using service role key (not anon)
   - Check for extra spaces/quotes in .env
   - Regenerate key in Supabase dashboard if needed

### Sync Issues

1. **"Files remain in queue"**
   - Check network connectivity during job execution
   - Verify storage bucket exists
   - Check worker logs in `experiments/*/logs/`

## Quick Verification Script

Create `verify_cluster_setup.sh`:

```bash
#!/bin/bash
echo "🔍 Verifying dr_exp Cluster Setup"
echo "================================="

# Check environment
echo -e "\n1. Environment Variables:"
echo "   SUPABASE_URL: ${SUPABASE_URL:+Set}"
echo "   SUPABASE_KEY: ${SUPABASE_KEY:+Set}"

# Check connectivity
echo -e "\n2. Network Connectivity:"
if curl -s -o /dev/null -w "%{http_code}" https://supabase.co | grep -q "200\|301"; then
    echo "   ✅ Can reach supabase.co"
else
    echo "   ❌ Cannot reach supabase.co"
fi

# Check Python environment
echo -e "\n3. Python Environment:"
uv run python -c "import dr_exp; print(f'   ✅ dr_exp version: {dr_exp.__version__}')" 2>/dev/null || echo "   ❌ dr_exp not installed"

# Test Supabase connection
echo -e "\n4. Supabase Connection:"
uv run python scripts/test_remote_supabase.py 2>&1 | grep -E "(✅|❌)" | head -5

echo -e "\n✅ Setup verification complete!"
```

## Best Practices

1. **Use Environment Modules**: Load consistent Python/CUDA versions
2. **Set Up Logging**: Direct logs to persistent storage
3. **Monitor Sync Queue**: Check `sync_queue/` directory for pending items
4. **Use Scratch Space**: For large experiments and temporary files
5. **Regular Backups**: Sync ensures cloud backup of results

## Security Reminders

- Never share or commit your SUPABASE_KEY
- Use environment variables or secure secret management
- Restrict .env file permissions: `chmod 600 .env`
- Rotate keys periodically
- Use separate keys for dev/prod if needed

With this setup, your cluster workers will automatically sync all job results and artifacts to Supabase!