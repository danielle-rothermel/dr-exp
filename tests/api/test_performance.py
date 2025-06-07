"""Tests for API performance and concurrent access patterns."""

import time
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from .conftest import create_test_job, create_multiple_jobs, Priority, JobStatus


def test_response_time_benchmarks(client):
    """Test that API response times are within acceptable limits."""
    endpoints_with_limits = [
        ("/health", 1.0),      # Health check should be very fast
        ("/metrics", 2.0),     # System metrics should be fast
        ("/api", 1.0),         # API info should be fast
        ("/jobs", 3.0),        # Job listing might be slower
    ]
    
    for endpoint, max_time in endpoints_with_limits:
        start_time = time.time()
        resp = client.get(endpoint)
        end_time = time.time()
        
        assert resp.status_code == 200
        response_time = end_time - start_time
        assert response_time < max_time, f"{endpoint} took {response_time:.3f}s (limit: {max_time}s)"


def test_concurrent_read_operations(client, db_client):
    """Test concurrent read operations don't interfere with each other."""
    # Create some test data
    jobs = []
    for i in range(10):
        job = create_test_job(db_client, sweep_config_id=f"concurrent_read_{i}")
        jobs.append(job)
    
    results = []
    errors = []
    
    def read_jobs(thread_id):
        """Read jobs from a separate thread."""
        try:
            start_time = time.time()
            resp = client.get("/jobs")
            end_time = time.time()
            
            results.append({
                "thread_id": thread_id,
                "status_code": resp.status_code,
                "job_count": len(resp.json()) if resp.status_code == 200 else 0,
                "response_time": end_time - start_time
            })
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Launch concurrent read operations
    threads = []
    for i in range(20):
        thread = threading.Thread(target=read_jobs, args=(i,))
        threads.append(thread)
    
    # Start all threads
    start_time = time.time()
    for thread in threads:
        thread.start()
    
    # Wait for all to complete
    for thread in threads:
        thread.join(timeout=30)
    end_time = time.time()
    
    # Analyze results
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 20
    
    # All requests should succeed
    for result in results:
        assert result["status_code"] == 200
        assert result["job_count"] >= 10  # Should see at least our test jobs
        assert result["response_time"] < 5.0  # Individual requests should be fast
    
    # Total time should be reasonable (concurrent execution)
    total_time = end_time - start_time
    assert total_time < 10.0, f"Concurrent reads took too long: {total_time:.3f}s"


def test_concurrent_write_operations(client, db_client, admin_headers):
    """Test concurrent write operations handle contention properly."""
    # Create jobs for modification
    jobs = []
    for i in range(5):
        job = create_test_job(db_client, priority=Priority.NORMAL)
        jobs.append(job)
    
    results = []
    errors = []
    
    def boost_priority(thread_id, job_id):
        """Boost job priority from a separate thread."""
        try:
            start_time = time.time()
            resp = client.post(
                "/job/boost-priority",
                json={"job_id": job_id, "boost_amount": 10},
                headers=admin_headers
            )
            end_time = time.time()
            
            results.append({
                "thread_id": thread_id,
                "job_id": job_id,
                "status_code": resp.status_code,
                "response_time": end_time - start_time,
                "response": resp.json() if resp.status_code == 200 else None
            })
        except Exception as e:
            errors.append((thread_id, job_id, str(e)))
    
    # Launch concurrent write operations on different jobs
    threads = []
    for i, job in enumerate(jobs):
        for j in range(3):  # 3 concurrent boosts per job
            thread_id = i * 3 + j
            thread = threading.Thread(target=boost_priority, args=(thread_id, job["id"]))
            threads.append(thread)
    
    # Start all threads
    start_time = time.time()
    for thread in threads:
        thread.start()
    
    # Wait for all to complete
    for thread in threads:
        thread.join(timeout=30)
    end_time = time.time()
    
    # Analyze results
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 15  # 5 jobs * 3 operations each
    
    # All operations should complete
    successful_operations = [r for r in results if r["status_code"] == 200]
    assert len(successful_operations) == 15
    
    # Each operation should be reasonably fast
    for result in results:
        assert result["response_time"] < 5.0


def test_load_testing_job_creation(client, db_client):
    """Test system behavior under job creation load."""
    def create_job_batch(batch_id, batch_size=10):
        """Create a batch of jobs."""
        batch_jobs = []
        for i in range(batch_size):
            job = create_test_job(
                db_client,
                job_config={"batch_id": batch_id, "job_index": i},
                sweep_config_id=f"load_test_batch_{batch_id}_{i}"
            )
            batch_jobs.append(job)
        return batch_jobs
    
    # Create jobs in parallel batches
    with ThreadPoolExecutor(max_workers=5) as executor:
        start_time = time.time()
        
        # Submit batch creation tasks
        futures = []
        for batch_id in range(10):
            future = executor.submit(create_job_batch, batch_id, 5)
            futures.append(future)
        
        # Wait for all batches to complete
        all_jobs = []
        for future in as_completed(futures):
            batch_jobs = future.result()
            all_jobs.extend(batch_jobs)
        
        end_time = time.time()
    
    # Verify results
    assert len(all_jobs) == 50  # 10 batches * 5 jobs each
    total_time = end_time - start_time
    assert total_time < 30.0, f"Job creation took too long: {total_time:.3f}s"
    
    # Verify all jobs are accessible
    resp = client.get("/jobs")
    assert resp.status_code == 200
    job_list = resp.json()
    assert len(job_list) >= 50


def test_pagination_performance_with_large_dataset(client, db_client):
    """Test pagination performance with a larger dataset."""
    # Create a substantial number of jobs
    jobs = create_multiple_jobs(
        db_client,
        count=100,
        status_distribution={
            JobStatus.QUEUED: 0.4,
            JobStatus.RUNNING: 0.3,
            JobStatus.COMPLETED: 0.2,
            JobStatus.FAILED: 0.1
        }
    )
    
    # Test different pagination scenarios
    pagination_tests = [
        {"per_page": 10, "expected_pages": 10},
        {"per_page": 25, "expected_pages": 4},
        {"per_page": 50, "expected_pages": 2},
        {"per_page": 100, "expected_pages": 1},
    ]
    
    for test_case in pagination_tests:
        start_time = time.time()
        
        # Get first page
        resp = client.get(f"/jobs?paginated=true&per_page={test_case['per_page']}")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data["total"] >= 100
        assert data["pages"] >= test_case["expected_pages"]
        
        end_time = time.time()
        response_time = end_time - start_time
        
        # Pagination should be fast even with large datasets
        assert response_time < 3.0, f"Pagination too slow for per_page={test_case['per_page']}: {response_time:.3f}s"


def test_filtering_performance(client, db_client):
    """Test performance of filtering operations on large datasets."""
    # Create jobs with various statuses and priorities
    jobs = create_multiple_jobs(db_client, count=200)
    
    # Test different filtering scenarios
    filter_tests = [
        "/jobs?job_status=queued",
        "/jobs?job_status=running",
        "/jobs?priority_min=300",
        "/jobs?priority_max=200",
        "/jobs?priority_min=100&priority_max=400",
        "/jobs?job_status=queued&priority_min=200",
        "/jobs?paginated=true&job_status=running&sort_by=priority&sort_order=desc",
    ]
    
    for filter_url in filter_tests:
        start_time = time.time()
        resp = client.get(filter_url)
        end_time = time.time()
        
        assert resp.status_code == 200
        response_time = end_time - start_time
        
        # Filtering should be reasonably fast
        assert response_time < 5.0, f"Filtering too slow for {filter_url}: {response_time:.3f}s"


def test_memory_usage_stability(client, db_client):
    """Test that repeated operations don't cause memory leaks."""
    import gc
    import sys
    
    # Get baseline memory usage (approximate)
    gc.collect()
    
    # Perform many operations
    for i in range(50):
        # Create job
        job = create_test_job(db_client, sweep_config_id=f"memory_test_{i}")
        
        # Read job
        resp = client.get(f"/job/{job['id']}")
        assert resp.status_code == 200
        
        # List jobs
        resp = client.get("/jobs")
        assert resp.status_code == 200
        
        # Health check
        resp = client.get("/health")
        assert resp.status_code == 200
        
        # Force garbage collection periodically
        if i % 10 == 0:
            gc.collect()
    
    # Final cleanup
    gc.collect()
    
    # This test mainly ensures we don't crash or hang
    # Detailed memory analysis would require more sophisticated tools


def test_rate_limiting_behavior(client):
    """Test behavior under rapid successive requests."""
    def make_rapid_requests(request_count=50):
        """Make rapid successive requests."""
        start_time = time.time()
        response_times = []
        status_codes = []
        
        for i in range(request_count):
            req_start = time.time()
            resp = client.get("/health")
            req_end = time.time()
            
            status_codes.append(resp.status_code)
            response_times.append(req_end - req_start)
        
        end_time = time.time()
        return {
            "total_time": end_time - start_time,
            "response_times": response_times,
            "status_codes": status_codes
        }
    
    results = make_rapid_requests(30)
    
    # All requests should succeed (no rate limiting in test environment)
    assert all(code == 200 for code in results["status_codes"])
    
    # Individual requests should remain fast under load
    avg_response_time = sum(results["response_times"]) / len(results["response_times"])
    max_response_time = max(results["response_times"])
    
    assert avg_response_time < 0.5, f"Average response time too high: {avg_response_time:.3f}s"
    assert max_response_time < 2.0, f"Slowest response too slow: {max_response_time:.3f}s"


def test_database_connection_pooling(client, db_client):
    """Test that database connections are handled efficiently."""
    def database_intensive_operation(operation_id):
        """Perform database-intensive operations."""
        results = []
        
        # Create multiple jobs
        for i in range(5):
            job = create_test_job(
                db_client,
                sweep_config_id=f"db_test_{operation_id}_{i}"
            )
            results.append(job["id"])
        
        # Read all jobs multiple times
        for i in range(3):
            resp = client.get("/jobs")
            assert resp.status_code == 200
            job_count = len(resp.json())
            results.append(job_count)
        
        return results
    
    # Run multiple database-intensive operations concurrently
    with ThreadPoolExecutor(max_workers=8) as executor:
        start_time = time.time()
        
        futures = []
        for op_id in range(10):
            future = executor.submit(database_intensive_operation, op_id)
            futures.append(future)
        
        # Wait for all operations to complete
        all_results = []
        for future in as_completed(futures):
            result = future.result()
            all_results.extend(result)
        
        end_time = time.time()
    
    # Should complete without errors
    total_time = end_time - start_time
    assert total_time < 60.0, f"Database operations took too long: {total_time:.3f}s"
    
    # Should have processed all operations
    assert len(all_results) > 0


def test_error_handling_under_load(client, admin_headers):
    """Test that error handling remains robust under load."""
    def make_failing_request(request_id):
        """Make a request that should fail."""
        fake_job_id = f"fake-job-{request_id}"
        resp = client.post(
            "/job/kill",
            json={"job_id": fake_job_id},
            headers=admin_headers
        )
        return resp.status_code
    
    # Make many failing requests concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        start_time = time.time()
        
        futures = []
        for req_id in range(50):
            future = executor.submit(make_failing_request, req_id)
            futures.append(future)
        
        # Collect all responses
        status_codes = []
        for future in as_completed(futures):
            status_code = future.result()
            status_codes.append(status_code)
        
        end_time = time.time()
    
    # All should return appropriate error codes (404 for non-existent job)
    assert all(code in [400, 404] for code in status_codes)
    
    # Should handle errors efficiently
    total_time = end_time - start_time
    assert total_time < 20.0, f"Error handling took too long: {total_time:.3f}s"