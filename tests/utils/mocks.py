from dr_exp.sync.supabase_client import SupabaseClient
from dr_exp.worker.base import Worker

class MockSupabaseClient(SupabaseClient):
    def __init__(self):
        self.uploaded_files = []
        self.bucket_name = "experiments"
    
    def upload_file(self, local_path, storage_path):
        self.uploaded_files.append((local_path, storage_path))
        return True
    
    def test_connection(self):
        return True

class MockWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_jobs = []
    
    def execute_job(self, job):
        self.executed_jobs.append(job["id"])
        return super().execute_job(job)

def mock_sync_function(item):
    """Mock sync function for testing."""
    return True