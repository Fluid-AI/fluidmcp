"""
Advanced vLLM Configuration with Validation.

This module provides high-level configuration schema for vLLM models with:
- Production-safe defaults and profiles
- GPU memory validation
- Config transformation from high-level to vLLM CLI args
- Backward compatibility with raw args format
"""

from typing import Dict, Any, List, Optional, Tuple
from loguru import logger


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


class VLLMConfigWarning(UserWarning):
    """Warning for risky but valid vLLM configurations."""
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

    for model_id, config in llm_models.items():
        # Check if high-level config exists
        if "config" in config:
            gpu_mem = config["config"].get("gpu_memory_utilization", 0.9)
        # Fall back to parsing args for backward compatibility
        elif "args" in config:
            gpu_mem = _extract_gpu_memory_from_args(config["args"])
        else:
            gpu_mem = 0.9  # vLLM default

        memory_breakdown[model_id] = gpu_mem
        total_memory += gpu_mem

    # Log memory breakdown
    if memory_breakdown:
        logger.info("GPU Memory Allocation:")
        for model_id, mem in memory_breakdown.items():
            logger.info(f"  - {model_id}: {mem:.2f}")
        logger.info(f"Total: {total_memory:.2f}")

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


def _extract_gpu_memory_from_args(args: List[str]) -> float:
    """Extract --gpu-memory-utilization value from CLI args."""
    for i, arg in enumerate(args):
        if arg == "--gpu-memory-utilization" and i + 1 < len(args):
            try:
                return float(args[i + 1])
            except ValueError:
                logger.warning(f"Invalid --gpu-memory-utilization value: {args[i + 1]}")
                return 0.9
        elif arg.startswith("--gpu-memory-utilization="):
            try:
                return float(arg.split("=")[1])
            except (ValueError, IndexError):
                logger.warning(f"Invalid --gpu-memory-utilization format: {arg}")
                return 0.9
    return 0.9  # vLLM default


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
            port = config.get("port") if "port" in config else config["config"].get("port")
        # Fall back to parsing args
        elif "args" in config:
            port = _extract_port_from_args(config["args"])
        else:
            port = None

        if port is not None:
            if port in port_to_models:
                raise VLLMConfigError(
                    f"Port conflict: Models '{port_to_models[port]}' and '{model_id}' "
                    f"both use port {port}"
                )
            port_to_models[port] = model_id


def _extract_port_from_args(args: List[str]) -> Optional[int]:
    """Extract --port value from CLI args."""
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                return None
        elif arg.startswith("--port="):
            try:
                return int(arg.split("=")[1])
            except (ValueError, IndexError):
                return None
    return None


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
    if "gpu_memory_utilization" in cfg:
        mem = cfg["gpu_memory_utilization"]
        if not isinstance(mem, (int, float)) or mem < 0 or mem > 1.0:
            raise VLLMConfigError(
                f"gpu_memory_utilization must be between 0.0 and 1.0 (inclusive), got {mem}"
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
        if not isinstance(tps, int) or tps < 1:
            raise VLLMConfigError(
                f"tensor_parallel_size must be a positive integer, got {tps}"
            )

    # Validate max values
    for field in ["max_num_seqs", "max_num_batched_tokens", "max_model_len"]:
        if field in cfg:
            val = cfg[field]
            if not isinstance(val, int) or val <= 0:
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

    NOTE: This function mutates the input config dictionary in-place by adding
    profile defaults to config["config"]. User-specified values are not overridden.

    Args:
        config: Model configuration dictionary (modified in-place)
        profile_name: Name of profile to apply (development/production/high-throughput)

    Returns:
        The modified config dictionary (same object as input)

    Raises:
        VLLMConfigError: If profile name is invalid
    """
    if profile_name not in VLLM_PROFILES:
        raise VLLMConfigError(
            f"Invalid profile '{profile_name}'. "
            f"Valid profiles: {list(VLLM_PROFILES.keys())}"
        )

    profile = VLLM_PROFILES[profile_name]

    # Initialize config dict if not present
    if "config" not in config:
        config["config"] = {}

    # Apply profile defaults (don't override user-specified values)
    for key, value in profile.items():
        if key not in config["config"]:
            config["config"][key] = value

    logger.info(f"Using profile: {profile_name} (override any field to customize)")

    return config


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
    # Determine config style: high-level config takes precedence when present
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
    port = config.get("port", 8001)

    if not model:
        raise VLLMConfigError("'model' field is required for high-level config")

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
    1. Applies profiles if specified
    2. Validates all configs (GPU memory, ports, values)
    3. Transforms high-level configs to vLLM CLI args
    4. Maintains backward compatibility with raw args format

    Args:
        llm_models: Dictionary of LLM model configurations from JSON

    Returns:
        Dictionary of validated and transformed configurations ready for llm_launcher

    Raises:
        VLLMConfigError: If validation fails
    """
    if not llm_models:
        return {}

    transformed = {}

    # Step 1: Apply profiles and validate individual configs
    for model_id, config in llm_models.items():
        try:
            # Apply profile if specified (mutates config in-place)
            if "profile" in config:
                apply_profile(config, config["profile"])

            # Validate config values
            validate_config_values(config)

            # Transform to vLLM args format
            transformed[model_id] = transform_to_vllm_args(config)

        except VLLMConfigError as e:
            logger.error(f"Config error for model '{model_id}': {e}")
            raise

    # Step 2: Cross-model validation
    validate_port_conflicts(transformed)
    validate_gpu_memory(transformed)

    return transformed
