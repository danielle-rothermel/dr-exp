"""Tests for WebSocket real-time communication."""

import json
import pytest
from fastapi.testclient import TestClient
from .conftest import create_test_job, Priority, JobStatus


def test_websocket_connection_basic(client):
    """Test basic WebSocket connection establishment."""
    with client.websocket_connect("/ws") as websocket:
        # Send a test message
        websocket.send_text("test message")
        
        # Receive the echo
        data = websocket.receive_text()
        assert "Echo: test message" in data


def test_websocket_connection_lifecycle(client):
    """Test WebSocket connection and disconnection."""
    # Test that we can establish multiple connections
    with client.websocket_connect("/ws") as ws1:
        with client.websocket_connect("/ws") as ws2:
            ws1.send_text("message1")
            ws2.send_text("message2")
            
            response1 = ws1.receive_text()
            response2 = ws2.receive_text()
            
            assert "message1" in response1
            assert "message2" in response2


def test_websocket_invalid_json(client):
    """Test WebSocket handling of invalid JSON."""
    with client.websocket_connect("/ws") as websocket:
        # Send invalid JSON
        websocket.send_text("invalid json {")
        
        # Should still echo the message
        data = websocket.receive_text()
        assert "invalid json" in data


def test_websocket_empty_message(client):
    """Test WebSocket handling of empty messages."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("")
        
        data = websocket.receive_text()
        assert "Echo:" in data


def test_websocket_large_message(client):
    """Test WebSocket handling of large messages."""
    with client.websocket_connect("/ws") as websocket:
        large_message = "x" * 10000  # 10KB message
        websocket.send_text(large_message)
        
        data = websocket.receive_text()
        assert large_message in data


def test_websocket_json_message(client):
    """Test WebSocket handling of JSON messages."""
    with client.websocket_connect("/ws") as websocket:
        test_data = {"type": "test", "data": {"key": "value"}}
        websocket.send_text(json.dumps(test_data))
        
        response = websocket.receive_text()
        assert json.dumps(test_data) in response


def test_websocket_concurrent_connections(client):
    """Test multiple concurrent WebSocket connections."""
    connections = []
    
    try:
        # Establish multiple connections
        for i in range(5):
            ws = client.websocket_connect("/ws")
            connection = ws.__enter__()
            connections.append((ws, connection))
        
        # Send messages from each connection
        for i, (_, connection) in enumerate(connections):
            connection.send_text(f"message from connection {i}")
        
        # Verify each gets their own echo
        for i, (_, connection) in enumerate(connections):
            response = connection.receive_text()
            assert f"message from connection {i}" in response
            
    finally:
        # Clean up all connections
        for ws, _ in connections:
            try:
                ws.__exit__(None, None, None)
            except:
                pass  # Connection might already be closed


def test_websocket_connection_manager_state(client):
    """Test that WebSocket connection manager tracks connections properly."""
    # This is more of an integration test to ensure the ConnectionManager
    # is working correctly under the hood
    
    # Start with no connections (we can't directly access the manager,
    # but we can test behavior that depends on it)
    
    connection_count_before = 0  # We'd need to expose this for real testing
    
    with client.websocket_connect("/ws") as ws1:
        # Connection should be tracked
        ws1.send_text("test")
        response = ws1.receive_text()
        assert "test" in response
        
        with client.websocket_connect("/ws") as ws2:
            # Both connections should work independently
            ws2.send_text("test2")
            response2 = ws2.receive_text()
            assert "test2" in response2
            
            # First connection should still work
            ws1.send_text("test3")
            response3 = ws1.receive_text()
            assert "test3" in response3
    
    # After context managers exit, connections should be cleaned up
    # (We can't directly test this without exposing the connection manager)


@pytest.mark.skip(reason="Broadcasting not fully implemented in echo-only WebSocket")
def test_websocket_broadcast_message(client, db_client, admin_headers):
    """Test WebSocket broadcasting when job priorities change."""
    # This test would verify real broadcasting functionality
    # Currently skipped because the WebSocket only echoes messages
    
    job = create_test_job(db_client, priority=Priority.NORMAL)
    job_id = job["id"]
    
    with client.websocket_connect("/ws") as websocket:
        # Boost job priority via API
        resp = client.post(
            "/job/boost-priority",
            json={"job_id": job_id, "boost_amount": 100},
            headers=admin_headers
        )
        assert resp.status_code == 200
        
        # Should receive broadcast message about priority change
        # (This would require implementing actual broadcasting)
        data = websocket.receive_text()
        message = json.loads(data)
        
        assert message["type"] == "job_update"
        assert message["job_id"] == job_id
        assert message["action"] == "priority_boosted"
        assert message["new_priority"] == Priority.NORMAL + 100


@pytest.mark.skip(reason="Broadcasting not fully implemented in echo-only WebSocket")
def test_websocket_job_status_broadcast(client, db_client, admin_headers):
    """Test WebSocket broadcasting for job status changes."""
    # This test would verify job status change broadcasts
    
    job = create_test_job(db_client, status=JobStatus.FAILED)
    job_id = job["id"]
    
    with client.websocket_connect("/ws") as websocket:
        # Requeue job via API
        resp = client.post(
            "/job/requeue",
            json={"job_id": job_id},
            headers=admin_headers
        )
        assert resp.status_code == 200
        
        # Should receive broadcast about job requeue
        data = websocket.receive_text()
        message = json.loads(data)
        
        assert message["type"] == "job_update"
        assert message["job_id"] == job_id
        assert message["action"] == "requeued"


def test_websocket_connection_close_handling(client):
    """Test graceful handling of WebSocket connection closure."""
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("test before close")
        response = websocket.receive_text()
        assert "test before close" in response
        
        # WebSocket will be closed when exiting context manager
        # The connection manager should handle this gracefully
    
    # Verify we can establish a new connection after the previous one closed
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("test after reconnect")
        response = websocket.receive_text()
        assert "test after reconnect" in response