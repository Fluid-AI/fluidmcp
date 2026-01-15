"""
Manual test for vLLM advanced configuration features.

This script tests:
1. High-level config transformation
2. Profile application
3. GPU memory validation
4. Port conflict detection
5. Config value validation
6. Backward compatibility

Prerequisites:
- vLLM installed: pip install vllm>=0.6.0
- GPU available (recommended)

Usage:
    python tests/manual/test_advanced_config.py
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fluidmcp.cli.services.vllm_config import (
    validate_and_transform_llm_config,
    VLLMConfigError,
    validate_gpu_memory,
    validate_port_conflicts,
    apply_profile,
    VLLM_PROFILES,
)


def test_high_level_config_transformation():
    """Test that high-level config transforms to vLLM args correctly."""
    print("\n=== Test 1: High-Level Config Transformation ===")

    config = {
        "vllm": {
            "model": "TEST_MODEL",  # e.g., facebook/opt-125m
            "port": 8001,
            "config": {
                "gpu_memory_utilization": 0.9,
                "max_num_seqs": 64,
                "max_model_len": 4096,
                "dtype": "float16",
            }
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✓ Config transformed successfully")
        print(f"  Command: {result['vllm']['command']}")
        print(f"  Args: {' '.join(result['vllm']['args'])}")
        assert result['vllm']['command'] == 'vllm'
        assert 'serve' in result['vllm']['args']
        assert 'TEST_MODEL' in result['vllm']['args']
        assert '--gpu-memory-utilization' in result['vllm']['args']
        print("✓ All assertions passed")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    return True


def test_profile_application():
    """Test that profiles apply correct defaults."""
    print("\n=== Test 2: Profile Application ===")

    for profile_name in ["development", "production", "high-throughput"]:
        print(f"\nTesting profile: {profile_name}")
        config = {
            "model": "TEST_MODEL",
            "port": 8001,
            "profile": profile_name,
        }

        try:
            result = apply_profile(config, profile_name)
            print(f"✓ Profile '{profile_name}' applied")
            print(f"  Config: {result['config']}")

            # Verify profile defaults were applied
            expected = VLLM_PROFILES[profile_name]
            for key, value in expected.items():
                assert result['config'][key] == value, f"Expected {key}={value}, got {result['config'][key]}"

            print(f"✓ All profile defaults verified")
        except Exception as e:
            print(f"✗ Failed: {e}")
            return False

    return True


def test_gpu_memory_validation():
    """Test GPU memory validation across multiple models."""
    print("\n=== Test 3: GPU Memory Validation ===")

    # Test 1: Valid config (total < 1.0)
    print("\nTest 3a: Valid memory allocation")
    config = {
        "model1": {
            "model": "TEST_MODEL_1",
            "port": 8001,
            "config": {"gpu_memory_utilization": 0.45}
        },
        "model2": {
            "model": "TEST_MODEL_2",
            "port": 8002,
            "config": {"gpu_memory_utilization": 0.45}
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✓ Valid config accepted (total = 0.90)")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    # Test 2: Invalid config (total > 1.0)
    print("\nTest 3b: Invalid memory allocation (should fail)")
    config = {
        "model1": {
            "model": "TEST_MODEL_1",
            "port": 8001,
            "config": {"gpu_memory_utilization": 0.6}
        },
        "model2": {
            "model": "TEST_MODEL_2",
            "port": 8002,
            "config": {"gpu_memory_utilization": 0.6}
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✗ Should have failed but didn't")
        return False
    except VLLMConfigError as e:
        print(f"✓ Correctly rejected: {e}")

    return True


def test_port_conflict_detection():
    """Test port conflict detection."""
    print("\n=== Test 4: Port Conflict Detection ===")

    config = {
        "model1": {
            "model": "TEST_MODEL_1",
            "port": 8001,
            "config": {"gpu_memory_utilization": 0.45}
        },
        "model2": {
            "model": "TEST_MODEL_2",
            "port": 8001,  # Same port as model1
            "config": {"gpu_memory_utilization": 0.45}
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✗ Should have detected port conflict")
        return False
    except VLLMConfigError as e:
        print(f"✓ Port conflict detected: {e}")

    return True


def test_config_value_validation():
    """Test validation of individual config values."""
    print("\n=== Test 5: Config Value Validation ===")

    # Test invalid gpu_memory_utilization
    print("\nTest 5a: Invalid gpu_memory_utilization")
    config = {
        "vllm": {
            "model": "TEST_MODEL",
            "port": 8001,
            "config": {"gpu_memory_utilization": 1.5}  # > 1.0
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✗ Should have rejected invalid value")
        return False
    except VLLMConfigError as e:
        print(f"✓ Invalid value rejected: {e}")

    # Test invalid dtype
    print("\nTest 5b: Invalid dtype")
    config = {
        "vllm": {
            "model": "TEST_MODEL",
            "port": 8001,
            "config": {"dtype": "invalid"}
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✗ Should have rejected invalid dtype")
        return False
    except VLLMConfigError as e:
        print(f"✓ Invalid dtype rejected: {e}")

    return True


def test_backward_compatibility():
    """Test that old raw args format still works."""
    print("\n=== Test 6: Backward Compatibility ===")

    config = {
        "vllm": {
            "command": "vllm",
            "args": [
                "serve",
                "TEST_MODEL",
                "--port", "8001",
                "--gpu-memory-utilization", "0.9"
            ],
            "env": {},
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }
    }

    try:
        result = validate_and_transform_llm_config(config)
        print(f"✓ Raw args format accepted")
        print(f"  Command: {result['vllm']['command']}")
        print(f"  Args: {' '.join(result['vllm']['args'])}")
        # Should return as-is
        assert result['vllm']['command'] == 'vllm'
        assert result['vllm']['args'][0] == 'serve'
        print("✓ Backward compatibility verified")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

    return True


def test_example_configs():
    """Test that example configs are valid."""
    print("\n=== Test 7: Example Config Files ===")

    examples = [
        "examples/vllm-advanced-config.json",
        "examples/vllm-profile-development.json",
        "examples/vllm-multi-model-advanced.json",
    ]

    for example_path in examples:
        full_path = project_root / example_path
        if not full_path.exists():
            print(f"⚠ Skipping {example_path} (not found)")
            continue

        print(f"\nValidating {example_path}")
        try:
            with open(full_path) as f:
                config_data = json.load(f)

            llm_models = config_data.get("llmModels", {})
            result = validate_and_transform_llm_config(llm_models)
            print(f"✓ {example_path} is valid")
            print(f"  Models: {list(result.keys())}")
        except Exception as e:
            print(f"✗ {example_path} failed: {e}")
            return False

    return True


def main():
    """Run all tests."""
    print("="*60)
    print("vLLM Advanced Configuration - Manual Tests")
    print("="*60)

    tests = [
        test_high_level_config_transformation,
        test_profile_application,
        test_gpu_memory_validation,
        test_port_conflict_detection,
        test_config_value_validation,
        test_backward_compatibility,
        test_example_configs,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
