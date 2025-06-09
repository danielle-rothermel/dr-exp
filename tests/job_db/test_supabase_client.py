import io
import zipfile
from typing import Dict, Any, Optional

import pytest

from dr_exp.job_db import SupabaseJobDB, JobDBConfig


class StubBucket:
    def __init__(self, recorder: Dict[str, Any]) -> None:
        self.recorder = recorder

    def upload(self, file: Any, path: str, file_options: Dict[str, Any]) -> None:
        self.recorder["content"] = file.read()
        self.recorder["path"] = path
        self.recorder["options"] = file_options


class StubStorage:
    def __init__(self, recorder: Dict[str, Any]) -> None:
        self.recorder = recorder

    def from_(self, _bucket: str) -> StubBucket:
        return StubBucket(self.recorder)


class StubClient:
    def __init__(self, recorder: Dict[str, Any]) -> None:
        self.storage = StubStorage(recorder)
        self.recorder = recorder
        self.last_table: Optional[str] = None

    def table(self, name: str) -> "StubTable":
        self.last_table = name
        return StubTable(name, self.recorder)


class StubTable:
    def __init__(self, name: str, recorder: Dict[str, Any]) -> None:
        self.name = name
        self.recorder = recorder
        self.data: Optional[Dict[str, Any]] = None

    def insert(self, data: Dict[str, Any]) -> "StubTable":
        self.recorder.setdefault("tables", []).append((self.name, data))
        self.data = data
        return self

    def execute(self) -> Any:
        return type("Resp", (), {"data": [self.data]})()


@pytest.fixture
def stub_client(monkeypatch: Any) -> Dict[str, Any]:
    recorder: Dict[str, Any] = {}
    client = StubClient(recorder)
    monkeypatch.setattr(
        "dr_exp.job_db.supabase_job_db.create_client",
        lambda url, key: client,
    )
    return recorder


def test_directory_is_zipped(tmp_path: Any, stub_client: Dict[str, Any]) -> None:
    config = JobDBConfig(
        base_path=str(tmp_path),
        mode="supabase_remote",
        storage_path=str(tmp_path / "storage"),
        supabase_url="https://test.supabase.co",
        supabase_key="key",
    )
    client = SupabaseJobDB(config)
    d = tmp_path / "artifacts"
    d.mkdir()
    (d / "file.txt").write_text("data")
    result = client.upload_artifact("jid", str(d), "my_dir")
    assert result["success"] is True
    assert stub_client["path"] == "run_jid/artifacts/my_dir.zip"
    z = zipfile.ZipFile(io.BytesIO(stub_client["content"]))
    assert z.namelist() == ["file.txt"]


def test_empty_suffix_zips_to_default(
    tmp_path: Any, stub_client: Dict[str, Any]
) -> None:
    config = JobDBConfig(
        base_path=str(tmp_path),
        mode="supabase_remote",
        storage_path=str(tmp_path / "storage"),
        supabase_url="https://test.supabase.co",
        supabase_key="key",
    )
    client = SupabaseJobDB(config)
    d = tmp_path / "artifacts2"
    d.mkdir()
    (d / "a.txt").write_text("a")
    result = client.upload_artifact("jid2", str(d), "")
    assert result["success"] is True
    assert stub_client["path"] == "run_jid2/artifacts.zip"
    z = zipfile.ZipFile(io.BytesIO(stub_client["content"]))
    assert z.namelist() == ["a.txt"]


def test_insert_helpers(monkeypatch: Any, stub_client: Dict[str, Any]) -> None:
    config = JobDBConfig(
        base_path="/tmp",
        mode="supabase_remote",
        storage_path="/tmp/storage",
        supabase_url="https://test.supabase.co",
        supabase_key="key",
    )
    client = SupabaseJobDB(config)

    result = client.add_sweep_config_cluster("c1", description="d")
    assert stub_client["tables"][0] == (
        "sweep_config_clusters",
        {"name": "c1", "description": "d"},
    )
    assert result == {"name": "c1", "description": "d"}

    result = client.add_sweep_config("cid", {"a": 1}, "hash", interface_version="1")
    assert stub_client["tables"][1][0] == "sweep_configs"
    assert result["cluster_id"] == "cid"

    result = client.add_job_entry("cid", status="queued")
    assert stub_client["tables"][2][0] == "jobs"
    assert result["config_id"] == "cid"


def test_write_finished_flag(tmp_path: Any, stub_client: Dict[str, Any]) -> None:
    config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        supabase_url="https://test.supabase.co",
        supabase_key="key",
        mode="supabase_remote",
    )
    client = SupabaseJobDB(config)
    job_id = "jid3"
    client._write_finished_flag(job_id)
    # Flag is now written to storage_dir (unified behavior)
    flag_path = tmp_path / "storage" / f"run_{job_id}" / "finished.flag"
    assert flag_path.exists()
