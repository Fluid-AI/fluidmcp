"""
LLM Inference Metrics Collector.

Tracks request counts, latency, errors, and token usage for LLM inference endpoints.
Provides Prometheus-compatible metrics endpoint for monitoring and alerting.
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from loguru import logger


@dataclass
class ModelMetrics:
    """Metrics for a single model."""

    # Request counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency tracking (in seconds)
    total_latency: float = 0.0
    min_latency: float = float('inf')
    max_latency: float = 0.0

    # Token usage (for cost estimation)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0

    # Error tracking
    errors_by_status: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # Provider-specific
    provider_type: Optional[str] = None

    def avg_latency(self) -> float:
        """Calculate average latency."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency / self.total_requests

    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100


class LLMMetricsCollector:
    """
    Thread-safe metrics collector for LLM inference.

    Tracks per-model metrics including request counts, latency, errors, and token usage.
    Provides Prometheus-compatible export format.
    """

    def __init__(self):
        """Initialize metrics collector."""
        self._metrics: Dict[str, ModelMetrics] = {}
        self._lock = Lock()
        self._start_time = time.time()
        logger.info("Initialized LLM metrics collector")

    def record_request_start(self, model_id: str, provider_type: str) -> float:
        """
        Record the start of a request.

        Args:
            model_id: Model identifier
            provider_type: Provider type (replicate, vllm, etc.)

        Returns:
            Start timestamp for latency calculation
        """
        with self._lock:
            if model_id not in self._metrics:
                self._metrics[model_id] = ModelMetrics(provider_type=provider_type)

            self._metrics[model_id].total_requests += 1

        return time.time()

    def record_request_success(
        self,
        model_id: str,
        start_time: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ):
        """
        Record a successful request completion.

        Args:
            model_id: Model identifier
            start_time: Request start timestamp
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens generated
        """
        latency = time.time() - start_time

        with self._lock:
            if model_id not in self._metrics:
                logger.warning(f"Metrics not initialized for model '{model_id}'")
                return

            metrics = self._metrics[model_id]
            metrics.successful_requests += 1
            metrics.total_latency += latency
            metrics.min_latency = min(metrics.min_latency, latency)
            metrics.max_latency = max(metrics.max_latency, latency)

            # Track token usage
            metrics.total_prompt_tokens += prompt_tokens
            metrics.total_completion_tokens += completion_tokens
            metrics.total_tokens += (prompt_tokens + completion_tokens)

        logger.debug(
            f"Recorded success for '{model_id}': "
            f"{latency:.3f}s, {prompt_tokens}+{completion_tokens} tokens"
        )

    def record_request_failure(
        self,
        model_id: str,
        start_time: float,
        status_code: int
    ):
        """
        Record a failed request.

        Args:
            model_id: Model identifier
            start_time: Request start timestamp
            status_code: HTTP status code of the error
        """
        latency = time.time() - start_time

        with self._lock:
            if model_id not in self._metrics:
                logger.warning(f"Metrics not initialized for model '{model_id}'")
                return

            metrics = self._metrics[model_id]
            metrics.failed_requests += 1
            metrics.total_latency += latency
            metrics.min_latency = min(metrics.min_latency, latency)
            metrics.max_latency = max(metrics.max_latency, latency)
            metrics.errors_by_status[status_code] += 1

        logger.debug(
            f"Recorded failure for '{model_id}': "
            f"{latency:.3f}s, status={status_code}"
        )

    def get_model_metrics(self, model_id: str) -> Optional[ModelMetrics]:
        """
        Get metrics for a specific model.

        Args:
            model_id: Model identifier

        Returns:
            ModelMetrics or None if not found
        """
        with self._lock:
            return self._metrics.get(model_id)

    def get_all_metrics(self) -> Dict[str, ModelMetrics]:
        """
        Get metrics for all models.

        Returns:
            Dictionary mapping model IDs to their metrics
        """
        with self._lock:
            return dict(self._metrics)

    def reset_metrics(self, model_id: Optional[str] = None):
        """
        Reset metrics for a specific model or all models.

        Args:
            model_id: Model to reset, or None to reset all
        """
        with self._lock:
            if model_id:
                if model_id in self._metrics:
                    provider_type = self._metrics[model_id].provider_type
                    self._metrics[model_id] = ModelMetrics(provider_type=provider_type)
                    logger.info(f"Reset metrics for model '{model_id}'")
            else:
                self._metrics.clear()
                self._start_time = time.time()
                logger.info("Reset all metrics")

    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = [
            "# HELP fluidmcp_llm_requests_total Total number of LLM inference requests",
            "# TYPE fluidmcp_llm_requests_total counter",
            "# HELP fluidmcp_llm_requests_successful Number of successful requests",
            "# TYPE fluidmcp_llm_requests_successful counter",
            "# HELP fluidmcp_llm_requests_failed Number of failed requests",
            "# TYPE fluidmcp_llm_requests_failed counter",
            "# HELP fluidmcp_llm_latency_seconds Request latency statistics",
            "# TYPE fluidmcp_llm_latency_seconds gauge",
            "# HELP fluidmcp_llm_tokens_total Total tokens processed",
            "# TYPE fluidmcp_llm_tokens_total counter",
            "# HELP fluidmcp_llm_errors_by_status Error counts by HTTP status code",
            "# TYPE fluidmcp_llm_errors_by_status counter",
        ]

        with self._lock:
            for model_id, metrics in self._metrics.items():
                labels = f'model_id="{model_id}",provider="{metrics.provider_type}"'

                # Request counts
                lines.append(f'fluidmcp_llm_requests_total{{{labels}}} {metrics.total_requests}')
                lines.append(f'fluidmcp_llm_requests_successful{{{labels}}} {metrics.successful_requests}')
                lines.append(f'fluidmcp_llm_requests_failed{{{labels}}} {metrics.failed_requests}')

                # Latency
                lines.append(f'fluidmcp_llm_latency_seconds{{{labels},stat="avg"}} {metrics.avg_latency():.6f}')
                if metrics.min_latency != float('inf'):
                    lines.append(f'fluidmcp_llm_latency_seconds{{{labels},stat="min"}} {metrics.min_latency:.6f}')
                lines.append(f'fluidmcp_llm_latency_seconds{{{labels},stat="max"}} {metrics.max_latency:.6f}')

                # Token usage
                lines.append(f'fluidmcp_llm_tokens_total{{{labels},type="prompt"}} {metrics.total_prompt_tokens}')
                lines.append(f'fluidmcp_llm_tokens_total{{{labels},type="completion"}} {metrics.total_completion_tokens}')
                lines.append(f'fluidmcp_llm_tokens_total{{{labels},type="total"}} {metrics.total_tokens}')

                # Errors by status
                for status_code, count in metrics.errors_by_status.items():
                    error_labels = f'{labels},status_code="{status_code}"'
                    lines.append(f'fluidmcp_llm_errors_by_status{{{error_labels}}} {count}')

        # Add uptime
        uptime = time.time() - self._start_time
        lines.append(f'# HELP fluidmcp_uptime_seconds Time since metrics collection started')
        lines.append(f'# TYPE fluidmcp_uptime_seconds gauge')
        lines.append(f'fluidmcp_uptime_seconds {uptime:.0f}')

        return '\n'.join(lines) + '\n'

    def export_json(self) -> Dict[str, any]:
        """
        Export metrics in JSON format.

        Returns:
            Dictionary containing all metrics
        """
        with self._lock:
            result = {
                "uptime_seconds": time.time() - self._start_time,
                "models": {}
            }

            for model_id, metrics in self._metrics.items():
                result["models"][model_id] = {
                    "provider_type": metrics.provider_type,
                    "requests": {
                        "total": metrics.total_requests,
                        "successful": metrics.successful_requests,
                        "failed": metrics.failed_requests,
                        "success_rate_percent": round(metrics.success_rate(), 2),
                        "error_rate_percent": round(metrics.error_rate(), 2),
                    },
                    "latency": {
                        "avg_seconds": round(metrics.avg_latency(), 3),
                        "min_seconds": round(metrics.min_latency, 3) if metrics.min_latency != float('inf') else None,
                        "max_seconds": round(metrics.max_latency, 3),
                    },
                    "tokens": {
                        "prompt": metrics.total_prompt_tokens,
                        "completion": metrics.total_completion_tokens,
                        "total": metrics.total_tokens,
                    },
                    "errors_by_status": dict(metrics.errors_by_status),
                }

            return result


# Global metrics collector instance
_metrics_collector: Optional[LLMMetricsCollector] = None


def get_metrics_collector() -> LLMMetricsCollector:
    """
    Get the global metrics collector instance (singleton pattern).

    Returns:
        LLMMetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = LLMMetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """Reset the global metrics collector (useful for testing)."""
    global _metrics_collector
    _metrics_collector = None
