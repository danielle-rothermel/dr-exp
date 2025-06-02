import io
import zipfile

import pytest

from dr_exp.core.supabase_client import SupabaseClient


class StubBucket:
    def __init__(self, recorder):
        self.recorder = recorder

    def upload(self, file, path, file_options):
        self.recorder["content"] = file.read()
        self.recorder["path"] = path
        self.recorder["options"] = file_options
        return None


class StubStorage:
    def __init__(self, recorder):
        self.recorder = recorder

    def from_(self, _bucket):
        return StubBucket(self.recorder)


class StubClient:
    def __init__(self, recorder):
        self.storage = StubStorage(recorder)


@pytest.fixture
def stub_client(monkeypatch):
    recorder = {}
    client = StubClient(recorder)
    monkeypatch.setattr(
        "dr_exp.core.supabase_client.create_client",
        lambda url, key: client,
    )
    return recorder


def test_directory_is_zipped(tmp_path, stub_client):
    client = SupabaseClient("url", "key")
    d = tmp_path / "artifacts"
    d.mkdir()
    (d / "file.txt").write_text("data")
    result = client.upload_artifact("jid", str(d), "my_dir")
    assert result["success"] is True
    assert stub_client["path"] == "run_jid/artifacts/my_dir.zip"
    z = zipfile.ZipFile(io.BytesIO(stub_client["content"]))
    assert z.namelist() == ["file.txt"]


def test_empty_suffix_zips_to_default(tmp_path, stub_client):
    client = SupabaseClient("url", "key")
    d = tmp_path / "artifacts2"
    d.mkdir()
    (d / "a.txt").write_text("a")
    result = client.upload_artifact("jid2", str(d), "")
    assert result["success"] is True
    assert stub_client["path"] == "run_jid2/artifacts.zip"
    z = zipfile.ZipFile(io.BytesIO(stub_client["content"]))
    assert z.namelist() == ["a.txt"]
