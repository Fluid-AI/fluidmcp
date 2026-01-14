#!/usr/bin/env python3
"""
Manual Integration Test Script for vLLM Streaming Support in FluidMCP

IMPORTANT: This is a manual integration test that requires:
1. A running FluidMCP server on http://localhost:8099
2. A vLLM model configured and started (requires GPU)

This is NOT part of the automated test suite. Use pytest for automated tests:
    pytest tests/test_streaming.py

Usage:
    python tests/manual/integration_test_streaming.py
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8099/llm/vllm/v1"

def test_non_streaming():
    """Test non-streaming chat completion"""
    print("=" * 60)
    print("TEST 1: Non-Streaming Chat Completion")
    print("=" * 60)

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            json={
                "model": "facebook/opt-125m",
                "messages": [
                    {"role": "user", "content": "Say hello in one word"}
                ],
                "max_tokens": 10,
                "stream": False
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print("✓ SUCCESS")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"✗ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def test_streaming():
    """Test streaming chat completion"""
    print("\n" + "=" * 60)
    print("TEST 2: Streaming Chat Completion")
    print("=" * 60)

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            json={
                "model": "facebook/opt-125m",
                "messages": [
                    {"role": "user", "content": "Count from 1 to 3"}
                ],
                "max_tokens": 30,
                "stream": True
            },
            stream=True,
            timeout=30
        )

        if response.status_code != 200:
            print(f"✗ FAILED with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

        print("✓ Receiving streaming response...")
        print("\nStreamed chunks:")
        print("-" * 60)

        chunk_count = 0
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')

                # Skip empty lines
                if not decoded_line.strip():
                    continue

                # Handle SSE format
                if decoded_line.startswith('data: '):
                    data_str = decoded_line[6:]  # Remove 'data: ' prefix

                    # Check for [DONE] marker
                    if data_str.strip() == '[DONE]':
                        print("\n[DONE]")
                        break

                    try:
                        chunk = json.loads(data_str)
                        chunk_count += 1

                        # Extract content from chunk
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(f"Chunk {chunk_count}: {repr(content)}")

                    except json.JSONDecodeError as e:
                        print(f"Warning: Could not parse chunk: {data_str[:100]}")

        print("-" * 60)
        print(f"✓ SUCCESS - Received {chunk_count} chunks")
        return True

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_status_endpoint():
    """Test LLM status endpoint"""
    print("\n" + "=" * 60)
    print("TEST 3: LLM Status Endpoint")
    print("=" * 60)

    try:
        response = requests.get("http://localhost:8099/api/llm/status", timeout=10)

        if response.status_code == 200:
            result = response.json()
            print("✓ SUCCESS")
            print(f"Status: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"✗ FAILED with status {response.status_code}")
            return False

    except Exception as e:
        print(f"✗ FAILED with exception: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("FluidMCP vLLM Streaming Tests")
    print("=" * 60)
    print("\nPrerequisites:")
    print("1. FluidMCP server running on http://localhost:8099")
    print("2. vLLM model configured and started")
    print("=" * 60 + "\n")

    results = []

    # Run tests
    results.append(("Non-Streaming", test_non_streaming()))
    results.append(("Streaming", test_streaming()))
    results.append(("Status", test_status_endpoint()))

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
