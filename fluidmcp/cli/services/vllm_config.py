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
        "gpu_memory_utilization": 0.88,
        "max_num_seqs": 128,
        "max_num_batched_tokens": 16384,
        "max_model_len": 2048,
        "dtype": "float16",
    },
}

# Recommended GPU memory utilization range for production use
# Values outside this range are allowed but may have trade-offs:
# - Below 0.5: Underutilizes GPU, wastes resources
# - 0.5-0.9: Recommended range balancing performance and stability
# - Above 0.9: Higher risk of OOM errors, less memory headroom for spikes
# - 1.0: Maximum utilization, highest OOM risk, not recommended for production
RECOMMENDED_GPU_MEMORY_MIN = 0.5
RECOMMENDED_GPU_MEMORY_MAX = 0.9


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
    tensor_parallel_models = {}

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

        # Track models with tensor parallelism separately
        if tensor_parallel_size > 1:
            tensor_parallel_models[model_id] = (gpu_mem, tensor_parallel_size)
            logger.debug(f"Excluding {model_id} from GPU memory total (uses tensor parallelism)")
        else:
            memory_breakdown[model_id] = gpu_mem
            total_memory += gpu_mem

    # Log memory breakdown
    if memory_breakdown or tensor_parallel_models:
        logger.info("GPU Memory Allocation:")
        for model_id, mem in memory_breakdown.items():
            logger.info(f"  - {model_id}: {mem:.2f}")
        for model_id, (mem, tps) in tensor_parallel_models.items():
            logger.info(f"  - {model_id}: {mem:.2f} (tensor_parallel_size={tps}, excluded from total)")
        logger.info(f"Total (single-GPU models only): {total_memory:.2f}")
        if tensor_parallel_models:
            logger.warning(
                f"Tensor parallelism detected in models: {list(tensor_parallel_models.keys())}. "
                f"These models are excluded from GPU memory validation as they use multiple GPUs. "
                f"You must manually ensure your multi-GPU setup has sufficient resources for these models."
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
                # Treat empty and whitespace-only values as empty
                if not value.strip():
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
    models_with_no_port = []

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
        else:
            models_with_no_port.append(model_id)

    # Warn if multiple models have no explicit port
    if len(models_with_no_port) > 1:
        logger.warning(
            f"Multiple models have no explicit port configured: {models_with_no_port}. "
            f"They will use vLLM's default ports which may cause runtime conflicts. "
            f"Please specify unique ports for each model to avoid issues."
        )


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

    Notes:
        gpu_memory_utilization:
        - Valid range: 0.0 to 1.0 (inclusive)
        - Recommended range: 0.5 to 0.9 for production
        - Values outside recommended range trigger warnings but are not rejected
        - See RECOMMENDED_GPU_MEMORY_MIN and RECOMMENDED_GPU_MEMORY_MAX constants
    """
    if "config" not in config:
        return  # Skip validation for raw args format

    cfg = config["config"]

    # Validate that config is a dictionary
    if not isinstance(cfg, dict):
        raise VLLMConfigError(
            f"'config' field must be a dictionary, got {type(cfg).__name__}: {cfg!r}"
        )

    # Validate gpu_memory_utilization
    # Note: 0.0 is allowed by vLLM, but its exact behavior is backend-defined
    if "gpu_memory_utilization" in cfg:
        mem = cfg["gpu_memory_utilization"]
        if not _is_valid_number(mem, allow_zero=True, allow_negative=False):
            raise VLLMConfigError(
                f"gpu_memory_utilization must be a number between 0.0 and 1.0 (inclusive), got {mem!r}"
            )

        # Validate range (convert to float for comparison only)
        mem_float = float(mem)
        if mem_float > 1.0:
            raise VLLMConfigError(
                f"gpu_memory_utilization must be between 0.0 and 1.0 (inclusive), got {mem_float}"
            )

        # Warn about edge case values
        if mem_float == 0.0:
            logger.warning(
                "gpu_memory_utilization is set to 0.0. With this value, vLLM will use its "
                "internal heuristics to determine GPU memory allocation, which varies by backend "
                "and model. This can lead to unpredictable memory usage and may cause OOM errors. "
                f"For production use, explicitly set a value between {RECOMMENDED_GPU_MEMORY_MIN} "
                f"and {RECOMMENDED_GPU_MEMORY_MAX} to ensure deterministic memory allocation."
            )
        elif 0.0 < mem_float < RECOMMENDED_GPU_MEMORY_MIN:
            logger.warning(
                f"gpu_memory_utilization is set to {mem_float}, which is below the recommended minimum "
                f"of {RECOMMENDED_GPU_MEMORY_MIN}. While this is technically allowed, such low values "
                f"can underutilize the GPU and waste resources. Consider using a value between "
                f"{RECOMMENDED_GPU_MEMORY_MIN} and {RECOMMENDED_GPU_MEMORY_MAX} for more efficient "
                f"GPU utilization in production."
            )
        elif mem_float > RECOMMENDED_GPU_MEMORY_MAX:
            logger.warning(
                f"gpu_memory_utilization is set to {mem_float}, which exceeds the recommended maximum "
                f"of {RECOMMENDED_GPU_MEMORY_MAX}. While values up to 1.0 are technically allowed, "
                f"higher values leave less memory headroom for allocation spikes and increase the "
                f"risk of OOM errors. Consider using a value between {RECOMMENDED_GPU_MEMORY_MIN} "
                f"and {RECOMMENDED_GPU_MEMORY_MAX} for better stability in production."
            )

    # Validate dtype
    if "dtype" in cfg:
        dtype = cfg["dtype"]
        valid_dtypes = ["float16", "bfloat16", "float32", "auto"]

        # Validate type first
        if not isinstance(dtype, str):
            raise VLLMConfigError(
                f"dtype must be a string, got {type(dtype).__name__}: {dtype!r}"
            )

        # Then validate value
        if dtype not in valid_dtypes:
            raise VLLMConfigError(
                f"dtype must be one of {valid_dtypes}, got '{dtype}'"
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
        # Validate that config is a dictionary
        if not isinstance(config["config"], dict):
            raise VLLMConfigError(
                f"'config' field must be a dictionary, got {type(config['config']).__name__}: {config['config']!r}"
            )
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

    # Validate port type and range
    if not validate_port_number(port):
        raise VLLMConfigError(
            f"Invalid port {port!r}. Port must be an integer between 1 and 65535."
        )

    if not isinstance(model, str) or not model.strip():
        raise VLLMConfigError(
            "'model' field must be a non-empty string for high-level config, "
            f"got {type(model).__name__}: {model!r}"
        )

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
        args.extend(["--dtype", str(cfg["dtype"])])

    if "max_num_seqs" in cfg:
        args.extend(["--max-num-seqs", str(cfg["max_num_seqs"])])

    if "max_num_batched_tokens" in cfg:
        args.extend(["--max-num-batched-tokens", str(cfg["max_num_batched_tokens"])])

    # Validate optional fields
    env = config.get("env", {})
    if not isinstance(env, dict):
        raise VLLMConfigError(
            f"'env' field must be a dictionary, got {type(env).__name__}: {env!r}"
        )

    endpoints = config.get("endpoints", {"base_url": f"http://localhost:{port}/v1"})
    if not isinstance(endpoints, dict):
        raise VLLMConfigError(
            f"'endpoints' field must be a dictionary, got {type(endpoints).__name__}: {endpoints!r}"
        )

    # Construct transformed config
    transformed = {
        "command": "vllm",
        "args": args,
        "env": env,
        "endpoints": endpoints,
    }

    # Add timeout configuration if present
    if "timeouts" in config:
        timeouts = config["timeouts"]
        if not isinstance(timeouts, dict):
            raise VLLMConfigError(
                f"'timeouts' field must be a dictionary, got {type(timeouts).__name__}: {timeouts!r}"
            )

        # Validate timeout values
        for key, value in timeouts.items():
            if value is not None:  # None is allowed (means no timeout)
                # Explicitly reject booleans; only allow non-negative int/float
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise VLLMConfigError(
                        f"Timeout '{key}' must be a non-negative number or null, got {type(value).__name__}: {value!r}"
                    )
                # Warn about timeout=0 which may have special behavior
                if value == 0:
                    logger.warning(
                        f"Timeout '{key}' is set to 0, which may have special semantics (immediate timeout, "
                        f"poll-only, or infinite timeout depending on the implementation). "
                        f"Consider using null for no timeout or a small positive value for testing."
                    )

        transformed["timeouts"] = timeouts

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
