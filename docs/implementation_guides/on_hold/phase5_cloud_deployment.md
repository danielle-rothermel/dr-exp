# Phase 5: Cloud Deployment Implementation Guide

## Overview
This phase deploys the API to Vercel for true remote access without SSH tunneling.

**Duration**: 1-2 days
**Prerequisite**: Phase 4 must be complete with local API working
**Outcome**: API accessible from anywhere via HTTPS

## Pre-flight Checklist

### Verify Phase 4 Completion
```bash
# Ensure quality gates passed
ckdr  # Should show "All checks passed!"
pt tests/test_api_local.py  # Should pass

# Verify Supabase is working
# Check that your Supabase project has data
```

### Set Up Vercel Account
1. Go to https://vercel.com and sign up (free)
2. Install Vercel CLI:
```bash
npm install -g vercel
# or
brew install vercel-cli  # macOS
```

## Step 1: Create Vercel-Compatible API

Create `api/index.py` in project root:

```python
"""Vercel serverless function entry point."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import our simple API
from dr_exp.api.simple_api import app as original_app

# For Vercel, we need to export the app directly
app = original_app

# Vercel handles startup differently, so initialize here
from dr_exp.core.job_db import JobDB

# Get configuration from Vercel environment variables
base_path = os.getenv("DR_EXP_BASE_PATH", "/tmp")  # Vercel gives us /tmp
experiment_name = os.getenv("DR_EXP_EXPERIMENT", "default_experiment")

# Initialize JobDB globally (Vercel will cache this between invocations)
job_db = JobDB(
    base_path=base_path,
    experiment_name=experiment_name,
    enable_remote_read=True  # Must use Supabase on Vercel
)

# Update the app's job_db reference
import dr_exp.api.simple_api
dr_exp.api.simple_api.job_db = job_db

# Note: WebSockets don't work on Vercel, so those endpoints will be disabled
```

## Step 2: Create Vercel Configuration

Create `vercel.json` in project root:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "15mb"
      }
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ],
  "env": {
    "DR_EXP_EXPERIMENT": "@dr_exp_experiment",
    "SUPABASE_URL": "@supabase_url",
    "SUPABASE_KEY": "@supabase_key"
  }
}
```

## Step 3: Create Requirements File for Vercel

Create `requirements.txt` in project root:

```
fastapi==0.104.1
supabase==2.0.0
python-dotenv==1.0.0
pydantic==2.5.0
```

## Step 4: Prepare for Deployment

Since Vercel can't access `/scratch`, we need to ensure everything works with Supabase only:

```python
# Create a test script: prepare_vercel_deployment.py

#!/usr/bin/env python3
"""Prepare and test Vercel deployment."""

import os
import time
from dotenv import load_dotenv
from dr_exp.core.job_db import JobDB
from dr_exp.sync.supabase_client import SupabaseClient

load_dotenv()

def prepare_vercel_deployment():
    """Ensure Supabase has data for Vercel to read."""
    print("Preparing for Vercel deployment...")
    
    # Check environment
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("❌ SUPABASE_URL and SUPABASE_KEY must be set")
        return False
    
    experiment_name = "vercel_demo"
    print(f"Using experiment: {experiment_name}")
    
    # Create some demo data directly in Supabase
    client = SupabaseClient()
    client.ensure_experiment(experiment_name)
    
    # Create demo jobs
    demo_jobs = [
        {
            "id": f"demo_{i}",
            "experiment_name": experiment_name,
            "config": {"model": f"model_{i}", "lr": 0.01 * (i + 1)},
            "priority": 100 * (i + 1),
            "status": ["queued", "running", "completed"][i % 3],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        for i in range(3)
    ]
    
    for job in demo_jobs:
        try:
            client.sync_job(job)
            print(f"✓ Created demo job {job['id']}")
        except Exception as e:
            print(f"❌ Failed to create job {job['id']}: {e}")
    
    print("\n✅ Supabase prepared for Vercel deployment")
    print(f"Set DR_EXP_EXPERIMENT={experiment_name} in Vercel")
    return True


if __name__ == "__main__":
    prepare_vercel_deployment()
```

## Step 5: Deploy to Vercel

```bash
# Step 1: Login to Vercel
vercel login

# Step 2: Run preparation script
python prepare_vercel_deployment.py

# Step 3: Deploy (first time)
vercel

# Answer the prompts:
# - Set up and deploy? Y
# - Which scope? (select your account)
# - Link to existing project? N
# - Project name? dr-exp-monitor (or your choice)
# - Directory? ./ (current directory)
# - Override settings? N

# Step 4: Set environment variables
vercel env add DR_EXP_EXPERIMENT production  # Enter: vercel_demo
vercel env add SUPABASE_URL production       # Enter: your Supabase URL
vercel env add SUPABASE_KEY production       # Enter: your Supabase key

# Step 5: Deploy to production
vercel --prod
```

## Step 6: Test Deployed API

Create `test_vercel_deployment.py`:

```python
#!/usr/bin/env python3
"""Test the Vercel deployment."""

import requests
import json


def test_vercel_deployment(deployment_url):
    """Test API on Vercel."""
    print(f"Testing deployment at {deployment_url}")
    
    # Test health check
    response = requests.get(f"{deployment_url}/")
    assert response.status_code == 200
    data = response.json()
    print(f"✓ Health check: {data}")
    
    # Test list jobs
    response = requests.get(f"{deployment_url}/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    print(f"✓ Found {len(jobs)} jobs")
    
    # Test specific job
    if jobs:
        job_id = jobs[0]["id"]
        response = requests.get(f"{deployment_url}/api/jobs/{job_id}")
        assert response.status_code == 200
        print(f"✓ Retrieved job {job_id}")
    
    print("\n✅ Vercel deployment working!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_vercel_deployment.py <deployment-url>")
        print("Example: python test_vercel_deployment.py https://dr-exp-monitor.vercel.app")
        sys.exit(1)
    
    test_vercel_deployment(sys.argv[1])
```

## Step 7: Create Production Frontend

Update the `test_frontend.html` to use your Vercel URL:

```javascript
// Change this line:
const API_URL = 'http://localhost:8000';
// To:
const API_URL = 'https://your-app-name.vercel.app';
```

## Validation Checklist

- [ ] **ALL quality checks still pass**: `ckdr` shows "All checks passed!"
- [ ] Vercel CLI is installed and you're logged in
- [ ] Preparation script created demo data in Supabase
- [ ] Deployment completed successfully
- [ ] Environment variables are set in Vercel dashboard
- [ ] API health check works
- [ ] Can list and retrieve jobs
- [ ] Frontend can connect to deployed API

### Phase 5 Validation Gate

Since this is an optional deployment phase, the validation is simpler:

```bash
# Ensure code quality maintained
ckdr && echo "✓ Quality checks pass" || echo "✗ FIX CODE QUALITY FIRST"

# Test the deployment (replace with your URL)
uv run python test_vercel_deployment.py https://your-app.vercel.app
```

If deployment test fails:
1. Check Vercel logs for errors
2. Verify environment variables are set
3. Ensure Supabase credentials are correct
4. Check that demo data exists in Supabase

## Important Notes

### Vercel Limitations
1. **No WebSockets**: Vercel doesn't support WebSockets, so real-time updates won't work
2. **No local storage**: Everything must be in Supabase
3. **Cold starts**: First request might be slow
4. **Execution limits**: 10 second timeout on free tier

### Security Considerations
1. **Use environment variables**: Never commit keys to git
2. **Add authentication**: Consider adding API keys for production
3. **Rate limiting**: Vercel has built-in DDoS protection

### Alternative: Railway Deployment

If you need WebSockets or longer execution times, consider Railway instead:

```bash
# Install Railway CLI
brew install railway

# Login and deploy
railway login
railway init
railway up

# Add environment variables in Railway dashboard
```

## Next Steps

1. **Add authentication**: Protect your API with bearer tokens
2. **Custom domain**: Add your own domain in Vercel settings
3. **Monitoring**: Use Vercel Analytics to track usage
4. **Optimize**: Use Vercel Edge Functions for better performance

## Troubleshooting

**"Module not found" errors**
- Make sure all imports are in requirements.txt
- Check that your package structure is correct
- Vercel uses Python 3.9 by default

**"No data" in API**
- Verify Supabase credentials are correct
- Check Vercel logs: `vercel logs`
- Ensure preparation script ran successfully

**Slow response times**
- This is normal for cold starts
- Consider upgrading to Vercel Pro for better performance
- Use caching headers for static data

Once deployed, you can monitor your experiments from anywhere without SSH access to the cluster!