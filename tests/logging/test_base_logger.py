"""Tests for the BaseLogger abstract base class."""

import pytest
from abc import ABC

from dr_exp.logging.base_logger import BaseLogger
from dr_exp.logging.structured_logger import StructuredLogger


def test_base_logger_is_abstract():
    """Test that BaseLogger cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseLogger()


def test_base_logger_inheritance():
    """Test that BaseLogger is properly inherited by concrete implementations."""
    assert issubclass(StructuredLogger, BaseLogger)
    
    # Test with a simple log directory
    logger = StructuredLogger("/tmp/test_logs")
    assert isinstance(logger, BaseLogger)


def test_base_logger_enforces_abstract_methods():
    """Test that concrete implementations must implement all abstract methods."""
    class IncompleteLogger(BaseLogger):
        run_id = "test_run"
        
        # Missing implementations of abstract methods
        pass
    
    with pytest.raises(TypeError):
        IncompleteLogger()


def test_minimal_logger_implementation():
    """Test a minimal implementation that satisfies all abstract methods."""
    from dr_exp.logging.logger_paths import LoggerPathManager
    
    class MinimalLogger(BaseLogger):
        run_id = "test_run"
        
        def __init__(self):
            self._paths = LoggerPathManager("/tmp/minimal_logs")
        
        @property
        def paths(self):
            return self._paths
        
        def log(self, metrics):
            pass
            
        def save_checkpoint(self, state_dict, tag):
            return f"/tmp/checkpoint_{tag}.pt"
            
        def log_artifact(self, path):
            pass
            
        def finalize(self):
            return {"finalize_success": True}
    
    # Should be able to instantiate
    logger = MinimalLogger()
    assert isinstance(logger, BaseLogger)
    
    # Test all methods
    logger.log({"epoch": 1})
    path = logger.save_checkpoint({"weights": [1, 2]}, "test")
    assert "checkpoint_test.pt" in path
    logger.log_artifact("/tmp/artifact.txt")
    result = logger.finalize()
    assert result["finalize_success"] is True


def test_structured_logger_implements_interface():
    """Test that StructuredLogger properly implements the BaseLogger interface."""
    logger = StructuredLogger("/tmp/test_logs")
    
    # Should be instance of BaseLogger
    assert isinstance(logger, BaseLogger)
    
    # Should have required attribute
    assert hasattr(logger, 'run_id')
    
    # Should have all abstract methods and properties
    abstract_methods = ['log', 'save_checkpoint', 'log_artifact', 'finalize']
    abstract_properties = ['paths']
    
    for method in abstract_methods:
        assert hasattr(logger, method) and callable(getattr(logger, method))
    
    for prop in abstract_properties:
        assert hasattr(logger, prop)


def test_interface_consistency():
    """Test that the interface is consistent across implementations."""
    logger = StructuredLogger("/tmp/test_logs")
    
    # Test method signatures match base class
    import inspect
    
    # Check log method (excluding 'self' parameter)
    base_sig = inspect.signature(BaseLogger.log)
    impl_sig = inspect.signature(logger.log)
    base_params = [p for name, p in base_sig.parameters.items() if name != 'self']
    impl_params = [p for name, p in impl_sig.parameters.items() if name != 'self']
    assert len(base_params) == len(impl_params)
    
    # Check save_checkpoint method (excluding 'self' parameter)
    base_sig = inspect.signature(BaseLogger.save_checkpoint)
    impl_sig = inspect.signature(logger.save_checkpoint)
    base_params = [p for name, p in base_sig.parameters.items() if name != 'self']
    impl_params = [p for name, p in impl_sig.parameters.items() if name != 'self']
    assert len(base_params) == len(impl_params)
    
    # Check finalize method (excluding 'self' parameter)
    base_sig = inspect.signature(BaseLogger.finalize)
    impl_sig = inspect.signature(logger.finalize)
    base_params = [p for name, p in base_sig.parameters.items() if name != 'self']
    impl_params = [p for name, p in impl_sig.parameters.items() if name != 'self']
    assert len(base_params) == len(impl_params)


def test_base_logger_docstrings():
    """Test that abstract methods have proper docstrings."""
    methods_to_check = ['log', 'save_checkpoint', 'log_artifact', 'finalize']
    
    for method_name in methods_to_check:
        method = getattr(BaseLogger, method_name)
        assert method.__doc__ is not None, f"{method_name} should have a docstring"
        # finalize doesn't take parameters beyond self, so skip parameter check
        if method_name != 'finalize':
            assert "Parameters" in method.__doc__, f"{method_name} docstring should document parameters"


def test_type_annotations():
    """Test that BaseLogger methods have proper type annotations."""
    import inspect
    
    # Check that abstract methods have type annotations
    sig = inspect.signature(BaseLogger.log)
    assert 'return' in sig.parameters or hasattr(sig, 'return_annotation')
    
    sig = inspect.signature(BaseLogger.save_checkpoint)
    assert len(sig.parameters) >= 2  # self, state_dict, tag
    
    sig = inspect.signature(BaseLogger.finalize)
    assert hasattr(sig, 'return_annotation') or 'return' in str(sig)


def test_abc_inheritance():
    """Test that BaseLogger properly inherits from ABC."""
    assert issubclass(BaseLogger, ABC)
    
    # Test that abstract method decorator works
    from abc import abstractmethod
    assert hasattr(BaseLogger.log, '__isabstractmethod__')
    assert hasattr(BaseLogger.save_checkpoint, '__isabstractmethod__')
    assert hasattr(BaseLogger.log_artifact, '__isabstractmethod__')
    assert hasattr(BaseLogger.finalize, '__isabstractmethod__')
    assert hasattr(BaseLogger.paths, '__isabstractmethod__')


def test_logger_factory_compatibility():
    """Test that logger instances work with factory patterns."""
    def create_logger(logger_cls, log_dir):
        """Simple factory function."""
        return logger_cls(log_dir)
    
    # Should be able to use BaseLogger as type hint in factory
    logger = create_logger(StructuredLogger, "/tmp/test_logs")
    assert isinstance(logger, BaseLogger)
    assert isinstance(logger, StructuredLogger)