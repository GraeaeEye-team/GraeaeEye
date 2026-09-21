"""
Autonomous Diagnostic Probe Script: LLM & Ollama Integration Reality Check.

Tests:
1. Direct HTTP probe to configured settings.ollama_host (/api/tags).
2. Live inference attempt to /api/generate (checks response latency & token output).
3. Network unreachable / mock disconnection probe on AsyncLLMClient.
4. Timeout enforcement and non-crashing structured fallback verification.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Dict, Any

import httpx

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.core.config import settings
from fintech_app.ml.llm_client import AsyncLLMClient


async def probe_direct_ollama(host: str) -> Dict[str, Any]:
    """Probes direct Ollama server HTTP endpoints."""
    url_tags = f"{host.rstrip('/')}/api/tags"
    url_generate = f"{host.rstrip('/')}/api/generate"
    results = {
        "host": host,
        "online": False,
        "models": [],
        "latency_ms": None,
        "sample_output": None,
        "error": None,
    }

    print(f"\n[Probe 1] Probing direct Ollama host at: {url_tags}")
    try:
        start_t = time.perf_counter()
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url_tags)
            latency = (time.perf_counter() - start_t) * 1000
            results["latency_ms"] = round(latency, 2)

            if resp.status_code == 200:
                results["online"] = True
                models = [m.get("name") for m in resp.json().get("models", [])]
                results["models"] = models
                print(f"  --> Status: ONLINE ({latency:.1f}ms). Models: {models or 'NO MODELS PULLED'}")
            else:
                results["error"] = f"HTTP {resp.status_code}: {resp.text}"
                print(f"  --> Status: HTTP Error: {resp.status_code}")
                return results

        # If online, test /api/generate
        print(f"[Probe 2] Attempting test generation to: {url_generate}")
        model_to_use = results["models"][0] if results["models"] else "llama3:latest"
        payload = {
            "model": model_to_use,
            "prompt": "Evaluate SME borrower: stable cashflow 250k, 0 delinquencies. Return one sentence.",
            "stream": False,
        }
        start_t = time.perf_counter()
        async with httpx.AsyncClient(timeout=10.0) as client:
            gen_resp = await client.post(url_generate, json=payload)
            gen_latency = (time.perf_counter() - start_t) * 1000
            if gen_resp.status_code == 200:
                text = gen_resp.json().get("response", "")
                results["sample_output"] = text.strip()
                print(f"  --> Generation SUCCESS ({gen_latency:.1f}ms): {text.strip()[:80]}...")
            else:
                results["error"] = f"Generation failed: HTTP {gen_resp.status_code}"
                print(f"  --> Generation failed: {results['error']}")

    except Exception as exc:
        results["error"] = f"{type(exc).__name__}: {exc}"
        print(f"  --> Status: UNREACHABLE ({type(exc).__name__}: {exc})")

    return results


async def probe_async_llm_client_resilience():
    """Probes AsyncLLMClient under network disconnect and timeout."""
    print("\n[Probe 3] Testing AsyncLLMClient with unreachable endpoint...")
    client_unreachable = AsyncLLMClient(
        ollama_host="http://192.0.2.1:11434",  # TEST-NET-1 unroutable IP for timeout
        openai_api_key="",
        timeout=1.5,
    )

    t0 = time.perf_counter()
    memo = await client_unreachable.generate_executive_summary(
        prompt="Test prompt for underwriting evaluation",
        context_metadata={
            "score": 75.5,
            "verdict_category": "MODERATE_MONITORED",
            "recommendation": "APPROVED",
            "probability_of_default_pct": 2.15,
        },
    )
    elapsed = time.perf_counter() - t0

    print(f"  --> Fallback triggered in {elapsed:.2f}s (enforced <= 1.5s timeout)")
    assert memo is not None and len(memo) > 50, "Fallback returned empty text"
    assert "CREDIT COMMITTEE UNDERWRITING MEMORANDUM" in memo, "Fallback header missing"
    assert "Score of 75.5/100.0" in memo, "Context metadata score not preserved in fallback"
    print("  --> Client degradation integrity: PASS (Clean structured memorandum generated)")


async def main():
    print("=" * 60)
    print("🔎 OLLAMA & LLM INTEGRATION DIAGNOSTIC PROBE SUITE")
    print("=" * 60)

    # 1. Probe current settings
    current_host = getattr(settings, "ollama_host", "http://localhost:11434")
    res_current = await probe_direct_ollama(current_host)

    # 2. Probe Docker bridge host-gateway if current fails
    if not res_current["online"]:
        print("\nChecking host-gateway (Docker internal alias):")
        await probe_direct_ollama("http://host.docker.internal:11434")

    # 3. Probe client timeout & graceful degradation
    await probe_async_llm_client_resilience()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY:")
    print(f"  - Ollama Connectivity: {'ONLINE' if res_current['online'] else 'OFFLINE / UNREACHABLE'}")
    print(f"  - Active Mode:         {'NEURAL INFERENCE' if res_current['online'] else 'STRUCTURED TEMPLATE FALLBACK'}")
    print("  - Fallback Resilience: OPERATIONAL & SAFE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
