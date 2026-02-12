# Changelog

All notable changes to FluidMCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-02-10

### ⚠️ BREAKING CHANGES

#### Unified LLM API Structure
All LLM providers (Replicate, vLLM, Ollama, LM Studio) are now unified under a single API namespace.

**Old Endpoints (Deprecated)**:
- `/api/replicate/models`
- `/api/replicate/models/{model_id}/predict`
- `/api/replicate/models/{model_id}/predictions/{prediction_id}`
- `/api/replicate/models/{model_id}/predictions/{prediction_id}/cancel`
- `/api/replicate/models/{model_id}/stream`
- `/api/replicate/models/{model_id}/info`
- `/api/replicate/models/{model_id}/health`

**New Unified Endpoints**:
- `/api/llm/{model_id}/v1/chat/completions` - Unified chat completions (all providers)
- `/api/llm/{model_id}/v1/completions` - Unified text completions (all providers)
- `/api/llm/{model_id}/v1/embeddings` - Unified embeddings (all providers)

**Migration Guide**:
1. Replace all `/api/replicate/models/{model_id}/*` calls with `/api/llm/{model_id}/v1/*`
2. Use OpenAI-compatible request format for all providers
3. Provider type is auto-detected from model configuration
4. Old endpoints still work with deprecation warnings (will be removed in v2.0.0)

### Added

#### Core Features
- **Unified LLM API** - Single integration point for all LLM providers
- **Comprehensive Metrics System**
  - Prometheus-formatted metrics export (`/api/metrics`)
  - JSON metrics export (`/api/metrics/json`)
  - Per-model metrics (`/api/metrics/models/{model_id}`)
  - Metrics reset endpoint (`/api/metrics/reset`)
  - Uses `time.monotonic()` for accurate latency tracking (prevents NTP clock skew)

#### Replicate Enhancements
- **Token Bucket Rate Limiting**
  - Configurable per-model rate limits
  - Prevents API quota exhaustion
  - Stats endpoint (`/api/metrics/rate-limiters`)
- **LRU Response Cache with TTL**
  - Reduces API costs for repeated requests
  - Configurable TTL and max size per model
  - Cache stats endpoint (`/api/metrics/cache/stats`)
- **Replicate Metrics Integration**
  - Request/failure tracking
  - Prometheus metrics export
  - Cache hit rate monitoring

#### Observability
- **Metrics Tracking**
  - Request counts (total, successful, failed)
  - Latency statistics (min, max, avg)
  - Token usage (prompt, completion, total)
  - Error counts by status code
  - Uptime tracking
- **Management Endpoints**
  - Cache statistics and clearing
  - Rate limiter statistics and clearing
  - Per-model and global metrics

### Changed

#### API Structure
- All LLM endpoints unified under `/api/llm/{model_id}/v1/*` namespace
- Provider-specific endpoints deprecated (still functional with warnings)
- Consistent OpenAI-compatible API across all providers

#### Internal Improvements
- Metrics use `time.monotonic()` instead of `time.time()` for accuracy
- Improved exception handling with detailed logging and stack traces
- Pytest configuration moved to `conftest.py` for proper marker registration
- Thread-safe cache and rate limiter implementations

### Fixed

- Cache clear endpoint now returns actual count of entries cleared (not hardcoded 0)
- Rate limiter clear endpoint now returns actual count of limiters cleared
- Rate limiter stats endpoint avoids creating limiters as side effect
- Generic exception handler now logs details and returns sanitized HTTPException
- Prediction ID validation for empty/whitespace strings
- Response cache warns when different configs requested for same global instance
- Test assertion tightened to [404, 422] instead of [404, 422, 500]

### Security

#### LLM Launcher Improvements
- **Command Sanitization** - Automatically redacts sensitive patterns in logs (api-key, token, secret, password, auth, credential)
- **Environment Variable Filtering** - Allowlist approach for subprocess environment (only safe system vars passed)
- **Secure Log Files** - Log file permissions set to 0o600 (owner read/write only)
- **Path Traversal Prevention** - Model IDs sanitized in file paths

### Documentation

- **New Documentation**
  - `docs/OBSERVABILITY.md` - Comprehensive metrics and monitoring guide
  - `docs/REPLICATE_SUPPORT.md` - Complete Replicate features documentation
  - Updated `CLAUDE.md` with LLM inference sections
- **Examples**
  - `examples/replicate-inference.json` - Replicate model configuration
  - `examples/vllm-with-error-recovery.json` - vLLM with health monitoring
- **Migration Guides**
  - API endpoint migration instructions
  - Breaking changes documentation

### Testing

- **Test Coverage**: 717 tests passing
- **New Test Suites**
  - `tests/test_llm_metrics.py` - Metrics collection tests
  - `tests/test_response_cache.py` - Cache behavior tests
  - `tests/test_rate_limiter.py` - Rate limiting tests
  - `tests/test_replicate_client.py` - Replicate integration tests (25 tests)
  - `tests/conftest.py` - Centralized pytest configuration

---

## [0.1.0] - Previous Release

Initial release with basic MCP server orchestration.
