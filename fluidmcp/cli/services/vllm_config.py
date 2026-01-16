"""
Advanced vLLM Configuration with Validation.

This module provides high-level configuration schema for vLLM models with:
- Production-safe defaults and profiles
- GPU memory validation
- Config transformation from high-level to vLLM CLI args
- Backward compatibility with raw args format
"""

import copy
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from .validators import validate_port_number


# Configuration profiles with production-safe defaults
VLLM_PROFILES = {
    "development": {
        "gpu_memory_utilization": 0.5,
        "max_num_seqs": 16,
        "max_num_batched_tokens": 2048,
        "max_model_len": 2048,
        "dtype": "float16",
    },
    "production": {
        "gpu_memory_utilization": 0.85,
        "max_num_seqs": 64,
        "max_num_batched_tokens": 8192,
        "max_model_len": 4096,
        "dtype": "float16",
    },
    "high-throughput": {
        "gpu_memory_utilization": 0.9,
        "max_num_seqs": 128,
        "max_num_batched_tokens": 16384,
        "max_model_len": 2048,
        "dtype": "float16",
    },
}


class VLLMConfigError(Exception):
    """Raised when vLLM configuration is invalid."""
    pass


def validate_gpu_memory(
    llm_models: Dict[str, Dict[str, Any]],
    fail_on_exceed: bool = True
) -> Tuple[float, Dict[str, float]]:
    """
    Validate GPU memory allocation across all vLLM models.

    Args:
        llm_models: Dictionary of LLM model configurations
        fail_on_exceed: If True, raise error when total > 1.0; if False, only warn

    Returns:
        Tuple of (total_memory, memory_breakdown)

    Raises:
        VLLMConfigError: If total GPU memory exceeds 1.0 (when fail_on_exceed=True)
    """
    memory_breakdown = {}
    total_memory = 0.0
    has_tensor_parallelism = False

    for model_id, config in llm_models.items():
        # Check if high-level config exists
        if "config" in config:
            gpu_mem = config["config"].get("gpu_memory_utilization", 0.9)
            tensor_parallel_size = config["config"].get("tensor_parallel_size", 1)
        # Fall back to parsing args for backward compatibility
        elif "args" in config:
            gpu_mem = _extract_gpu_memory_from_args(config["args"])
            tensor_parallel_size = 1  # Can't easily parse from args, assume 1
        else:
            gpu_mem = 0.9  # vLLM default
            tensor_parallel_size = 1

        if tensor_parallel_size > 1:
            has_tensor_parallelism = True

        memory_breakdown[model_id] = gpu_mem
        total_memory += gpu_mem

    # Log memory breakdown
    if memory_breakdown:
        logger.info("GPU Memory Allocation:")
        for model_id, mem in memory_breakdown.items():
            logger.info(f"  - {model_id}: {mem:.2f}")
        logger.info(f"Total: {total_memory:.2f}")
        if has_tensor_parallelism:
            logger.warning(
                "Tensor parallelism detected (tensor_parallel_size > 1). "
                "GPU memory validation is simplified and may not accurately reflect multi-GPU setups. "
                "Ensure your GPU resources can accommodate all models with their tensor parallel configurations."
            )

    # Validation: Fail on exceeded memory
    if total_memory > 1.0:
        msg = (
            f"GPU memory allocation exceeds 1.0 (total: {total_memory:.2f}). "
            f"This will cause out-of-memory errors. Breakdown: {memory_breakdown}"
        )
        if fail_on_exceed:
            raise VLLMConfigError(msg)
        else:
            logger.warning(msg)

    # Validation: Warn if dangerously close to 1.0
    elif total_memory > 0.95:
        logger.warning(
            f"GPU memory allocation is {total_memory:.2f} (very close to 1.0). "
            f"Consider reducing to avoid potential OOM errors."
        )

    return total_memory, memory_breakdown


def _extract_arg_value(args: List[str], arg_name: str, converter=str, default=None):
    """
    Extract argument value from CLI args list.

    Handles both formats: --arg-name value and --arg-name=value

    Args:
        args: List of CLI arguments
        arg_name: Name of argument (e.g., "--port", "--gpu-memory-utilization")
        converter: Function to convert string value (e.g., int, float)
        default: Default value if argument not found or conversion fails

    Returns:
        Extracted and converted value, or default if not found/invalid
    """
    for i, arg in enumerate(args):
        # Format: --arg-name value
        if arg == arg_name and i + 1 < len(args):
            try:
                return converter(args[i + 1])
            except (ValueError, TypeError):
                logger.warning(f"Invalid {arg_name} value: {args[i + 1]}, using default: {default}")
                return default
        # Format: --arg-name=value
        elif arg.startswith(f"{arg_name}="):
            try:
                # Split only on first '=' to handle values containing '=' (e.g., --arg=key=value)
                value = arg.split("=", 1)[1]
                if value == "":
                    logger.warning(f"Empty {arg_name} value in argument: {arg}, using default: {default}")
                    return default
                return converter(value)
            except (ValueError, IndexError, TypeError):
                logger.warning(f"Invalid {arg_name} format: {arg}, using default: {default}")
                return default
    return default


def _extract_gpu_memory_from_args(args: List[str]) -> float:
    """Extract --gpu-memory-utilization value from CLI args."""
    return _extract_arg_value(args, "--gpu-memory-utilization", float, 0.9)


def validate_port_conflicts(llm_models: Dict[str, Dict[str, Any]]) -> None:
    """
    Validate that no two models use the same port.

    Args:
        llm_models: Dictionary of LLM model configurations

    Raises:
        VLLMConfigError: If port conflicts are detected
    """
    port_to_models = {}

    for model_id, config in llm_models.items():
        # Check if high-level config exists
        if "config" in config:
            # Port can be specified at top-level or inside "config"
            # Top-level takes precedence if both are present
            top_level_port = config.get("port")
            nested_port = config["config"].get("port")

            if top_level_port is not None and nested_port is not None and top_level_port != nested_port:
                raise VLLMConfigError(
                    f"Model '{model_id}' specifies conflicting 'port' values: "
                    f"top-level={top_level_port}, config.port={nested_port}. "
                    "Please specify 'port' in a single location or ensure the values match."
                )

            port = top_level_port if top_level_port is not None else nested_port
        # Fall back to parsing args
        elif "args" in config:
            port = _extract_port_from_args(config["args"])
        else:
            port = None

        if port is not None:
            # Validate port range using shared validator
            if not validate_port_number(port):
                raise VLLMConfigError(
                    f"Model '{model_id}' has invalid port {port}. "
                    f"Port must be an integer between 1 and 65535."
                )
            # Check for conflicts
            if port in port_to_models:
                raise VLLMConfigError(
                    f"Port conflict: Models '{port_to_models[port]}' and '{model_id}' "
                    f"both use port {port}"
                )
            port_to_models[port] = model_id


def _extract_port_from_args(args: List[str]) -> Optional[int]:
    """Extract --port value from CLI args."""
    return _extract_arg_value(args, "--port", int, None)


def _is_bool_type(value: Any) -> bool:
    """
    Check if value is a boolean type.

    Helper function to explicitly reject booleans in numeric validation,
    since bool is a subclass of int in Python (True==1, False==0).

    Args:
        value: Value to check

    Returns:
        True if value is a bool, False otherwise
    """
    return isinstance(value, bool)


def _is_valid_number(value: Any, allow_zero: bool = True, allow_negative: bool = False) -> bool:
    """
    Check if value is a valid numeric type (int or float, but not bool).

    Args:
        value: Value to check
        allow_zero: Whether 0 is valid
        allow_negative: Whether negative values are valid

    Returns:
        True if valid number, False otherwise

    Note:
        Explicitly rejects booleans because bool is a subclass of int in Python (True==1, False==0)
    """
    if _is_bool_type(value) or not isinstance(value, (int, float)):
        return False

    if not allow_negative and value < 0:
        return False

    if not allow_zero and value == 0:
        return False

    return True


def _is_valid_positive_int(value: Any) -> bool:
    """
    Check if value is a valid positive integer (not bool, not zero, not negative).

    Args:
        value: Value to check

    Returns:
        True if valid positive integer, False otherwise

    Note:
        Explicitly rejects booleans because bool is a subclass of int in Python (True==1, False==0)
    """
    if _is_bool_type(value) or not isinstance(value, int):
        return False

    return value > 0


def validate_config_values(config: Dict[str, Any]) -> None:
    """
    Validate individual configuration values.

    Args:
        config: Model configuration dictionary

    Raises:
        VLLMConfigError: If configuration values are invalid
    """
    if "config" not in config:
        return  # Skip validation for raw args format

    cfg = config["config"]

    # Validate gpu_memory_utilization
    # Note: 0.0 is allowed by vLLM, but its exact behavior is backend-defined
    if "gpu_memory_utilization" in cfg:
        mem = cfg["gpu_memory_utilization"]
        if not _is_valid_number(mem, allow_zero=True, allow_negative=False):
            raise VLLMConfigError(
                f"gpu_memory_utilization must be a number between 0.0 and 1.0 (inclusive), got {mem!r}"
            )
        mem = float(mem)  # Normalize to float for vLLM
        if mem > 1.0:
            raise VLLMConfigError(
                f"gpu_memory_utilization must be between 0.0 and 1.0 (inclusive), got {mem}"
            )

        # Warn about edge case value
        if mem == 0.0:
            logger.warning(
                "gpu_memory_utilization is set to 0.0. With this value, vLLM will use its "
                "internal heuristics to determine GPU memory allocation, which varies by backend "
                "and model. This can lead to unpredictable memory usage and may cause OOM errors. "
                "For production use, explicitly set a value between 0.5 and 0.9 to ensure "
                "deterministic memory allocation."
            )

    # Validate dtype
    if "dtype" in cfg:
        valid_dtypes = ["float16", "bfloat16", "float32", "auto"]
        if cfg["dtype"] not in valid_dtypes:
            raise VLLMConfigError(
                f"dtype must be one of {valid_dtypes}, got '{cfg['dtype']}'"
            )

    # Validate tensor_parallel_size
    if "tensor_parallel_size" in cfg:
        tps = cfg["tensor_parallel_size"]
        if not _is_valid_positive_int(tps):
            raise VLLMConfigError(
                f"tensor_parallel_size must be a positive integer, got {tps}"
            )

    # Validate max values
    for field in ["max_num_seqs", "max_num_batched_tokens", "max_model_len"]:
        if field in cfg:
            val = cfg[field]
            if not _is_valid_positive_int(val):
                raise VLLMConfigError(
                    f"{field} must be a positive integer, got {val}"
                )

    # Warn on risky values
    if cfg.get("max_model_len", 0) > 32768:
        logger.warning(
            f"max_model_len is very high ({cfg['max_model_len']}). "
            f"This may cause memory issues or slow performance."
        )

    if cfg.get("max_num_seqs", 0) > 256:
        logger.warning(
            f"max_num_seqs is very high ({cfg['max_num_seqs']}). "
            f"This may cause high latency or memory pressure."
        )


def apply_profile(config: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    """
    Apply a configuration profile to a model config.

    This function is now immutable - it creates and returns a new dictionary
    instead of modifying the input config in-place.

    Args:
        config: Model configuration dictionary (will NOT be modified)
        profile_name: Name of profile to apply (development/production/high-throughput)

    Returns:
        New config dictionary with profile defaults applied

    Raises:
        VLLMConfigError: If profile name is invalid

    Behavior:
        - Creates a deep copy of the input config
        - Adds profile default values to the copy's config["config"]
        - Does NOT override user-specified values
        - Returns the new config without modifying the original
    """
    if profile_name not in VLLM_PROFILES:
        raise VLLMConfigError(
            f"Invalid profile '{profile_name}'. "
            f"Valid profiles: {list(VLLM_PROFILES.keys())}"
        )

    # Make a deep copy to avoid mutating the input
    result = copy.deepcopy(config)

    profile = VLLM_PROFILES[profile_name]

    # Initialize config dict if not present
    if "config" not in result:
        result["config"] = {}

    # Apply profile defaults (don't override user-specified values)
    for key, value in profile.items():
        if key not in result["config"]:
            result["config"][key] = value

    logger.info(f"Using profile: {profile_name} (override any field to customize)")

    return result


def transform_to_vllm_args(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform high-level config to vLLM CLI args format.

    Supports both:
    1. High-level config (with "config" key) - transforms to args
    2. Raw args format (with "command"/"args") - returns as-is for backward compatibility

    Args:
        config: Model configuration dictionary

    Returns:
        Config with vLLM CLI args in the format expected by llm_launcher

    Raises:
        VLLMConfigError: If config is invalid
    """
    # Determine config style and detect ambiguous configurations
    if "config" in config and "command" in config and "args" in config:
        raise VLLMConfigError(
            "Config contains both high-level format ('config') and raw format ('command'+'args'). "
            "Please use only one format."
        )

    if "config" in config:
        logger.debug("Using high-level config format")
    elif "command" in config and "args" in config:
        logger.debug("Using raw args format (backward compatibility)")
        return config
    else:
        raise VLLMConfigError(
            "Config must have either 'config' (high-level) or 'command'+'args' (raw format)"
        )

    cfg = config["config"]
    model = config.get("model")

    # Port can be at top-level or inside config, with top-level taking precedence
    # This matches the logic in validate_port_conflicts()
    top_level_port = config.get("port")
    nested_port = cfg.get("port")
    port = top_level_port if top_level_port is not None else (nested_port if nested_port is not None else 8001)

    if not model or (isinstance(model, str) and not model.strip()):
        raise VLLMConfigError("'model' field is required and cannot be empty for high-level config")

    # Build vLLM CLI args
    args = [
        "serve",
        model,
        "--port", str(port),
        "--host", "0.0.0.0",
    ]

    # Add optional parameters
    if "tensor_parallel_size" in cfg:
        args.extend(["--tensor-parallel-size", str(cfg["tensor_parallel_size"])])

    if "gpu_memory_utilization" in cfg:
        args.extend(["--gpu-memory-utilization", str(cfg["gpu_memory_utilization"])])

    if "max_model_len" in cfg:
        args.extend(["--max-model-len", str(cfg["max_model_len"])])

    if "dtype" in cfg:
        args.extend(["--dtype", cfg["dtype"]])

    if "max_num_seqs" in cfg:
        args.extend(["--max-num-seqs", str(cfg["max_num_seqs"])])

    if "max_num_batched_tokens" in cfg:
        args.extend(["--max-num-batched-tokens", str(cfg["max_num_batched_tokens"])])

    # Construct transformed config
    transformed = {
        "command": "vllm",
        "args": args,
        "env": config.get("env", {}),
        "endpoints": config.get("endpoints", {"base_url": f"http://localhost:{port}/v1"}),
    }

    # Add timeout configuration if present
    if "timeouts" in config:
        transformed["timeouts"] = config["timeouts"]

    return transformed


def validate_and_transform_llm_config(llm_models: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point: validate and transform all LLM model configurations.

    This function:
    1. Makes a deep copy to avoid mutating caller's data
    2. Applies profiles if specified
    3. Validates individual configs (individual model values)
    4. Validates cross-model constraints (GPU memory, port conflicts)
    5. Transforms high-level configs to vLLM CLI args
    6. Maintains backward compatibility with raw args format

    Args:
        llm_models: Dictionary of LLM model configurations from JSON

    Returns:
        Dictionary of validated and transformed configurations ready for llm_launcher

    Raises:
        VLLMConfigError: If validation fails

    Note:
        This function does NOT mutate the input llm_models dictionary. A deep copy
        is made internally to prevent side effects on the caller's data.
    """
    if not llm_models:
        return {}

    # Make a deep copy to avoid mutating the caller's config
    llm_models = copy.deepcopy(llm_models)

    # Step 1: Apply profiles, set defaults, and validate individual configs
    for model_id, config in llm_models.items():
        try:
            # Apply profile if specified (returns new config without mutation)
            if "profile" in config:
                llm_models[model_id] = apply_profile(config, config["profile"])

            # Use updated config after profile application
            current_config = llm_models[model_id]

            # Apply default port if not specified (for proper conflict detection)
            if "config" in current_config:
                top_level_port = current_config.get("port")
                nested_port = current_config["config"].get("port")
                if top_level_port is None and nested_port is None:
                    current_config["port"] = 8001  # Apply default for validation

            # Validate config values
            validate_config_values(current_config)

        except VLLMConfigError as e:
            logger.error(f"Config error for model '{model_id}': {e}")
            raise

    # Step 2: Cross-model validation (before transformation to avoid re-parsing)
    validate_port_conflicts(llm_models)
    validate_gpu_memory(llm_models)

    # Step 3: Transform to vLLM args format
    transformed = {}
    for model_id, config in llm_models.items():
        try:
            transformed[model_id] = transform_to_vllm_args(config)
        except VLLMConfigError as e:
            logger.error(f"Transformation error for model '{model_id}': {e}")
            raise

    return transformed
