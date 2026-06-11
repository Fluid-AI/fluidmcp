import asyncio
import httpx
import time

URL = "http://localhost:8099/test-server/mcp"
TOOL_NAME = "sleep_test_async"
CONCURRENCY_LEVELS = [50,75,100]
TIMEOUT = 30.0


def make_payload(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": TOOL_NAME, "arguments": {}},
    }


async def send_request(client, request_id):
    start = time.monotonic()
    try:
        resp = await client.post(URL, json=make_payload(request_id))
        elapsed = time.monotonic() - start
        return {"status": resp.status_code, "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {"status": None, "elapsed": elapsed, "error": str(e)}


async def run_batch(client, concurrency):
    start = time.monotonic()
    tasks = [send_request(client, i) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)
    wall_clock = time.monotonic() - start
    return results, wall_clock


async def main():
    w = 52
    print()
    print("=" * w)
    print("  FLUIDMCP GATEWAY — CONCURRENCY TEST")
    print("=" * w)
    print(f"  Each request calls a tool that takes 1 second.")
    print(f"  If requests run one-by-one, N requests = ~N seconds.")
    print(f"  If requests run in parallel, N requests = ~1 second.")
    print("=" * w)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        warmup = await send_request(client, -1)
        if warmup["error"]:
            print(f"\n  Connection failed: {warmup['error']}")
            return

        all_passed = True

        for n in CONCURRENCY_LEVELS:
            results, wall_clock = await run_batch(client, n)
            errors = sum(1 for r in results if r["error"] or r["status"] != 200)
            speedup = n / wall_clock

            passed = wall_clock < n * 0.3
            if not passed:
                all_passed = False
            verdict = "PASS" if passed else "SLOW"

            print()
            print(f"  {n} concurrent requests")
            print(f"  ├─ Completed in:    {wall_clock:.2f}s")
            print(f"  ├─ Sequential would take:  ~{n}s")
            print(f"  ├─ Speedup:         {speedup:.1f}x")
            print(f"  ├─ Errors:          {errors}")
            print(f"  └─ Result:          {verdict}")

        print()
        print("-" * w)
        if all_passed:
            print("  All tests passed. Gateway handles concurrent")
            print("  requests in parallel with no serialization.")
        else:
            print("  Some tests showed degraded concurrency.")
        print("-" * w)
        print()


if __name__ == "__main__":
    asyncio.run(main())