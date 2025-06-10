# Phase 4: API Local Testing Implementation Guide

## Overview
This phase implements a minimal API for local testing before cloud deployment. We'll focus on getting the API working locally with the new JobDB architecture.

**Duration**: 2-3 days
**Prerequisite**: Phase 3 must be complete with Supabase integration working
**Outcome**: Working API that can be tested locally

## Pre-flight Checklist

### Verify Phase 3 Completion
```bash
# Run integration test
python test_supabase_integration.py  # Should pass

# Check Supabase dashboard
# You should see test data in tables and storage
```

## Step 1: Create Minimal API

Create `src/dr_exp/api/simple_api.py`:

```python
"""Minimal API for experiment monitoring."""

import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from dr_exp.core.job_db import JobDB

load_dotenv()

# Request/Response models
class JobResponse(BaseModel):
    id: str
    experiment_name: str
    config: Dict[str, Any]
    priority: int
    status: str
    created_at: str
    updated_at: str
    assigned_worker: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MetricsResponse(BaseModel):
    job_id: str
    metrics: List[Dict[str, Any]]


# Create FastAPI app
app = FastAPI(
    title="DR_EXP Experiment Monitor",
    description="Simple API for monitoring ML experiments",
    version="1.0.0"
)

# Add CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global JobDB instance (will be initialized on startup)
job_db: Optional[JobDB] = None
connected_websockets: List[WebSocket] = []


@app.on_event("startup")
async def startup_event():
    """Initialize JobDB on startup."""
    global job_db
    
    # Get configuration from environment
    base_path = os.getenv("DR_EXP_BASE_PATH")
    experiment_name = os.getenv("DR_EXP_EXPERIMENT")
    
    if not base_path or not experiment_name:
        raise RuntimeError(
            "DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT must be set in environment"
        )
    
    # Initialize JobDB with remote read enabled
    job_db = JobDB(
        base_path=base_path,
        experiment_name=experiment_name,
        enable_remote_read=True
    )
    
    print(f"API initialized for experiment '{experiment_name}' at {base_path}")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "experiment": job_db.experiment_name if job_db else None,
        "base_path": str(job_db.base_path) if job_db else None,
    }


@app.get("/api/jobs", response_model=List[JobResponse])
async def list_jobs(status: Optional[str] = None):
    """List all jobs, optionally filtered by status."""
    if not job_db:
        raise HTTPException(status_code=500, detail="JobDB not initialized")
    
    try:
        # Try remote read first (Supabase)
        jobs = job_db.list_jobs_remote(status=status)
    except Exception as e:
        # Fall back to local read if remote fails
        print(f"Remote read failed, falling back to local: {e}")
        jobs = job_db.list_jobs(status=status)
    
    return [JobResponse(**job) for job in jobs]


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get details for a specific job."""
    if not job_db:
        raise HTTPException(status_code=500, detail="JobDB not initialized")
    
    job = job_db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    return JobResponse(**job)


@app.get("/api/jobs/{job_id}/metrics", response_model=MetricsResponse)
async def get_job_metrics(job_id: str):
    """Get metrics for a specific job."""
    if not job_db:
        raise HTTPException(status_code=500, detail="JobDB not initialized")
    
    # Try to get metrics from remote first
    metrics_path = None
    try:
        metrics_path = job_db.get_metrics_remote(job_id)
    except Exception as e:
        print(f"Remote metrics fetch failed: {e}")
    
    # Fall back to local if remote failed
    if not metrics_path:
        local_path = job_db.get_storage_path(job_id) / "metrics.jsonl"
        if local_path.exists():
            metrics_path = local_path
    
    if not metrics_path or not metrics_path.exists():
        raise HTTPException(status_code=404, detail=f"Metrics not found for job {job_id}")
    
    # Read metrics
    metrics = []
    with open(metrics_path, 'r') as f:
        for line in f:
            if line.strip():
                metrics.append(json.loads(line))
    
    return MetricsResponse(job_id=job_id, metrics=metrics)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    connected_websockets.append(websocket)
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)


# Helper function to broadcast updates (call this from workers)
async def broadcast_job_update(job_id: str, status: str):
    """Broadcast job status update to all connected clients."""
    message = json.dumps({
        "type": "job_update",
        "job_id": job_id,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
    })
    
    for ws in connected_websockets[:]:  # Copy list to avoid modification during iteration
        try:
            await ws.send_text(message)
        except:
            connected_websockets.remove(ws)
```

## Step 2: Create Local Test Script

Create `test_api_local.py`:

```python
#!/usr/bin/env python3
"""Test the API locally."""

import os
import time
import json
import requests
import subprocess
import tempfile
from pathlib import Path

from dr_exp.core.job_db import JobDB
from dr_exp.worker.training_worker import TrainingWorker


def test_api_local():
    """Test API functionality locally."""
    print("Testing API locally...")
    
    # Create test environment
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "users", "testuser", "experiments")
        experiment_name = f"api_test_{int(time.time())}"
        
        # Set environment variables
        env = os.environ.copy()
        env["DR_EXP_BASE_PATH"] = base_path
        env["DR_EXP_EXPERIMENT"] = experiment_name
        env["SUPABASE_URL"] = os.getenv("SUPABASE_URL", "")
        env["SUPABASE_KEY"] = os.getenv("SUPABASE_KEY", "")
        
        # Initialize JobDB and create test data
        db = JobDB(base_path=base_path, experiment_name=experiment_name)
        print(f"✓ Created test experiment at {db.experiment_path}")
        
        # Create test jobs
        job_ids = []
        for i in range(3):
            job_id = db.create_job({
                "model": f"test_model_{i}",
                "lr": 0.01 * (i + 1),
                "epochs": 1,
            }, priority=100 * (i + 1))
            job_ids.append(job_id)
        print(f"✓ Created {len(job_ids)} test jobs")
        
        # Start API server
        print("\nStarting API server...")
        api_process = subprocess.Popen(
            ["uvicorn", "dr_exp.api.simple_api:app", "--host", "0.0.0.0", "--port", "8000"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Wait for API to start
        time.sleep(3)
        
        try:
            # Test health check
            response = requests.get("http://localhost:8000/")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["experiment"] == experiment_name
            print("✓ Health check passed")
            
            # Test list jobs
            response = requests.get("http://localhost:8000/api/jobs")
            assert response.status_code == 200
            jobs = response.json()
            assert len(jobs) >= len(job_ids)  # Might have jobs from Supabase too
            print(f"✓ Listed {len(jobs)} jobs")
            
            # Test get specific job
            response = requests.get(f"http://localhost:8000/api/jobs/{job_ids[0]}")
            assert response.status_code == 200
            job = response.json()
            assert job["id"] == job_ids[0]
            assert job["status"] == "queued"
            print(f"✓ Retrieved job {job_ids[0]}")
            
            # Run a job to generate metrics
            print("\nRunning a job to generate metrics...")
            worker = TrainingWorker(
                worker_id="api_test_worker",
                job_db=db,
                sync_enabled=False,  # No sync for this test
            )
            completed_job_id = worker.run_next_job()
            assert completed_job_id == job_ids[2]  # Highest priority
            print(f"✓ Completed job {completed_job_id}")
            
            # Test metrics endpoint
            response = requests.get(f"http://localhost:8000/api/jobs/{completed_job_id}/metrics")
            assert response.status_code == 200
            metrics_data = response.json()
            assert metrics_data["job_id"] == completed_job_id
            assert len(metrics_data["metrics"]) > 0
            print(f"✓ Retrieved {len(metrics_data['metrics'])} metrics")
            
            # Test WebSocket (basic connection)
            print("\nTesting WebSocket connection...")
            import websocket
            ws = websocket.WebSocket()
            ws.connect("ws://localhost:8000/ws")
            ws.send("Hello")
            result = ws.recv()
            assert result == "Echo: Hello"
            ws.close()
            print("✓ WebSocket connection works")
            
        finally:
            # Stop API server
            api_process.terminate()
            api_process.wait(timeout=5)
            print("\n✓ API server stopped")
    
    print("\n✅ All API tests passed!")


if __name__ == "__main__":
    # Check for required dependencies
    try:
        import requests
        import websocket
    except ImportError:
        print("Please install test dependencies:")
        print("pip install requests websocket-client")
        exit(1)
    
    test_api_local()
```

## Step 3: Install API Dependencies

```bash
# Install FastAPI and server using uv
uv add fastapi uvicorn websockets

# Install test dependencies
uv add --dev httpx pytest-asyncio websocket-client
```

## Step 4: Create Simple Frontend Test

Create `test_frontend.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>DR_EXP Monitor - Local Test</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .job {
            border: 1px solid #ddd;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .status-queued { background-color: #f0f0f0; }
        .status-running { background-color: #fffacd; }
        .status-completed { background-color: #90ee90; }
        .status-failed { background-color: #ffcccb; }
        pre {
            background-color: #f5f5f5;
            padding: 10px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    <h1>DR_EXP Experiment Monitor</h1>
    
    <div id="status">Connecting...</div>
    
    <h2>Jobs</h2>
    <button onclick="refreshJobs()">Refresh</button>
    <div id="jobs"></div>
    
    <h2>WebSocket Messages</h2>
    <div id="messages"></div>

    <script>
        const API_URL = 'http://localhost:8000';
        let ws = null;
        
        // Connect WebSocket
        function connectWebSocket() {
            ws = new WebSocket('ws://localhost:8000/ws');
            
            ws.onopen = () => {
                document.getElementById('status').textContent = 'Connected';
                console.log('WebSocket connected');
            };
            
            ws.onmessage = (event) => {
                const msg = document.createElement('div');
                msg.textContent = new Date().toISOString() + ': ' + event.data;
                document.getElementById('messages').prepend(msg);
            };
            
            ws.onclose = () => {
                document.getElementById('status').textContent = 'Disconnected - Reconnecting...';
                setTimeout(connectWebSocket, 3000);
            };
        }
        
        // Fetch and display jobs
        async function refreshJobs() {
            try {
                const response = await fetch(`${API_URL}/api/jobs`);
                const jobs = await response.json();
                
                const jobsDiv = document.getElementById('jobs');
                jobsDiv.innerHTML = '';
                
                jobs.forEach(job => {
                    const jobDiv = document.createElement('div');
                    jobDiv.className = `job status-${job.status}`;
                    jobDiv.innerHTML = `
                        <h3>Job ${job.id.substring(0, 8)}...</h3>
                        <p>Status: <strong>${job.status}</strong></p>
                        <p>Priority: ${job.priority}</p>
                        <p>Model: ${job.config.model || 'N/A'}</p>
                        <p>Created: ${new Date(job.created_at).toLocaleString()}</p>
                        ${job.result ? '<pre>' + JSON.stringify(job.result, null, 2) + '</pre>' : ''}
                    `;
                    jobsDiv.appendChild(jobDiv);
                });
            } catch (error) {
                console.error('Error fetching jobs:', error);
                document.getElementById('jobs').innerHTML = '<p>Error loading jobs</p>';
            }
        }
        
        // Initialize
        connectWebSocket();
        refreshJobs();
        
        // Auto-refresh every 5 seconds
        setInterval(refreshJobs, 5000);
    </script>
</body>
</html>
```

## Step 5: Run Tests with Quality Gates

### Validation Gate
Run these commands and fix ALL issues before proceeding:

```bash
# 1. Code quality check
ckdr
# Expected: "All checks passed!"
# If fails: Fix the code, not the rules

# 2. Run all tests
pt
# Expected: All tests pass, no skips
# If fails: Fix implementation, not tests

# 3. Run API tests specifically
pt tests/test_api_local.py -v
# Expected: All API tests pass
```

⚠️ **CRITICAL**: If any check fails:
1. Read the FULL error message
2. Understand what the test/check expects
3. Fix YOUR CODE to meet expectations
4. Do NOT modify tests/rules to pass

Common fixes:
- Import errors → Ensure FastAPI properly installed with `uv add fastapi`
- Type errors → Add proper type hints to API endpoints
- Test failures → API implementation doesn't match spec

## Step 6: Run Local Integration Test

```bash
# Terminal 1: Set environment and start API
export DR_EXP_BASE_PATH=/tmp/test_experiments
export DR_EXP_EXPERIMENT=my_test_experiment
uv run uvicorn dr_exp.api.simple_api:app --reload

# Terminal 2: Run pytest tests
pt tests/test_api_local.py -v

# Terminal 3: Open the HTML file in a browser
# Just double-click test_frontend.html or:
open test_frontend.html  # macOS
xdg-open test_frontend.html  # Linux
```

## Validation Checklist

Before proceeding to cloud deployment:

- [ ] **ALL quality checks pass**: `ckdr` shows "All checks passed!"
- [ ] **ALL tests pass**: `pt` shows all tests passing
- [ ] Test coverage is adequate: `pt --cov=dr_exp.api`
- [ ] API tests pass: `pt tests/test_api_local.py -v`
- [ ] API server starts without errors
- [ ] Frontend HTML can connect and display jobs
- [ ] WebSocket connections work
- [ ] API can read from both local files and Supabase
- [ ] Metrics endpoint returns data for completed jobs

### Phase 4 Validation Gate

```bash
# No proceeding until these ALL work:
ckdr && echo "✓ Quality checks pass" || echo "✗ FIX CODE QUALITY FIRST"
pt tests/test_api_local.py && echo "✓ API tests pass" || echo "✗ FIX IMPLEMENTATION"
pt && echo "✓ All tests pass" || echo "✗ FIX ALL FAILURES"
```

If any check shows ✗:
1. STOP
2. Read the error carefully
3. Fix the implementation (not the test)
4. Run all checks again
5. Only proceed when all show ✓

## Architecture Notes

Key design decisions for local API:
- Single experiment per API instance (configured via environment)
- Automatic fallback from Supabase to local files
- Simple WebSocket for real-time updates
- Minimal dependencies (just FastAPI)

## Common Issues

**"JobDB not initialized" error**
- Make sure DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT are set
- Check that the paths exist and are accessible

**Cannot connect to API**
- Check that port 8000 is not in use
- Make sure uvicorn is installed
- Check firewall settings

**No jobs showing in UI**
- Verify jobs exist in the experiment directory
- Check browser console for errors
- Make sure CORS is configured correctly

## Common Test Anti-Patterns

### ⚠️ DO NOT Test with Real Servers

❌ **WRONG - Don't spawn servers in tests:**
```python
# This is flaky and slow
subprocess.Popen(["uvicorn", "app:app"])
time.sleep(5)  # Hope it's ready?
```

✅ **RIGHT - Use TestClient:**
```python
from fastapi.testclient import TestClient
client = TestClient(app)
response = client.get("/api/jobs")
```

### ⚠️ DO NOT Mock What You're Testing

❌ **WRONG - Don't mock the API logic:**
```python
@patch('dr_exp.api.simple_api.get_jobs')
def test_api(mock_get_jobs):
    mock_get_jobs.return_value = []  # Not testing anything!
```

✅ **RIGHT - Test with real JobDB:**
```python
def test_api(test_job_db):
    # Use fixture that creates real JobDB
    response = client.get("/api/jobs")
    assert len(response.json()) == 3
```

## Next Steps

Once local testing is working well:
1. Decide if you need cloud deployment
2. If yes, proceed to Phase 5: Cloud Deployment
3. If no, you can use the local API with SSH tunneling:
   ```bash
   # From your laptop, tunnel to cluster
   ssh -L 8000:localhost:8000 cluster.example.com
   # Then run API on cluster and access at http://localhost:8000
   ```

This gives you full remote monitoring without cloud deployment!