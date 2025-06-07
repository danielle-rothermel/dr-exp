# API Reference (`docs/api_reference.md`)

## Overview

The DR Experiment Manager provides a comprehensive REST API with WebSocket support for managing deep learning experiments. The API is built with FastAPI and provides real-time monitoring, job management, priority control, and system observability.

## Base URL and Versioning

**Current Version:** `v1.0.0`

**Base URLs:**
- **Development:** `http://localhost:8000`
- **Production:** Your deployed API endpoint

**API Versioning:**
- **Current Endpoints:** Direct access (e.g., `/jobs`)
- **Versioned Endpoints:** Future `/api/v1/` prefix
- **Migration Path:** Unversioned endpoints include deprecation headers for future migration

## Authentication

The API uses **Bearer Token Authentication** with role-based access control:

### Roles
- **Admin Role:** Full access to all endpoints including job management and priority controls
- **Reader Role:** Read-only access to job data and metrics

### Authentication Headers
```http
Authorization: Bearer <your-token>
```

### Environment Variables
```bash
# Default development tokens
ADMIN_API_KEY=testkey    # Admin access
READER_API_KEY=readkey   # Read-only access
```

### Protected Endpoints
All admin operations require authentication:
- Job control (kill, requeue)
- Priority management (boost, set)
- System administration

## API Information

### GET /api
Get API version information and available endpoints.

**Response:**
```json
{
  "name": "DR Experiment Manager API",
  "version": "1.0.0",
  "versions": {
    "v1": {
      "status": "stable",
      "prefix": "/api/v1",
      "docs": "/docs"
    }
  },
  "health_check": "/health",
  "metrics": "/metrics",
  "websocket": "/ws"
}
```

## Job Management

### GET /jobs
List jobs with optional pagination, filtering, and sorting.

**Query Parameters:**
- `page` (int): Page number (1-based, default: 1)
- `per_page` (int): Items per page (1-100, default: 20)
- `paginated` (bool): Return paginated response (default: false)
- `job_status` (string): Filter by status (queued, running, completed, failed, killed)
- `priority_min` (int): Minimum priority (0-1000)
- `priority_max` (int): Maximum priority (0-1000)
- `sort_by` (string): Sort field (created_at, priority, status, retry_index)
- `sort_order` (string): Sort order (asc, desc)

**Simple Response (paginated=false):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running",
    "priority": 500,
    "retry_index": 0,
    "assigned_worker": "worker_001",
    "created_at": "2024-01-15T10:30:00Z",
    "started_at": "2024-01-15T10:35:00Z",
    "heartbeat": "2024-01-15T10:45:00Z",
    "config_id": "config_123"
  }
]
```

**Paginated Response (paginated=true):**
```json
{
  "jobs": [...],
  "total": 150,
  "page": 1,
  "per_page": 20,
  "pages": 8,
  "has_next": true,
  "has_prev": false
}
```

### GET /job/{job_id}
Get detailed information for a specific job.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "priority": 500,
  "retry_index": 0,
  "assigned_worker": "worker_001",
  "created_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:35:00Z",
  "end_time": null,
  "heartbeat": "2024-01-15T10:45:00Z",
  "kill_requested": false,
  "config_id": "config_123"
}
```

### GET /config/{job_id}
Get the configuration for a specific job.

**Response:**
```json
{
  "config": {
    "model": {
      "name": "resnet",
      "layers": 50
    },
    "optimizer": {
      "name": "adam",
      "lr": 0.001
    },
    "trainer": {
      "epochs": 100,
      "batch_size": 32
    }
  }
}
```

### GET /metrics/{run_id}
Get metrics for a specific training run.

**Query Parameters:**
- `limit` (int): Maximum number of metrics to return (default: 500)

**Response:**
```json
{
  "metrics": [
    {
      "step": 0,
      "train_loss": 2.34,
      "val_loss": 2.12,
      "val_accuracy": 0.15,
      "timestamp": "2024-01-15T10:35:30Z"
    },
    {
      "step": 1,
      "train_loss": 2.30,
      "val_loss": 2.08,
      "val_accuracy": 0.18,
      "timestamp": "2024-01-15T10:36:00Z"
    }
  ],
  "count": 2
}
```

## Administrative Operations

### POST /job/kill
**Authentication Required:** Admin

Mark a job for termination.

**Request:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Job 550e8400-e29b-41d4-a716-446655440000 marked for termination",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### POST /job/requeue
**Authentication Required:** Admin

Requeue a job for another execution attempt.

**Request:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Job 550e8400-e29b-41d4-a716-446655440000 requeued for retry (attempt 1)",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Priority Management

### POST /job/boost-priority
**Authentication Required:** Admin

Increase a job's priority by the specified amount.

**Request:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "boost_amount": 100
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "old_priority": 500,
  "new_priority": 600,
  "success": true,
  "message": "Priority boosted from 500 to 600"
}
```

### POST /job/set-priority
**Authentication Required:** Admin

Set the absolute priority of a job.

**Request:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "priority": 800,
  "reason": "Urgent deadline experiment"
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "old_priority": 600,
  "new_priority": 800,
  "success": true,
  "message": "Priority updated to 800"
}
```

## System Monitoring

### GET /health
Health check endpoint providing system status information.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:45:00Z",
  "uptime_seconds": 3600.5,
  "version": "1.0.0",
  "database_status": "healthy",
  "job_stats": {
    "queued": 25,
    "running": 4,
    "completed": 120,
    "failed": 2,
    "killed": 0
  }
}
```

### GET /metrics
System metrics for monitoring and observability.

**Response:**
```json
{
  "timestamp": "2024-01-15T10:45:00Z",
  "uptime_seconds": 3600.5,
  "active_connections": 3,
  "job_stats": {
    "queued": 25,
    "running": 4,
    "completed": 120,
    "failed": 2,
    "killed": 0
  },
  "total_jobs": 151,
  "queue_depth": 25,
  "running_jobs": 4
}
```

## Real-time Communication

### WebSocket /ws
WebSocket endpoint for real-time job updates and system notifications.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

**Message Types:**

**Job Update:**
```json
{
  "type": "job_update",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "priority_boosted",
  "old_priority": 500,
  "new_priority": 600,
  "boost_amount": 100,
  "message": "Job 550e8400... priority boosted by 100"
}
```

**Job Status Change:**
```json
{
  "type": "job_update",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "requeued",
  "retry_index": 1,
  "message": "Job 550e8400... requeued for retry (attempt 1)"
}
```

**Job Termination:**
```json
{
  "type": "job_update",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "kill_requested",
  "message": "Job 550e8400... marked for termination"
}
```

## Response Headers

### Standard Headers
All responses include:
- `X-API-Version`: Current API version (1.0.0)
- `X-Process-Time`: Request processing time in seconds

### Security Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

### Deprecation Headers
Non-versioned endpoints include:
- `X-API-Deprecation-Notice`: Migration guidance
- `X-API-Migration-Guide`: Specific migration instructions

## Priority System

### Priority Ranges
The system uses a 0-1000 priority scale:

- **SYSTEM (900-1000):** Critical system operations
- **URGENT (700-899):** High-priority research experiments  
- **HIGH (500-699):** Important experiments
- **NORMAL (200-499):** Standard experiments
- **LOW (0-199):** Background/cleanup jobs

### Default Priority
Jobs default to priority `100` when not specified.

## Error Handling

### Standard Error Response
```json
{
  "error": "ValidationError",
  "detail": "Priority must be between 0 and 1000",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### HTTP Status Codes
- `200`: Success
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (invalid/missing token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found (job/config/metrics not found)
- `500`: Internal Server Error

## Rate Limiting

Currently no rate limiting is enforced, but this may be added in future versions for production deployments.

## Examples

### List High Priority Jobs
```bash
curl "http://localhost:8000/jobs?priority_min=500&sort_by=priority&sort_order=desc"
```

### Kill a Job (Admin)
```bash
curl -X POST "http://localhost:8000/job/kill" \
  -H "Authorization: Bearer testkey" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "550e8400-e29b-41d4-a716-446655440000"}'
```

### Monitor System Health
```bash
curl "http://localhost:8000/health"
```

### Get Paginated Jobs
```bash
curl "http://localhost:8000/jobs?paginated=true&page=2&per_page=10&job_status=running"
```

## Interactive Documentation

Visit `/docs` for interactive Swagger UI documentation with:
- Complete endpoint specifications
- Request/response models
- Authentication testing
- Example requests

Visit `/redoc` for alternative ReDoc documentation format.