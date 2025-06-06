"""Tests for the LoggerPathManager and LoggerPathConfig."""

import os
import pytest

from dr_exp.logging.logger_paths import LoggerPathConfig, LoggerPathManager


def test_logger_path_config_defaults():
    """Test LoggerPathConfig default values."""
    config = LoggerPathConfig(base_dir="/tmp/logs")
    assert config.base_dir == "/tmp/logs"
    assert config.metrics_filename == "metrics.jsonl"
    assert config.checkpoint_dir == "checkpoints"
    assert config.artifact_dir == "artifacts"
    assert config.error_filename == "errors.log"


def test_logger_path_config_custom():
    """Test LoggerPathConfig with custom values."""
    config = LoggerPathConfig(
        base_dir="/custom/logs",
        metrics_filename="custom_metrics.json",
        checkpoint_dir="models",
        artifact_dir="outputs",
        error_filename="error_log.txt"
    )
    assert config.base_dir == "/custom/logs"
    assert config.metrics_filename == "custom_metrics.json"
    assert config.checkpoint_dir == "models"
    assert config.artifact_dir == "outputs"
    assert config.error_filename == "error_log.txt"


def test_logger_path_manager_from_string(tmp_path):
    """Test LoggerPathManager initialization from string."""
    log_dir = str(tmp_path / "logs")
    manager = LoggerPathManager(log_dir)
    
    assert manager.base_dir == log_dir
    assert manager.metrics_path == os.path.join(log_dir, "metrics.jsonl")
    assert manager.checkpoint_dir == os.path.join(log_dir, "checkpoints")
    assert manager.artifact_dir == os.path.join(log_dir, "artifacts")
    assert manager.error_log_path == os.path.join(log_dir, "errors.log")


def test_logger_path_manager_from_config(tmp_path):
    """Test LoggerPathManager initialization from LoggerPathConfig."""
    config = LoggerPathConfig(
        base_dir=str(tmp_path / "logs"),
        metrics_filename="test.jsonl",
        checkpoint_dir="ckpts",
        artifact_dir="arts",
        error_filename="test_errors.log"
    )
    manager = LoggerPathManager(config)
    
    base = str(tmp_path / "logs")
    assert manager.base_dir == base
    assert manager.metrics_path == os.path.join(base, "test.jsonl")
    assert manager.checkpoint_dir == os.path.join(base, "ckpts")
    assert manager.artifact_dir == os.path.join(base, "arts")
    assert manager.error_log_path == os.path.join(base, "test_errors.log")


def test_logger_path_manager_creates_directories(tmp_path):
    """Test that LoggerPathManager creates necessary directories."""
    log_dir = str(tmp_path / "new_logs")
    manager = LoggerPathManager(log_dir)
    
    assert os.path.exists(log_dir)
    assert os.path.exists(manager.checkpoint_dir)
    assert os.path.exists(manager.artifact_dir)


def test_checkpoint_path_generation():
    """Test checkpoint path generation."""
    manager = LoggerPathManager("/tmp/logs")
    
    # Test uncompressed checkpoint
    path = manager.checkpoint_path("epoch_10")
    assert path == "/tmp/logs/checkpoints/checkpoint_epoch_10.pt"
    
    # Test compressed checkpoint
    path = manager.checkpoint_path("best", compressed=True)
    assert path == "/tmp/logs/checkpoints/checkpoint_best.pt.gz"


def test_artifact_path_generation():
    """Test artifact path generation."""
    manager = LoggerPathManager("/tmp/logs")
    
    path = manager.artifact_path("plot.png")
    assert path == "/tmp/logs/artifacts/plot.png"
    
    path = manager.artifact_path("results/metrics.csv")
    assert path == "/tmp/logs/artifacts/results/metrics.csv"


def test_paths_are_consistent():
    """Test that paths remain consistent across multiple accesses."""
    manager = LoggerPathManager("/tmp/logs")
    
    # Access paths multiple times
    metrics1 = manager.metrics_path
    metrics2 = manager.metrics_path
    assert metrics1 == metrics2
    
    ckpt_dir1 = manager.checkpoint_dir
    ckpt_dir2 = manager.checkpoint_dir
    assert ckpt_dir1 == ckpt_dir2