"""Explicit opt-in checks against an otherwise idle experimental MLX service."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:19095")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packed-prompt", action="store_true", help="Exercise compressed history in late-loop reads")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    base = args.url.rstrip("/")
    content = "What is 2 + 2?"
    if args.packed_prompt:
        content = "Context for this arithmetic check. " * 32 + content
    prompt = {"messages": [{"role": "user", "content": content}], "max_tokens": 8}

    def request(path, body=None):
        req = urllib.request.Request(base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def metrics():
        status, text = request("/metrics")
        assert status == 200
        return text, {line.split()[0]: float(line.split()[1]) for line in text.splitlines()
                      if line and not line.startswith("#")}

    def until(predicate, timeout=30):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if predicate():
                return
            time.sleep(.05)
        raise AssertionError("condition timed out")

    assert not json.loads(request("/slots")[1])[0]["is_processing"], "service must be idle"
    _, before = metrics()
    long_prompt = prompt | {"messages": [{"role": "user", "content": " x" * 4000}]}
    assert request("/v1/chat/completions", long_prompt)[0] == 400
    _, rejected = metrics()
    assert rejected['flashloop_generated_tokens_total'] == before['flashloop_generated_tokens_total']
    assert rejected['flashloop_model_loads_total'] == before['flashloop_model_loads_total']
    latency = []
    with ThreadPoolExecutor() as executor:
        future = executor.submit(request, "/v1/chat/completions", prompt)
        until(lambda: metrics()[1]['flashloop_requests_active'] == 1)
        assert request("/v1/chat/completions", prompt)[0] == 503
        while not future.done():
            start = time.monotonic()
            metrics()
            latency.append(time.monotonic() - start)
            time.sleep(.1)
        status, reply = future.result()
        assert status == 200, reply
    usage = json.loads(reply)["usage"]
    _, after = metrics()
    assert after['flashloop_prompt_tokens_total'] - before['flashloop_prompt_tokens_total'] == usage['prompt_tokens']
    assert after['flashloop_generated_tokens_total'] - before['flashloop_generated_tokens_total'] == usage['completion_tokens']

    if args.packed_prompt:
        assert usage["prompt_tokens"] >= 128, "packed cache must be exercised"
    for loop in range(1, 5):
        for phase, expected in (("prefill", 1), ("decode", usage["completion_tokens"] - 1)):
            name = f'flashloop_loop_passes_total{{loop="{loop}",phase="{phase}"}}'
            assert after.get(name, 0) - before.get(name, 0) == expected, name

    # Close a real TCP connection during decode; ASGI cancellation alone isn't sufficient coverage.
    parsed = urlparse(base)
    connection = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
    body = json.dumps(prompt | {"max_tokens": 1024}).encode()
    wire = (f"POST /v1/chat/completions HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body
    try:
        connection.sendall(wire)
        until(lambda: metrics()[1]['flashloop_generated_tokens_total'] > after['flashloop_generated_tokens_total'])
    finally:
        connection.shutdown(socket.SHUT_RDWR)
        connection.close()
    until(lambda: metrics()[1].get('flashloop_generation_requests_total{outcome="cancelled"}', 0)
          > after.get('flashloop_generation_requests_total{outcome="cancelled"}', 0))
    assert metrics()[1]['flashloop_requests_active'] == 0
    status, reply = request("/v1/chat/completions", prompt | {"max_tokens": 2})
    assert status == 200, reply
    text, end = metrics()
    assert end['flashloop_cache_bytes'] == 0
    assert end['flashloop_model_loads_total'] == 1, "run against a fresh service"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"checks": "passed", "usage": usage,
        "scrape_seconds": latency, "metrics": end,
        "slots": json.loads(request("/slots")[1])}, indent=2) + "\n")
    args.output.with_suffix(".prom").write_text(text)
    args.output.with_suffix(".slots.json").write_text(request("/slots")[1] + "\n")
    print(json.dumps({"checks": "passed", "max_scrape_seconds": max(latency, default=0),
                      "scrapes_during_generation": len(latency), "usage": usage}), flush=True)


if __name__ == "__main__":
    main()
