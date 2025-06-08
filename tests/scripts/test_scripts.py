"""Tests for streamlined scripts - focused on import and basic functionality."""

from unittest.mock import patch

# Basic import and functionality tests since full script testing is complex


class TestDiscoverGpus:
    """Test GPU discovery functionality."""
    
    def test_discover_gpus_from_env(self):
        """Test GPU discovery from environment variable."""
        from scripts.run_manager import discover_gpus
        
        with patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': '1,3,5'}):
            gpus = discover_gpus(4)
            assert gpus == ['1', '3', '5']
    
    def test_discover_gpus_default(self):
        """Test GPU discovery with default behavior."""
        from scripts.run_manager import discover_gpus
        
        with patch.dict('os.environ', {}, clear=True):
            gpus = discover_gpus(3)
            assert gpus == ['0', '1', '2']
    
    def test_discover_gpus_empty_env(self):
        """Test GPU discovery with empty environment variable."""
        from scripts.run_manager import discover_gpus
        
        with patch.dict('os.environ', {'CUDA_VISIBLE_DEVICES': ''}):
            gpus = discover_gpus(2)
            assert gpus == ['0', '1']


class TestScriptImports:
    """Test that scripts can be imported and have basic structure."""
    
    def test_manager_script_import(self):
        """Test manager script can be imported."""
        from scripts.run_manager import main, discover_gpus
        
        assert main is not None
        assert discover_gpus is not None
        assert callable(main)
        assert callable(discover_gpus)
    
    def test_worker_script_import(self):
        """Test worker script can be imported.""" 
        from scripts.run_worker import main
        
        assert main is not None
        assert callable(main)