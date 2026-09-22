"""
Unit Test Suite: Modular LLM Executors and Strategy Pattern Verification.

Verifies:
1. Conformance to `LLMExecutor` protocol.
2. `EXECUTOR_REGISTRY` catalog and dynamic lookup.
3. 1-line executor swapping with custom mock callables (lambda / async functions).
4. `with_executor` fluent cloning on `AsyncLLMClient`.
5. Seamless integration with `CreditScoringEngine.generate_llm_summary` and `generate_detailed_llm_summary`.
6. Graceful degradation to deterministic memorandum on network failures in `ollama_sdk` and `ollama_http`.
7. Mocked unit execution of `execute_ollama_sdk`, `execute_ollama_http`, and `execute_openai`.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
import pytest

from fintech_app.ml.llm_client import (
    EXECUTOR_REGISTRY,
    AsyncLLMClient,
    LLMExecutor,
    LLMGenerationResult,
    execute_ollama_http,
    execute_ollama_sdk,
    execute_openai,
    execute_structured_fallback,
    generate_structured_fallback_memo,
)
from fintech_app.ml.scoring import CreditScoringEngine


@pytest.mark.asyncio
async def test_llm_executor_protocol_conformance():
    """Validates that executors conform to the runtime-checkable LLMExecutor protocol."""
    assert isinstance(execute_ollama_sdk, LLMExecutor)
    assert isinstance(execute_ollama_http, LLMExecutor)
    assert isinstance(execute_openai, LLMExecutor)
    assert isinstance(execute_structured_fallback, LLMExecutor)

    async def custom_lambda(prompt: str, model: str, **kwargs) -> str:
        return "Custom response"

    assert isinstance(custom_lambda, LLMExecutor)


def test_executor_registry_catalog():
    """Validates that standard strategies are registered in EXECUTOR_REGISTRY."""
    expected_keys = {"ollama_sdk", "ollama_http", "openai", "fallback"}
    assert expected_keys.issubset(set(EXECUTOR_REGISTRY.keys()))
    assert EXECUTOR_REGISTRY["ollama_sdk"] is execute_ollama_sdk
    assert EXECUTOR_REGISTRY["ollama_http"] is execute_ollama_http
    assert EXECUTOR_REGISTRY["openai"] is execute_openai
    assert EXECUTOR_REGISTRY["fallback"] is execute_structured_fallback


@pytest.mark.asyncio
async def test_dynamic_executor_swapping_via_mock():
    """Validates 1-line runtime swapping of executor strategy via custom async callable."""

    async def mock_underwriter_executor(prompt: str, model: str, **kwargs) -> str:
        return f"SYNTHESIZED_MEMO: Enterprise approved with model {model}"

    client = AsyncLLMClient()
    result = await client.generate_detailed_summary(
        prompt="Synthesize underwriting dossier for SME",
        executor=mock_underwriter_executor,
    )

    assert isinstance(result, LLMGenerationResult)
    assert "SYNTHESIZED_MEMO: Enterprise approved" in result.text
    assert result.fallback_used is False
    assert result.status == "LLM_INFERENCE_SUCCESS"
    assert "mock_underwriter_executor" in result.synthesis_engine
    assert result.inference_time_ms >= 0.0


@pytest.mark.asyncio
async def test_client_with_executor_factory():
    """Validates fluent client cloning via .with_executor()."""

    async def stub_executor(prompt: str, model: str, **kwargs) -> str:
        return "Stubbed dossier response"

    base_client = AsyncLLMClient()
    custom_client = base_client.with_executor(stub_executor)

    assert custom_client.executor is stub_executor
    # Base client executor is unchanged
    assert base_client.executor != stub_executor

    summary = await custom_client.generate_executive_summary("Test prompt")
    assert summary == "Stubbed dossier response"


@pytest.mark.asyncio
async def test_scoring_engine_dynamic_executor_swap():
    """
    Validates that CreditScoringEngine supports 1-line executor swapping
    directly on generate_llm_summary and generate_detailed_llm_summary.
    """
    engine = CreditScoringEngine()
    dummy_features = [0.5] * 18
    scoring_result = engine.calculate_score(dummy_features, "Dossier text")

    async def specialized_evaluator(prompt: str, model: str, **kwargs) -> str:
        return "SPECIALIZED_EVALUATOR_DECISION: APPROVE_WITH_COVENANTS"

    # Test detailed summary with custom executor
    detailed = await engine.generate_detailed_llm_summary(
        scoring_result,
        executor=specialized_evaluator,
    )
    assert detailed.text == "SPECIALIZED_EVALUATOR_DECISION: APPROVE_WITH_COVENANTS"
    assert detailed.fallback_used is False
    assert detailed.status == "LLM_INFERENCE_SUCCESS"

    # Test string summary with custom executor
    text_summary = await engine.generate_llm_summary(
        scoring_result,
        executor=specialized_evaluator,
    )
    assert text_summary == "SPECIALIZED_EVALUATOR_DECISION: APPROVE_WITH_COVENANTS"


@pytest.mark.asyncio
async def test_offline_fallback_executor_explicit_selection():
    """Validates explicit selection of 'fallback' strategy produces structured memorandum."""
    client = AsyncLLMClient(executor="fallback")
    result = await client.generate_detailed_summary(
        prompt="Evaluate credit request",
        context_metadata={
            "score": 82.5,
            "verdict_category": "STRONG_CREDIT_PERFORMANCE",
            "recommendation": "APPROVED",
            "probability_of_default_pct": 1.25,
        },
    )

    assert result.fallback_used is True
    assert result.status == "LLM_FALLBACK_TRIGGERED"
    assert result.synthesis_engine == "fallback:template"
    assert "Score of 82.5/100.0" in result.text
    assert "STRONG_CREDIT_PERFORMANCE" in result.text
    assert "Final Underwriting Recommendation:** **APPROVED**" in result.text


@pytest.mark.asyncio
async def test_ollama_sdk_offline_graceful_degradation():
    """Validates that an unreachable host in execute_ollama_sdk cleanly triggers fallback."""
    client = AsyncLLMClient(
        ollama_host="http://192.0.2.1:11434",  # Unroutable test IP
        executor="ollama_sdk",
        timeout=0.5,
    )

    result = await client.generate_detailed_summary(
        prompt="Analyze borrower financials",
        context_metadata={"score": 60.0, "verdict_category": "MODERATE_MONITORED"},
    )

    assert result.fallback_used is True
    assert result.status == "LLM_FALLBACK_TRIGGERED"
    assert "CREDIT COMMITTEE UNDERWRITING MEMORANDUM" in result.text
    assert result.error_details is not None
    assert "ollama_sdk" in result.error_details


@pytest.mark.asyncio
async def test_unknown_executor_raises_value_error():
    """Validates that specifying an unregistered string executor raises ValueError."""
    client = AsyncLLMClient(executor="non_existent_engine")
    with pytest.raises(ValueError, match="Unknown executor 'non_existent_engine'"):
        await client.generate_detailed_summary("Test prompt")


@pytest.mark.asyncio
async def test_execute_ollama_sdk_mocked_success():
    """Validates successful execution of execute_ollama_sdk when ollama.AsyncClient responds."""
    mock_response = {"response": "Official Ollama SDK generated narrative."}
    with patch("ollama.AsyncClient.generate", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = mock_response

        text = await execute_ollama_sdk(
            prompt="Evaluate SME liquidity",
            model="llama3:latest",
            host="http://localhost:11434",
            timeout=5.0,
        )

        assert text == "Official Ollama SDK generated narrative."
        mock_generate.assert_called_once_with(
            model="llama3:latest",
            prompt="Evaluate SME liquidity",
        )


@pytest.mark.asyncio
async def test_execute_ollama_http_mocked_success():
    """Validates successful execution of execute_ollama_http when REST endpoint responds."""
    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "HTTP REST generated narrative."}
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        text = await execute_ollama_http(
            prompt="Evaluate SME leverage",
            model="llama3:latest",
            host="http://localhost:11434",
            timeout=5.0,
        )

        assert text == "HTTP REST generated narrative."
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_execute_openai_validation_and_mock():
    """Validates OpenAI executor validation on missing key and successful mocked completion."""
    # Missing key raises ValueError
    with pytest.raises(ValueError, match="OpenAI API key is missing or empty"):
        await execute_openai("prompt", "gpt-4o-mini", api_key="")

    # Mocked completion
    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI generated credit memorandum."}}]}
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        text = await execute_openai(
            prompt="Evaluate counterparty",
            model="gpt-4o-mini",
            api_key="sk-test-mock-key-12345",
            timeout=5.0,
        )

        assert text == "OpenAI generated credit memorandum."


def test_generate_structured_fallback_memo_formatting():
    """Validates precision formatting of metrics inside structured fallback memo."""
    memo = generate_structured_fallback_memo(
        prompt="Test",
        score=78.912,
        verdict="SATISFACTORY_CREDIT",
        recommendation="EXPEDITED_APPROVAL",
        pd_pct=1.876,
    )
    assert "Score of 78.9/100.0" in memo
    assert "SATISFACTORY_CREDIT" in memo
    assert "Probability of Default (PD) of **1.88%**" in memo
    assert "EXPEDITED_APPROVAL" in memo
    assert "Mandatory minimum Days Cash on Hand (DCOH >= 15 days)" in memo
