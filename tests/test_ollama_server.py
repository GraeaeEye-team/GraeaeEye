"""
Test Suite for Ollama Server Health & Real Neural Inference.

Verifies:
1. HTTP connectivity and server responsiveness (/api/tags and /api/version).
2. Presence of downloaded LLM models (e.g. llama3.2:1b or llama3:8b).
3. Live end-to-end inference generation with latency benchmarking.
4. Integration with GraeaeEye AsyncLLMClient under 'ollama' executor strategy.

Usage:
    pytest tests/test_ollama_server.py -v
    python tests/test_ollama_server.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import List

import httpx
import pytest

sys.path.insert(0, os.path.abspath("src"))

from fintech_app.core.config import settings
from fintech_app.ml.llm_client import AsyncLLMClient, LLMGenerationResult


def resolve_local_ollama_host() -> str:
    """
    Resolves the Ollama host URL for host-side execution.
    Converts 'host.docker.internal' to '127.0.0.1' so the test works smoothly
    whether run directly on the host or inside a container.
    """
    raw_host = (
        os.getenv("OLLAMA_HOST")
        or getattr(settings, "ollama_host", "")
        or "http://127.0.0.1:11434"
    ).strip()

    if not raw_host:
        raw_host = "http://127.0.0.1:11434"

    # Replace host.docker.internal with 127.0.0.1 for local host runner
    resolved = raw_host.replace("host.docker.internal", "127.0.0.1")
    return resolved.rstrip("/")


OLLAMA_BASE_URL = resolve_local_ollama_host()
TARGET_MODEL = (os.getenv("LLM_MODEL") or getattr(settings, "llm_model", "") or "llama3.2:1b").strip()


def is_ollama_online() -> bool:
    """Synchronous probe to determine if Ollama daemon is currently online."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


# Skip fixture helper when Ollama daemon is intentionally not running
requires_ollama = pytest.mark.skipif(
    not is_ollama_online(),
    reason=(
        f"Ollama server is not active at {OLLAMA_BASE_URL}. "
        "Run './setup_ollama.sh' to start Ollama before running this test."
    ),
)


@pytest.mark.asyncio
@requires_ollama
async def test_ollama_server_health():
    """
    Test 1: Check HTTP health and latency of Ollama server.
    Ensures the daemon responds to /api/tags in under 2000ms.
    """
    start_t = time.perf_counter()
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")

    latency_ms = (time.perf_counter() - start_t) * 1000

    assert resp.status_code == 200, f"Expected HTTP 200, got {resp.status_code}: {resp.text}"
    assert latency_ms < 2000.0, f"Ollama healthcheck too slow: {latency_ms:.1f}ms"

    data = resp.json()
    assert "models" in data, "Ollama response missing 'models' key"
    print(f"\n[PASS] Ollama server is healthy at {OLLAMA_BASE_URL} (latency: {latency_ms:.1f}ms)")


@pytest.mark.asyncio
@requires_ollama
async def test_ollama_model_availability():
    """
    Test 2: Check that at least one model is downloaded and accessible.
    """
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")

    assert resp.status_code == 200
    models_data = resp.json().get("models", [])
    model_names: List[str] = [m.get("name", "") for m in models_data]

    assert len(model_names) > 0, (
        f"Ollama is running at {OLLAMA_BASE_URL}, but no models are installed. "
        f"Run: ollama pull {TARGET_MODEL}"
    )

    # Check if target model or any variant is present
    target_clean = TARGET_MODEL.split(":")[0]
    matched = [m for m in model_names if target_clean in m]
    print(f"\n[PASS] Installed models in Ollama: {model_names}")
    if matched:
        print(f"       Target model '{TARGET_MODEL}' is ready: {matched[0]}")


@pytest.mark.asyncio
@requires_ollama
async def test_ollama_live_inference():
    """
    Test 3: Execute a direct live inference request (/api/generate).
    Verifies that the model accepts prompts and returns non-empty generated text.
    """
    # Fetch available models
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
    models = [m.get("name") for m in resp.json().get("models", [])]
    model_to_use = models[0] if models else TARGET_MODEL

    payload = {
        "model": model_to_use,
        "prompt": "Reply with exactly one short sentence: How to assess SME credit risk?",
        "stream": False,
    }

    start_t = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        gen_resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
    elapsed_sec = time.perf_counter() - start_t

    assert gen_resp.status_code == 200, f"Inference failed with HTTP {gen_resp.status_code}: {gen_resp.text}"
    response_json = gen_resp.json()
    generated_text = response_json.get("response", "").strip()

    assert len(generated_text) > 10, f"Generated text too short or empty: '{generated_text}'"
    print(f"\n[PASS] Live inference with '{model_to_use}' in {elapsed_sec:.2f}s:")
    print(f"       Response: \"{generated_text[:120]}...\"")


@pytest.mark.asyncio
@requires_ollama
async def test_async_llm_client_integration():
    """
    Test 4: Verify full application integration through AsyncLLMClient.
    Ensures that our application client connects to Ollama, generates detailed memorandum,
    sets status='LLM_INFERENCE_SUCCESS', and does NOT trigger fallback.
    """
    client = AsyncLLMClient(
        ollama_host=OLLAMA_BASE_URL,
        model=TARGET_MODEL,
        executor="ollama",
        timeout=60.0,
    )

    test_metadata = {
        "final_score": 67.5,
        "risk_band": "MODERATE_MONITORED",
        "recommendation": "APPROVED",
        "probability_of_default": 0.22,
    }

    test_prompt = (
        "Draft a brief 2-paragraph Underwriting Memorandum for VICTORIA AGRO-EXPORT SRL. "
        "Score: 67.5/100. Stable cash flow, moderate trade debt."
    )

    result: LLMGenerationResult = await client.generate_detailed_summary(
        prompt=test_prompt,
        context_metadata=test_metadata,
        executor="ollama",
    )

    assert result is not None
    assert result.status == "LLM_INFERENCE_SUCCESS", (
        f"Expected LLM_INFERENCE_SUCCESS, got {result.status}. "
        f"Error details: {result.error_details}"
    )
    assert not result.fallback_used, "Fallback was unexpectedly used instead of Ollama inference"
    assert len(result.text) > 50, "Generated memorandum text is too short"
    assert "ollama" in result.synthesis_engine.lower(), f"Unexpected engine: {result.synthesis_engine}"

    print("\n[PASS] Application AsyncLLMClient generated memorandum successfully:")
    print(f"       Engine: {result.synthesis_engine}")
    print(f"       Inference time: {result.inference_time_ms:.1f}ms")
    print(f"       Text preview: \"{result.text[:150]}...\"")


# ------------------------------------------------------------------------------
# Standalone CLI execution
# ------------------------------------------------------------------------------
async def run_standalone_diagnostics():
    print("=" * 70)
    print("  GraeaeEye: Комплексный тест работоспособности сервера Ollama  ")
    print("=" * 70)
    print(f"Целевой адрес:  {OLLAMA_BASE_URL}")
    print(f"Целевая модель: {TARGET_MODEL}\n")

    if not is_ollama_online():
        print("❌ СТАТУС: Сервер Ollama НЕ ЗАПУЩЕН или порт недоступен.")
        print(f"   Адрес: {OLLAMA_BASE_URL}")
        print("\n👉 Чтобы запустить Ollama, выполните команду:")
        print("   ./setup_ollama.sh\n")
        sys.exit(1)

    print("✓ Сервер Ollama обнаружен и отвечает на запросы!")
    print("\nЗапуск проверочных тестов...")

    try:
        await test_ollama_server_health()
        await test_ollama_model_availability()
        await test_ollama_live_inference()
        await test_async_llm_client_integration()
        print("\n" + "=" * 70)
        print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ! Сервер Ollama полностью готов к работе.")
        print("=" * 70)
    except AssertionError as ae:
        print(f"\n❌ Ошибка проверки: {ae}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Непредвиденная ошибка: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_standalone_diagnostics())

