#!/usr/bin/env python3
"""
Manual Integration Test for vLLM Multi-Model Support in FluidMCP

IMPORTANT: This is a manual integration test that requires:
1. A running FluidMCP server on http://localhost:8099
2. Multiple vLLM models configured and started (requires GPU)

This is NOT part of the automated test suite.

Usage:
    python tests/manual/integration_test_multi_model.py

Environment Variables:
    FLUIDMCP_BASE_URL: Base URL for FluidMCP server (default: http://localhost:8099)
    VLLM_MODEL_1_ID: First vLLM model identifier (default: vllm-opt)
    VLLM_MODEL_2_ID: Second vLLM model identifier (default: vllm-gpt2)
"""
import requests
import json
import sys
import os

# Configurable via environment variables
FLUIDMCP_BASE_URL = os.getenv("FLUIDMCP_BASE_URL", "http://localhost:8099")
VLLM_MODEL_1_ID = os.getenv("VLLM_MODEL_1_ID", "vllm-opt")
VLLM_MODEL_2_ID = os.getenv("VLLM_MODEL_2_ID", "vllm-gpt2")


def test_status_endpoint():
    """Test LLM status endpoint shows all models"""
    print("=" * 60)
    print("TEST 1: Multi-Model Status Endpoint")
    print("=" * 60)

    try:
        response = requests.get(f"{FLUIDMCP_BASE_URL}/api/llm/status", timeout=10)

        if response.status_code == 200:
            result = response.json()
            print("✓ SUCCESS")
            print(f"Status: {json.dumps(result, indent=2)}")

            # Validate both models are present
            models = result.get("models", {})
            if VLLM_MODEL_1_ID in models and VLLM_MODEL_2_ID in models:
                print(f"✓ Both models found: {VLLM_MODEL_1_ID}, {VLLM_MODEL_2_ID}")
                return True
            else:
                print(f"✗ Expected models not found. Got: {list(models.keys())}")
                return False
        else:
            print(f"✗ FAILED with status {response.status_code}")
            return False

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def test_model_1_inference():
    """Test inference with first model"""
    print("\n" + "=" * 60)
    print(f"TEST 2: Inference with Model 1 ({VLLM_MODEL_1_ID})")
    print("=" * 60)

    try:
        response = requests.post(
            f"{FLUIDMCP_BASE_URL}/llm/v1/chat/completions",
            json={
                "model": VLLM_MODEL_1_ID,
                "messages": [
                    {"role": "user", "content": "Say 'Hello from OPT' in one sentence"}
                ],
                "max_tokens": 20,
                "stream": False
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print("✓ SUCCESS")
            print(f"Model: {result.get('model', 'unknown')}")
            print(f"Response: {content}")
            return True
        else:
            print(f"✗ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def test_model_2_inference():
    """Test inference with second model"""
    print("\n" + "=" * 60)
    print(f"TEST 3: Inference with Model 2 ({VLLM_MODEL_2_ID})")
    print("=" * 60)

    try:
        response = requests.post(
            f"{FLUIDMCP_BASE_URL}/llm/v1/chat/completions",
            json={
                "model": VLLM_MODEL_2_ID,
                "messages": [
                    {"role": "user", "content": "Say 'Hello from GPT-2' in one sentence"}
                ],
                "max_tokens": 20,
                "stream": False
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print("✓ SUCCESS")
            print(f"Model: {result.get('model', 'unknown')}")
            print(f"Response: {content}")
            return True
        else:
            print(f"✗ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def test_concurrent_inference():
    """Test concurrent requests to both models"""
    print("\n" + "=" * 60)
    print("TEST 4: Concurrent Inference (Both Models)")
    print("=" * 60)

    import concurrent.futures

    def query_model_1():
        response = requests.post(
            f"{FLUIDMCP_BASE_URL}/llm/v1/chat/completions",
            json={
                "model": VLLM_MODEL_1_ID,
                "messages": [{"role": "user", "content": "Count to 3"}],
                "max_tokens": 15,
                "stream": False
            },
            timeout=30
        )
        return ("Model 1", response.status_code, response.json() if response.status_code == 200 else response.text)

    def query_model_2():
        response = requests.post(
            f"{FLUIDMCP_BASE_URL}/llm/v1/chat/completions",
            json={
                "model": VLLM_MODEL_2_ID,
                "messages": [{"role": "user", "content": "Count to 3"}],
                "max_tokens": 15,
                "stream": False
            },
            timeout=30
        )
        return ("Model 2", response.status_code, response.json() if response.status_code == 200 else response.text)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(query_model_1)
            future2 = executor.submit(query_model_2)

            results = [future1.result(), future2.result()]

        success = True
        for model_name, status_code, result in results:
            if status_code == 200:
                content = result["choices"][0]["message"]["content"]
                print(f"✓ {model_name}: {content[:50]}")
            else:
                print(f"✗ {model_name} failed: {status_code}")
                success = False

        if success:
            print("✓ SUCCESS - Both models responded concurrently")
        return success

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streaming_model_1():
    """Test streaming with first model"""
    print("\n" + "=" * 60)
    print(f"TEST 5: Streaming with Model 1 ({VLLM_MODEL_1_ID})")
    print("=" * 60)

    try:
        response = requests.post(
            f"{FLUIDMCP_BASE_URL}/llm/v1/chat/completions",
            json={
                "model": VLLM_MODEL_1_ID,
                "messages": [
                    {"role": "user", "content": "Count from 1 to 3"}
                ],
                "max_tokens": 20,
                "stream": True
            },
            stream=True,
            timeout=30
        )

        if response.status_code != 200:
            print(f"✗ FAILED with status {response.status_code}")
            return False

        print("✓ Receiving streaming response...")
        chunk_count = 0
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data_str = decoded_line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data_str)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            if delta.get('content'):
                                chunk_count += 1
                    except json.JSONDecodeError:
                        # Ignore lines that are not valid JSON (SSE comments, empty lines, keep-alive, or malformed chunks)
                        pass

        print(f"✓ SUCCESS - Received {chunk_count} chunks")
        return True

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("FluidMCP vLLM Multi-Model Tests")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Base URL: {FLUIDMCP_BASE_URL}")
    print(f"  Model 1 ID: {VLLM_MODEL_1_ID} ({TEST_MODEL_1})")
    print(f"  Model 2 ID: {VLLM_MODEL_2_ID} ({TEST_MODEL_2})")
    print("\nPrerequisites:")
    print(f"1. FluidMCP server running on {FLUIDMCP_BASE_URL}")
    print("2. Multiple vLLM models configured and started")
    print(f"3. Config: examples/vllm-multi-model-config.json")
    print("=" * 60 + "\n")

    results = []

    # Run tests
    results.append(("Status Endpoint", test_status_endpoint()))
    results.append(("Model 1 Inference", test_model_1_inference()))
    results.append(("Model 2 Inference", test_model_2_inference()))
    results.append(("Concurrent Inference", test_concurrent_inference()))
    results.append(("Model 1 Streaming", test_streaming_model_1()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    print("=" * 60 + "\n")

    # Exit with appropriate code
    sys.exit(0 if passed_count == total_count else 1)


if __name__ == "__main__":
    main()
