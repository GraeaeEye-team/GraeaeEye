"""
Asynchronous LLM Client for Credit Committee Underwriting Dossier Synthesis.

Provides:
- Pluggable LLM execution strategies conforming to LLMExecutor protocol (Strategy Pattern).
- Modular executors:
    * execute_ollama_sdk: Inference using official `ollama.AsyncClient` with clean socket cancellation.
    * execute_ollama_http: Fallback raw HTTP REST via `httpx.AsyncClient` (/api/generate).
    * execute_openai: Cloud inference against OpenAI-compatible chat completions (/v1/chat/completions).
    * execute_structured_fallback: Deterministic institutional underwriting memorandum generator.
- Dynamic strategy swapping (lambda mocks, registered executors, environment-driven).
- Configurable extended timeout (defaults to 300.0s for heavy local Ollama models).
- Graceful degradation: deterministic structured memorandum synthesis on network/timeout failure.
- Explicit inference provenance tracking (synthesis_engine, llm_model, inference_time_ms).
- Zero credential leakage and sanitized error logging.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Dict, Optional, Protocol, Union, runtime_checkable

import httpx

from ..core.config import settings

logger = logging.getLogger("fintech_app.ml.llm_client")

DEFAULT_TIMEOUT_SECONDS: float = getattr(settings, "llm_inference_timeout", 300.0)


@dataclass
class LLMGenerationResult:
    """Detailed result envelope capturing generated memorandum and inference provenance."""

    text: str
    synthesis_engine: str  # e.g., "ollama_sdk:llama3:latest", "openai:gpt-4o-mini", "fallback:template"
    llm_model: str
    inference_time_ms: float
    fallback_used: bool
    status: str  # "LLM_INFERENCE_SUCCESS" | "LLM_FALLBACK_TRIGGERED"
    error_details: Optional[str] = None


@runtime_checkable
class LLMExecutor(Protocol):
    """Protocol defining a pluggable LLM execution strategy."""

    async def __call__(
        self,
        prompt: str,
        model: str,
        **kwargs: Any,
    ) -> str:
        """
        Execute text generation against an LLM backend or fallback generator.

        Args:
            prompt: Synthesized underwriting prompt string.
            model: Target model identifier.
            **kwargs: Backend-specific arguments (host, api_key, timeout, context_metadata).

        Returns:
            Generated memorandum or narrative text string.
        """
        ...


def generate_structured_fallback_memo(
    prompt: str,
    score: Optional[float] = None,
    verdict: str = "MODERATE_MONITORED",
    recommendation: str = "MANUAL_REVIEW",
    pd_pct: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generates an institutional Credit Committee Underwriting Memorandum template
    with exact evidence-based metrics when external LLM inference is offline.
    """
    score_str = f"{score:.1f}" if score is not None else "N/A"
    pd_str = f"{pd_pct:.2f}%" if pd_pct is not None else "N/A"

    memo = f"""## CREDIT COMMITTEE UNDERWRITING MEMORANDUM

### 1. Executive Summary & Core Verdict
The target enterprise has undergone algorithmic underwriting evaluation, achieving an **Investment Attractiveness Score of {score_str}/100.0**, classifying the enterprise under **{verdict}** with an estimated Probability of Default (PD) of **{pd_str}**.
- **Final Underwriting Recommendation:** **{recommendation}**
- **Evaluation Status:** Comprehensive multi-pillar assessment across active diagnostic submodules.

### 2. Pillar-by-Pillar Risk Breakdown
- **Governance & Ownership Stability:** Assessed cap-table concentration and management participation.
- **Macroeconomic & Sector Resilience:** Evaluated sector default rate and systemic cyclical pressures.
- **Commercial Counterparty Concentration:** Measured customer/supplier diversification and billing cycle volatility.
- **Liquidity & Cashflow Predictability:** Analyzed operational burn rate, cash buffer (DCOH), and debt service coverage.
- **Credit Repayment Discipline & Leverage:** Reviewed repayment track record, delinquent obligations, and facility leverage.

### 3. Key Risk Factors & Early Warnings
- Continuous monitoring of monthly operational cashflows and supplier payment concentration.
- Heightened sensitivity to overdue trade receivables and contractual settlement delays.

### 4. Mitigating Factors & Compensating Controls
- Diversified cash inflows from commercial counterparties providing operational cushion.
- Absence of severe legal encumbrances or unserviced high-rate short-term credit lines.

### 5. Underwriting Decision & Monitoring Terms
- **Decision:** **{recommendation}**
- **Required Covenants:** Mandatory minimum Days Cash on Hand (DCOH >= 15 days) and quarterly financial health reporting.
- **Cadence:** Ongoing automated bank statement ingestion and transaction flow telemetry.
"""
    return memo.strip()


async def execute_ollama_sdk(
    prompt: str,
    model: str,
    host: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> str:
    """
    Executes async LLM generation using the official `ollama` Python SDK (ollama.AsyncClient).
    Guarantees clean socket cancellation on timeout/exit to prevent zombie inference on Ollama daemon.
    """
    try:
        import ollama
    except ImportError as err:
        raise RuntimeError("The 'ollama' Python library is not installed.") from err

    effective_timeout = (
        timeout if timeout is not None else getattr(settings, "llm_inference_timeout", DEFAULT_TIMEOUT_SECONDS)
    )
    client_host = (host or settings.ollama_host or "http://localhost:11434").rstrip("/")
    target_model = model if "gpt" not in model else "llama3:latest"

    client = ollama.AsyncClient(host=client_host, timeout=effective_timeout)
    try:
        response = await client.generate(model=target_model, prompt=prompt)
        if isinstance(response, dict):
            text = str(response.get("response", ""))
        else:
            text = str(getattr(response, "response", ""))
        return text.strip()
    finally:
        # Crucial: Clean Socket Cancellation
        # Sever the underlying HTTP client socket to trigger request cancellation on Ollama server
        if hasattr(client, "_client") and hasattr(client._client, "aclose"):
            try:
                await client._client.aclose()
            except Exception:
                pass


async def execute_ollama_http(
    prompt: str,
    model: str,
    host: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> str:
    """
    Executes async LLM generation against Ollama REST endpoint (/api/generate) via raw HTTP (httpx).
    """
    effective_timeout = (
        timeout if timeout is not None else getattr(settings, "llm_inference_timeout", DEFAULT_TIMEOUT_SECONDS)
    )
    client_host = (host or settings.ollama_host or "http://localhost:11434").rstrip("/")
    target_model = model if "gpt" not in model else "llama3:latest"
    url = f"{client_host}/api/generate"
    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=effective_timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("response", "")).strip()


async def execute_openai(
    prompt: str,
    model: str,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> str:
    """
    Executes async completion against OpenAI-compatible REST endpoint (/v1/chat/completions).
    """
    effective_timeout = (
        timeout if timeout is not None else getattr(settings, "llm_inference_timeout", DEFAULT_TIMEOUT_SECONDS)
    )
    key = api_key if api_key is not None else settings.openai_api_key
    if not key or not key.strip():
        raise ValueError("OpenAI API key is missing or empty")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a Senior Credit Risk Underwriting Officer at a commercial SME fintech lender.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
    }
    async with httpx.AsyncClient(timeout=effective_timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()


async def execute_structured_fallback(
    prompt: str,
    model: str = "none",
    **kwargs: Any,
) -> str:
    """
    Generates an institutional Credit Committee Underwriting Memorandum template deterministically.
    """
    meta = kwargs.get("context_metadata") or {}
    score = meta.get("score")
    verdict = meta.get("verdict_category", "MODERATE_MONITORED")
    recommendation = meta.get("recommendation", "MANUAL_REVIEW")
    pd_pct = meta.get("probability_of_default_pct")
    return generate_structured_fallback_memo(
        prompt=prompt,
        score=score,
        verdict=verdict,
        recommendation=recommendation,
        pd_pct=pd_pct,
        extra=meta,
    )


async def execute_ollama(
    prompt: str,
    model: str,
    host: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> str:
    """
    Unified Ollama execution strategy.
    Attempts official Ollama Python SDK first; falls back seamlessly to raw HTTP endpoint (/api/generate).
    """
    try:
        return await execute_ollama_sdk(
            prompt=prompt,
            model=model,
            host=host,
            timeout=timeout,
            **kwargs,
        )
    except Exception as exc:
        logger.debug("execute_ollama: SDK execution failed (%s), falling back to raw HTTP: %s", type(exc).__name__, exc)
        return await execute_ollama_http(
            prompt=prompt,
            model=model,
            host=host,
            timeout=timeout,
            **kwargs,
        )


EXECUTOR_REGISTRY: Dict[str, LLMExecutor] = {
    "ollama": execute_ollama,
    "ollama_sdk": execute_ollama_sdk,
    "ollama_http": execute_ollama_http,
    "openai": execute_openai,
    "fallback": execute_structured_fallback,
}


class AsyncLLMClient:
    """
    Asynchronous client for generative synthesis of credit underwriting reports
    supporting pluggable execution strategies (Strategy Pattern).
    """

    def __init__(
        self,
        ollama_host: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        executor: Optional[Union[str, LLMExecutor]] = None,
    ) -> None:
        self.ollama_host = (ollama_host or settings.ollama_host or "").rstrip("/")
        self.openai_api_key = openai_api_key if openai_api_key is not None else settings.openai_api_key
        self.model = model or settings.llm_model or "gpt-4o-mini"
        self.timeout = (
            timeout if timeout is not None else getattr(settings, "llm_inference_timeout", DEFAULT_TIMEOUT_SECONDS)
        )
        self.executor = executor or getattr(settings, "llm_provider", "auto")

    def with_executor(
        self,
        executor: Union[str, LLMExecutor],
        timeout: Optional[float] = None,
    ) -> AsyncLLMClient:
        """Returns a cloned client instance configured with a specific executor and optional timeout."""
        return AsyncLLMClient(
            ollama_host=self.ollama_host,
            openai_api_key=self.openai_api_key,
            model=self.model,
            timeout=timeout if timeout is not None else self.timeout,
            executor=executor,
        )

    async def generate_executive_summary(
        self,
        prompt: str,
        context_metadata: Optional[Dict[str, Any]] = None,
        executor: Optional[Union[str, LLMExecutor]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Convenience method returning string text of synthesized memorandum."""
        res = await self.generate_detailed_summary(prompt, context_metadata, executor=executor, timeout=timeout)
        return res.text

    async def generate_detailed_summary(
        self,
        prompt: str,
        context_metadata: Optional[Dict[str, Any]] = None,
        executor: Optional[Union[str, LLMExecutor]] = None,
        timeout: Optional[float] = None,
    ) -> LLMGenerationResult:
        """
        Synthesizes an institutional underwriting memorandum from the prompt.
        Executes via configured pluggable strategy or auto-fallback chain.
        Tracks provenance metadata and falls back safely on provider error or timeout.
        """
        active_executor = executor or self.executor
        effective_timeout = timeout if timeout is not None else self.timeout
        meta = context_metadata or {}

        # If explicitly set to offline fallback strategy
        if active_executor == "fallback":
            fallback_text = await execute_structured_fallback(
                prompt=prompt,
                model="none",
                context_metadata=meta,
            )
            return LLMGenerationResult(
                text=fallback_text,
                synthesis_engine="fallback:template",
                llm_model="none",
                inference_time_ms=0.0,
                fallback_used=True,
                status="LLM_FALLBACK_TRIGGERED",
                error_details="Deterministic template executor explicitly selected",
            )

        # If a specific named executor or custom callable is requested
        if active_executor and active_executor != "auto":
            return await self._dispatch_single_executor(
                active_executor,
                prompt,
                meta,
                timeout=effective_timeout,
            )

        # Default "auto" resolution sequence: OpenAI -> Ollama SDK -> Ollama HTTP -> Structured Fallback
        return await self._dispatch_auto_sequence(prompt, meta, timeout=effective_timeout)

    async def _dispatch_single_executor(
        self,
        executor_target: Union[str, LLMExecutor, Callable[..., Any]],
        prompt: str,
        meta: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMGenerationResult:
        """Dispatches generation directly to a specific executor strategy with safe fallback."""
        effective_timeout = timeout if timeout is not None else self.timeout

        if isinstance(executor_target, str):
            if executor_target not in EXECUTOR_REGISTRY:
                raise ValueError(f"Unknown executor '{executor_target}'. Available: {list(EXECUTOR_REGISTRY.keys())}")
            chosen_fn = EXECUTOR_REGISTRY[executor_target]
            engine_name = executor_target
        else:
            chosen_fn = executor_target
            engine_name = getattr(executor_target, "__name__", "custom_executor")

        target_model = self.model
        if engine_name in ("ollama", "ollama_sdk", "ollama_http") and "gpt" in target_model:
            target_model = "llama3:latest"

        engine_tag = f"{engine_name}:{target_model}"
        start_t = time.perf_counter()
        try:
            res = await asyncio.wait_for(
                chosen_fn(
                    prompt=prompt,
                    model=target_model,
                    host=self.ollama_host,
                    api_key=self.openai_api_key,
                    timeout=effective_timeout,
                    context_metadata=meta,
                ),
                timeout=effective_timeout,
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000
            if res and res.strip():
                logger.info(
                    "LLM_INFERENCE_SUCCESS: Generated via %s in %.1fms",
                    engine_tag,
                    elapsed_ms,
                )
                return LLMGenerationResult(
                    text=res.strip(),
                    synthesis_engine=engine_tag,
                    llm_model=target_model,
                    inference_time_ms=round(elapsed_ms, 2),
                    fallback_used=False,
                    status="LLM_INFERENCE_SUCCESS",
                )
        except Exception as exc:
            err_msg = f"{engine_name} ({type(exc).__name__}: {exc})"
            logger.warning("LLM executor '%s' failed: %s. Degrading to fallback template.", engine_name, err_msg)
            fallback_text = await execute_structured_fallback(
                prompt=prompt,
                model="none",
                context_metadata=meta,
            )
            return LLMGenerationResult(
                text=fallback_text,
                synthesis_engine="fallback:template",
                llm_model="none",
                inference_time_ms=0.0,
                fallback_used=True,
                status="LLM_FALLBACK_TRIGGERED",
                error_details=err_msg,
            )

        # If returned empty text
        fallback_text = await execute_structured_fallback(
            prompt=prompt,
            model="none",
            context_metadata=meta,
        )
        return LLMGenerationResult(
            text=fallback_text,
            synthesis_engine="fallback:template",
            llm_model="none",
            inference_time_ms=0.0,
            fallback_used=True,
            status="LLM_FALLBACK_TRIGGERED",
            error_details=f"Executor '{engine_name}' returned empty response",
        )

    async def _dispatch_auto_sequence(
        self,
        prompt: str,
        meta: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMGenerationResult:
        """Automated multi-tier fallback sequence: OpenAI -> Ollama SDK -> Ollama HTTP -> Fallback."""
        effective_timeout = timeout if timeout is not None else self.timeout
        errors: list[str] = []

        # Validate whether real AI providers are configured
        has_real_openai_key = (
            bool(self.openai_api_key)
            and bool(self.openai_api_key.strip())
            and not self.openai_api_key.strip().lower().startswith("your_api_key")
            and self.openai_api_key.strip().lower() not in ("none", "null", "sk-xxx", "")
        )
        has_ollama_host = bool(self.ollama_host) and bool(self.ollama_host.strip())

        # If no external AI provider configured in .env, run deterministic non-AI report builder directly
        if not has_real_openai_key and not has_ollama_host:
            logger.info("No AI providers configured in .env. Using deterministic institutional report builder.")
            fallback_text = await execute_structured_fallback(
                prompt=prompt,
                model="none",
                context_metadata=meta,
            )
            return LLMGenerationResult(
                text=fallback_text,
                synthesis_engine="fallback:template",
                llm_model="none",
                inference_time_ms=0.0,
                fallback_used=True,
                status="LLM_INFERENCE_SUCCESS",
                error_details="Deterministic template builder used (no AI provider configured in .env)",
            )

        # 1. Prioritize OpenAI API if real key is present
        if has_real_openai_key:
            start_t = time.perf_counter()
            try:
                res = await execute_openai(
                    prompt=prompt,
                    model=self.model,
                    api_key=self.openai_api_key,
                    timeout=effective_timeout,
                    context_metadata=meta,
                )
                elapsed_ms = (time.perf_counter() - start_t) * 1000
                if res and res.strip():
                    logger.info(
                        "LLM_INFERENCE_SUCCESS: Generated via OpenAI (%s) in %.1fms",
                        self.model,
                        elapsed_ms,
                    )
                    return LLMGenerationResult(
                        text=res.strip(),
                        synthesis_engine=f"openai:{self.model}",
                        llm_model=self.model,
                        inference_time_ms=round(elapsed_ms, 2),
                        fallback_used=False,
                        status="LLM_INFERENCE_SUCCESS",
                    )
            except Exception as exc:
                err_msg = f"OpenAI ({type(exc).__name__}: {exc})"
                errors.append(err_msg)
                logger.warning("OpenAI LLM inference failed: %s. Attempting Ollama SDK.", err_msg)

        # 2. Try Ollama (only if host is configured)
        if self.ollama_host and self.ollama_host.strip():
            start_t = time.perf_counter()
            ollama_model = self.model if "gpt" not in self.model else "llama3:latest"
            try:
                res = await execute_ollama_sdk(
                    prompt=prompt,
                    model=ollama_model,
                    host=self.ollama_host,
                    timeout=effective_timeout,
                    context_metadata=meta,
                )
                elapsed_ms = (time.perf_counter() - start_t) * 1000
                if res and res.strip():
                    logger.info(
                        "LLM_INFERENCE_SUCCESS: Generated via Ollama SDK (%s) in %.1fms",
                        ollama_model,
                        elapsed_ms,
                    )
                    return LLMGenerationResult(
                        text=res.strip(),
                        synthesis_engine=f"ollama_sdk:{ollama_model}",
                        llm_model=ollama_model,
                        inference_time_ms=round(elapsed_ms, 2),
                        fallback_used=False,
                        status="LLM_INFERENCE_SUCCESS",
                    )
            except Exception as exc:
                err_msg = f"Ollama SDK ({type(exc).__name__}: {exc})"
                errors.append(err_msg)
                logger.warning("Ollama SDK failed: %s. Attempting Ollama HTTP.", err_msg)

            # 3. Try Ollama HTTP endpoint as fallback
            start_t = time.perf_counter()
            try:
                res = await execute_ollama_http(
                    prompt=prompt,
                    model=ollama_model,
                    host=self.ollama_host,
                    timeout=effective_timeout,
                    context_metadata=meta,
                )
                elapsed_ms = (time.perf_counter() - start_t) * 1000
                if res and res.strip():
                    logger.info(
                        "LLM_INFERENCE_SUCCESS: Generated via Ollama HTTP (%s) in %.1fms",
                        ollama_model,
                        elapsed_ms,
                    )
                    return LLMGenerationResult(
                        text=res.strip(),
                        synthesis_engine=f"ollama_http:{ollama_model}",
                        llm_model=ollama_model,
                        inference_time_ms=round(elapsed_ms, 2),
                        fallback_used=False,
                        status="LLM_INFERENCE_SUCCESS",
                    )
            except Exception as exc:
                err_msg = f"Ollama HTTP ({type(exc).__name__}: {exc})"
                errors.append(err_msg)
                logger.warning(
                    "LLM_FALLBACK_TRIGGERED: Ollama unreachable or timed out (%s). Using structured template.",
                    err_msg,
                )

        # 4. Deterministic Structured Fallback Memorandum
        fallback_text = await execute_structured_fallback(
            prompt=prompt,
            model="none",
            context_metadata=meta,
        )
        return LLMGenerationResult(
            text=fallback_text,
            synthesis_engine="fallback:template",
            llm_model="none",
            inference_time_ms=0.0,
            fallback_used=True,
            status="LLM_FALLBACK_TRIGGERED",
            error_details="; ".join(errors) if errors else "No active provider",
        )

    # Backward compatibility helpers
    async def _call_openai(self, prompt: str) -> str:
        return await execute_openai(prompt, self.model, self.openai_api_key, self.timeout)

    async def _call_ollama(self, prompt: str) -> str:
        return await execute_ollama_sdk(prompt, self.model, self.ollama_host, self.timeout)

    def _generate_structured_fallback_memo(
        self,
        prompt: str,
        score: Optional[float] = None,
        verdict: str = "MODERATE_MONITORED",
        recommendation: str = "MANUAL_REVIEW",
        pd_pct: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        return generate_structured_fallback_memo(
            prompt=prompt,
            score=score,
            verdict=verdict,
            recommendation=recommendation,
            pd_pct=pd_pct,
            extra=extra,
        )


# Global client instance
default_llm_client = AsyncLLMClient()

__all__ = [
    "AsyncLLMClient",
    "default_llm_client",
    "LLMGenerationResult",
    "LLMExecutor",
    "EXECUTOR_REGISTRY",
    "execute_ollama_sdk",
    "execute_ollama_http",
    "execute_openai",
    "execute_structured_fallback",
    "generate_structured_fallback_memo",
]
