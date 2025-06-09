"""Tests for job listing pagination and filtering."""

from typing import Any

from .conftest import create_test_job, Priority, JobStatus


def test_pagination_basic(client: Any, db_client: Any) -> None:
    """Test basic pagination functionality."""
    # Create 25 test jobs
    jobs = []
    for i in range(25):
        job = create_test_job(
            db_client,
            job_config={"index": i},
            sweep_config_id=f"sweep{i}",
            priority=100 + i,  # Varying priorities for sorting
        )
        jobs.append(job)

    # Test non-paginated response (default)
    resp = client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 25

    # Test paginated response - first page
    resp = client.get("/jobs?paginated=true&page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.json()

    # Check pagination metadata
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["pages"] == 3
    assert data["has_next"] is True
    assert data["has_prev"] is False
    assert len(data["jobs"]) == 10

    # Test second page
    resp = client.get("/jobs?paginated=true&page=2&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["has_next"] is True
    assert data["has_prev"] is True
    assert len(data["jobs"]) == 10

    # Test last page
    resp = client.get("/jobs?paginated=true&page=3&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 3
    assert data["has_next"] is False
    assert data["has_prev"] is True
    assert len(data["jobs"]) == 5  # Remaining jobs


def test_pagination_edge_cases(client: Any, db_client: Any) -> None:
    """Test pagination edge cases and validation."""
    # Create a few jobs for testing
    for i in range(5):
        create_test_job(db_client, sweep_config_id=f"sweep{i}")

    # Test page 0 (invalid)
    resp = client.get("/jobs?paginated=true&page=0")
    assert resp.status_code == 400

    # Test negative page
    resp = client.get("/jobs?paginated=true&page=-1")
    assert resp.status_code == 400

    # Test per_page too large
    resp = client.get("/jobs?paginated=true&per_page=101")
    assert resp.status_code == 400

    # Test per_page zero
    resp = client.get("/jobs?paginated=true&per_page=0")
    assert resp.status_code == 400

    # Test page beyond available data
    resp = client.get("/jobs?paginated=true&page=10&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["jobs"]) == 0
    assert data["pages"] == 1


def test_pagination_with_filtering(client: Any, db_client: Any) -> None:
    """Test pagination combined with filtering."""
    # Create jobs with different statuses
    _queued_jobs = [
        create_test_job(
            db_client, status=JobStatus.QUEUED, sweep_config_id=f"queued{i}"
        )
        for i in range(15)
    ]
    _running_jobs = [
        create_test_job(
            db_client, status=JobStatus.RUNNING, sweep_config_id=f"running{i}"
        )
        for i in range(10)
    ]

    # Test paginated filtering by status
    resp = client.get("/jobs?paginated=true&job_status=queued&page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 15  # Only queued jobs
    assert data["pages"] == 2  # 15 jobs / 10 per page = 2 pages
    assert len(data["jobs"]) == 10
    assert all(job["status"] == JobStatus.QUEUED for job in data["jobs"])

    # Test second page of filtered results
    resp = client.get("/jobs?paginated=true&job_status=queued&page=2&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert len(data["jobs"]) == 5  # Remaining queued jobs
    assert all(job["status"] == JobStatus.QUEUED for job in data["jobs"])


def test_pagination_with_sorting(client: Any, db_client: Any) -> None:
    """Test pagination combined with sorting."""
    # Create jobs with varying priorities
    priorities = [Priority.LOW, Priority.HIGH, Priority.NORMAL, Priority.URGENT]
    jobs = []
    for i, priority in enumerate(priorities):
        job = create_test_job(
            db_client,
            priority=priority,
            sweep_config_id=f"job{i}",
            job_config={"priority_value": priority},
        )
        jobs.append(job)

    # Test pagination with sorting by priority (descending)
    resp = client.get(
        "/jobs?paginated=true&sort_by=priority&sort_order=desc&page=1&per_page=2"
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 4
    assert data["pages"] == 2
    assert len(data["jobs"]) == 2

    # Should be highest priorities first
    priorities_returned = [job["priority"] for job in data["jobs"]]
    assert priorities_returned == [Priority.URGENT, Priority.HIGH]

    # Test second page
    resp = client.get(
        "/jobs?paginated=true&sort_by=priority&sort_order=desc&page=2&per_page=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["jobs"]) == 2
    priorities_returned = [job["priority"] for job in data["jobs"]]
    assert priorities_returned == [Priority.NORMAL, Priority.LOW]


def test_pagination_with_complex_filtering(client: Any, db_client: Any) -> None:
    """Test pagination with multiple filters."""
    # Create jobs with varying priorities and statuses
    test_jobs = [
        {"priority": Priority.LOW, "status": JobStatus.QUEUED},
        {"priority": Priority.NORMAL, "status": JobStatus.QUEUED},
        {"priority": Priority.HIGH, "status": JobStatus.QUEUED},
        {"priority": Priority.LOW, "status": JobStatus.RUNNING},
        {"priority": Priority.HIGH, "status": JobStatus.RUNNING},
        {"priority": Priority.URGENT, "status": JobStatus.COMPLETED},
    ]

    for i, job_params in enumerate(test_jobs):
        create_test_job(db_client, sweep_config_id=f"complex{i}", **job_params)

    # Test filtering by status and priority range with pagination
    resp = client.get(
        "/jobs?paginated=true"
        "&job_status=queued"
        "&priority_min=200"  # Normal and above
        "&sort_by=priority"
        "&sort_order=desc"
        "&page=1&per_page=2"
    )
    assert resp.status_code == 200
    data = resp.json()

    # Should find 2 queued jobs with priority >= 200 (NORMAL and HIGH)
    assert data["total"] == 2
    assert data["pages"] == 1
    assert len(data["jobs"]) == 2

    for job in data["jobs"]:
        assert job["status"] == JobStatus.QUEUED
        assert job["priority"] >= 200

    # Should be sorted by priority descending
    priorities = [job["priority"] for job in data["jobs"]]
    assert priorities == [Priority.HIGH, Priority.NORMAL]


def test_empty_pagination_results(client: Any, db_client: Any) -> None:
    """Test pagination when filters return no results."""
    # Create a few jobs
    create_test_job(db_client, status=JobStatus.QUEUED)
    create_test_job(db_client, status=JobStatus.RUNNING)

    # Filter for status that doesn't exist
    resp = client.get("/jobs?paginated=true&job_status=completed")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 0
    assert data["pages"] == 0
    assert len(data["jobs"]) == 0
    assert data["has_next"] is False
    assert data["has_prev"] is False


def test_pagination_per_page_limits(client: Any, db_client: Any) -> None:
    """Test per_page parameter limits."""
    # Create some jobs
    for i in range(5):
        create_test_job(db_client, sweep_config_id=f"limit{i}")

    # Test minimum per_page (1)
    resp = client.get("/jobs?paginated=true&per_page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["per_page"] == 1
    assert len(data["jobs"]) == 1
    assert data["pages"] == 5

    # Test maximum per_page (100)
    resp = client.get("/jobs?paginated=true&per_page=100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["per_page"] == 100
    assert len(data["jobs"]) == 5  # All jobs fit in one page
    assert data["pages"] == 1

    # Test default per_page (20)
    resp = client.get("/jobs?paginated=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["per_page"] == 20
