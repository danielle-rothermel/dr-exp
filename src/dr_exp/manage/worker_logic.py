"""Worker utility for executing a single training job."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import traceback
from datetime import datetime, UTC
from typing import Any, Callable, Optional

from dr_exp.logging.structured_logger import StructuredLogger
from dr_exp.utils.jobdb_factory import get_supabase_client
from dr_exp.job_db.base_job_db import BaseJobDB
from dr_exp.train_examples.dummy_trainer import train as default_train


def _heartbeat_loop(
    client: BaseJobDB,
    job_id: str,
    interval: float,
    stop_event: threading.Event,
) -> None:
    """Send heartbeats at a fixed interval until ``stop_event`` is set."""

    while not stop_event.is_set():
        time.sleep(interval)
        client.update_job(job_id, {"heartbeat": datetime.now(UTC).isoformat() + "Z"})


def run_worker(
    base_path: str = "./job_data",
    work_dir: Optional[str] = None,
    max_claim_attempts: int = 5,
    heartbeat_interval: float = 5.0,
    trainer_fn: Callable[[Any, StructuredLogger], dict] = default_train,
    logger_cls: type[StructuredLogger] = StructuredLogger,
    client: Optional[BaseJobDB] = None,
    worker_id: str = "unassigned_worker",
) -> str:
    """Run a single worker iteration.

    Parameters
    ----------
    base_path : str, optional
        Base path for mock database files.
    work_dir : str, optional
        Directory used for temporary work files.
    max_claim_attempts : int, optional
        How many times to poll for a job before giving up.
    heartbeat_interval : float, optional
        Seconds between heartbeat updates.
    trainer_fn : Callable[[Any, StructuredLogger], dict], optional
        Function implementing the training loop.
    logger_cls : type[StructuredLogger], optional
        Logger class to instantiate.
    client : BaseJobDB, optional
        Client to use for job operations.
    worker_id : str, optional
        Identifier used when claiming jobs.

    Returns
    -------
    str
        Final status string.
    """
    client = client or get_supabase_client(base_path=base_path)

    attempt = 0
    backoff = 1.0
    job = None
    while attempt < max_claim_attempts:
        job = client.claim_job(worker_id)
        if job:
            break
        time.sleep(backoff)
        backoff *= 2
        attempt += 1

    if job is None:
        return "no_job"

    job_id = job["id"]
    cfg = client.get_config_for_job(job_id)
    if cfg is None:
        client.record_failure(job_id, "config_missing", "Config not found")
        client.finalize_job(job_id, "failed", {"finalize_success": False})
        return "failed"

    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix=f"worker_{job_id}_")
    os.makedirs(work_dir, exist_ok=True)
    worker_log_path = os.path.join(work_dir, "worker.log")

    cfg.setdefault("logging", {})
    cfg["logging"].update(
        {
            "out_path": os.path.join(work_dir, "metrics.jsonl"),
            "checkpoint_dir": os.path.join(work_dir, "checkpoints"),
            "artifact_dir": os.path.join(work_dir, "artifacts"),
        }
    )

    os.makedirs(cfg["logging"]["checkpoint_dir"], exist_ok=True)
    os.makedirs(cfg["logging"]["artifact_dir"], exist_ok=True)

    logger = logger_cls(cfg)

    stop_event = threading.Event()
    hb_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(client, job_id, heartbeat_interval, stop_event),
        daemon=True,
    )

    with open(worker_log_path, "w") as wlog:
        wlog.write(f"Worker started for job {job_id}\n")
        hb_thread.start()
        try:
            result = trainer_fn(cfg, logger)
            train_status = result.get("status", "success")
        except Exception as e:  # training error
            train_status = "failed"
            stack = traceback.format_exc()
            client.record_failure(job_id, type(e).__name__, str(e), stack)
            wlog.write(stack)
            result = {
                "final_val_acc": None,
                "final_train_loss": None,
                "num_epochs": 0,
                "status": "crash",
            }
        finally:
            stop_event.set()
            hb_thread.join()

    logger_meta = logger.finalize()

    metrics_upload = client.upload_artifact(
        job_id, logger_meta["metrics_path"], "metrics.jsonl"
    )

    bundle_dir = os.path.join(work_dir, "bundle")
    os.makedirs(bundle_dir, exist_ok=True)
    shutil.copytree(
        cfg["logging"]["checkpoint_dir"],
        os.path.join(bundle_dir, "checkpoints"),
    )
    shutil.copytree(
        cfg["logging"]["artifact_dir"],
        os.path.join(bundle_dir, "artifacts"),
    )
    shutil.copy2(worker_log_path, os.path.join(bundle_dir, "worker.log"))

    bundle_zip = shutil.make_archive(
        os.path.join(work_dir, "bundle"), "zip", bundle_dir
    )
    bundle_upload = client.upload_artifact(job_id, bundle_zip, "bundle.zip")

    final_status = "completed" if train_status == "success" else "failed"
    metadata = {
        "final_val_acc": result.get("final_val_acc"),
        "final_train_loss": result.get("final_train_loss"),
        "num_epochs": result.get("num_epochs"),
        "train_status": train_status,
        "metrics_storage_path": metrics_upload.get("storage_path"),
        "bundle_storage_path": bundle_upload.get("storage_path"),
        "upload_complete_at": datetime.now(UTC).isoformat() + "Z",
        "finalize_success": logger_meta.get("finalize_success", False),
    }
    client.finalize_job(job_id, final_status, metadata)

    shutil.rmtree(work_dir, ignore_errors=True)
    return final_status


__all__ = ["run_worker", "default_train"]
