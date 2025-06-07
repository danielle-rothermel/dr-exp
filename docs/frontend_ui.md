# Frontend Babysitter UI Specification (`docs/frontend_ui.md`)

## Purpose

The React-based Babysitter UI provides real-time visibility and control over experiment execution through a comprehensive API integration. It displays the status of all jobs with advanced filtering and pagination, shows real-time updates via WebSocket connections, allows authenticated control actions (kill, requeue, priority management), and provides comprehensive experiment monitoring capabilities.

It is designed to support researchers in monitoring and debugging sweeps, triaging failures, managing experiment priorities, and understanding optimization dynamics at scale.

---

## Responsibilities

* Display all jobs with real-time status updates via WebSocket integration
* Provide advanced filtering by status, priority ranges, and other job attributes
* Support pagination for efficient handling of large job datasets  
* Render live metric plots and scalar summaries from API endpoints
* Display job configurations, logs, and artifact previews
* Enable authenticated control actions (kill, requeue, priority management)
* Show priority-based job ordering and queue management
* Provide system health monitoring and API status information
* Support role-based access control (admin vs reader permissions)

---

## Major Views / Components

### 1. **Job Table View**

* Paginated job listing with configurable items per page (1-100)
* Advanced filtering by status, priority ranges, and job attributes
* Sortable columns by priority, creation time, status, and retry count
* Real-time status updates via WebSocket connections
* Priority-based coloring and visual indicators
* Click-to-expand drawer showing full config and metadata
* Bulk operations for selected jobs (admin only)

### 2. **Job Detail Page**

* Live metric plots with configurable data limits (up to 500 points)
* Real-time metric streaming via API endpoints
* Job configuration display with syntax highlighting
* Training logs, error tracebacks, and artifact browser
* Priority management controls (boost/set priority with admin auth)
* Job control actions: requeue, kill (requires authentication)
* Retry history and lineage tracking

### 3. **System Dashboard**

* System health status and API connectivity monitoring
* Active job statistics by status (queued, running, completed, failed)
* Queue depth and processing rate metrics
* WebSocket connection status and real-time update indicators
* API performance metrics and response times

### 4. **Priority Management Panel** (Admin Only)

* Priority queue visualization with job ordering
* Bulk priority adjustment tools
* Priority boost history and audit trail
* Queue management and job reservation controls

---

## Backend Integration

The UI integrates with the comprehensive FastAPI backend through:

### Core API Endpoints

* **Job Management:**
  - `GET /jobs` - Paginated job listing with filtering and sorting
  - `GET /job/{id}` - Detailed job information and status
  - `GET /config/{id}` - Job configuration and parameters
  - `GET /metrics/{run_id}` - Training metrics with configurable limits

* **Administrative Operations (Require Authentication):**
  - `POST /job/kill` - Terminate running jobs
  - `POST /job/requeue` - Restart failed jobs
  - `POST /job/boost-priority` - Increase job priority
  - `POST /job/set-priority` - Set absolute priority levels

* **System Monitoring:**
  - `GET /health` - API health status and system information
  - `GET /metrics` - System metrics and job statistics
  - `GET /api` - API version and endpoint information

### Real-time Communication

* **WebSocket Connection:** `WS /ws`
  - Real-time job status updates
  - Priority change notifications
  - System alerts and job completion events
  - Connection management with automatic reconnection

### Authentication Integration

* **Bearer Token Authentication:**
  - Admin role: Full access to all operations
  - Reader role: Read-only access to job data
  - Secure token storage and automatic header injection
  - Role-based UI component visibility

### Response Handling

* **Standardized Error Responses:** Consistent error format across all endpoints
* **Pagination Metadata:** Page information for efficient data loading
* **Performance Headers:** Request timing information for optimization
* **API Version Headers:** Deprecation notices and migration guidance

For complete API specification, see `docs/api_reference.md`.

---

## Authentication

### Bearer Token Authentication

* **Admin Access:** Full permissions for job control and priority management
  - Default development token: `testkey` (set via `ADMIN_API_KEY`)
  - Can kill jobs, requeue jobs, and modify priorities
  - Access to all system administration features

* **Reader Access:** Read-only access to job data and metrics
  - Default development token: `readkey` (set via `READER_API_KEY`)
  - Can view jobs, configurations, and metrics
  - Cannot perform administrative operations

### Token Management

* Secure token storage in browser session/localStorage
* Automatic Bearer header injection for authenticated requests
* Token validation with clear error messages
* Role-based UI component rendering (hide admin features for readers)

### Development Setup

```bash
# Set API keys for development
export ADMIN_API_KEY=testkey
export READER_API_KEY=readkey
```

For production deployments, use secure token generation and proper key management.

---

## Deployment Notes

### Frontend Deployment

* UI is deployed via Netlify, Vercel, or static server
* Built with React 19, Vite build system, and TailwindCSS v4
* Environment-specific API endpoint configuration
* Secure token storage in browser session/localStorage

### API Integration

* **Development:** API at `http://localhost:8000`
* **Production:** Configure API endpoint via environment variables
* **WebSocket:** Automatic fallback to polling if WebSocket unavailable
* **CORS:** Properly configured for frontend domain access

### Performance Considerations

* Pagination for large job datasets (configurable page sizes)
* Efficient WebSocket connection management
* Optimized metric data loading with configurable limits
* Request timing monitoring via performance headers

### Monitoring Integration

* Real-time API health status display
* WebSocket connection status indicators
* Performance metrics and response time tracking
* Error boundary handling for graceful degradation

---

