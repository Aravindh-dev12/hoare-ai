from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import requests
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
_DEFAULT_MODEL = "Qwen/Qwen3.5-4B"
_LOCAL_LOCK = threading.Lock()
_LOCAL_PROCESSOR = None
_LOCAL_MODEL = None


@dataclass(frozen=True)
class InferenceConfig:
    backend: str
    model: str
    base_url: str
    api_key: str
    model_path: str
    timeout_seconds: int
    max_output_tokens: int


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_config() -> InferenceConfig:
    explicit = os.getenv("HOARE_LLM_BACKEND", "auto").strip().lower()
    base_url = os.getenv("HOARE_LLM_BASE_URL", "").strip().rstrip("/")
    model_path = os.getenv("HOARE_QWEN_MODEL_PATH", "").strip()
    model = os.getenv("HOARE_LLM_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

    if explicit == "auto":
        if base_url:
            backend = "openai"
        elif model_path:
            backend = "transformers"
        elif _truthy(os.getenv("HOARE_LOAD_MODEL_FROM_HUB")) or os.getenv("SPACE_ID"):
            backend = "transformers"
        elif os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CLOUD_PROJECT"):
            backend = "gemini"
        else:
            backend = "static"
    else:
        backend = explicit

    if backend not in {"openai", "transformers", "gemini", "static"}:
        raise ValueError("HOARE_LLM_BACKEND must be auto, openai, transformers, gemini, or static")

    return InferenceConfig(
        backend=backend,
        model=model,
        base_url=base_url,
        api_key=os.getenv("HOARE_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "EMPTY")).strip() or "EMPTY",
        model_path=model_path,
        timeout_seconds=max(30, min(int(os.getenv("HOARE_LLM_TIMEOUT_SECONDS", "180")), 900)),
        max_output_tokens=max(512, min(int(os.getenv("HOARE_MAX_OUTPUT_TOKENS", "6144")), 32768)),
    )


def inference_status() -> dict[str, str]:
    cfg = get_config()
    model_ref = cfg.model_path if cfg.backend == "transformers" and cfg.model_path else cfg.model
    return {
        "backend": cfg.backend,
        "model": model_ref,
        "endpoint": cfg.base_url if cfg.backend == "openai" else "local/process",
    }


def _strip_wrappers(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_wrappers(text)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("Model response did not contain a valid JSON object")


def _openai_compatible(prompt: str, cfg: InferenceConfig) -> str:
    if not cfg.base_url:
        raise RuntimeError("HOARE_LLM_BASE_URL is required for the openai backend")
    url = f"{cfg.base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.api_key and cfg.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON matching the requested schema. Do not include markdown fences."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": cfg.max_output_tokens,
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=cfg.timeout_seconds)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(1.5 * (2**attempt))
                continue
            response.raise_for_status()
            body = response.json()
            return str(body["choices"][0]["message"]["content"])
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"Qwen endpoint failed: {last_error}")


def _load_local_model(cfg: InferenceConfig):
    global _LOCAL_PROCESSOR, _LOCAL_MODEL
    if _LOCAL_PROCESSOR is not None and _LOCAL_MODEL is not None:
        return _LOCAL_PROCESSOR, _LOCAL_MODEL

    with _LOCAL_LOCK:
        if _LOCAL_PROCESSOR is not None and _LOCAL_MODEL is not None:
            return _LOCAL_PROCESSOR, _LOCAL_MODEL
        try:
            from transformers import AutoModelForMultimodalLM, AutoProcessor
        except Exception as exc:
            raise RuntimeError(
                "Local Qwen requires the optional local-model dependencies. "
                "Install requirements-local.txt or use a vLLM/SGLang endpoint."
            ) from exc

        model_ref = cfg.model_path or cfg.model
        if cfg.model_path and not Path(cfg.model_path).exists():
            raise RuntimeError(f"HOARE_QWEN_MODEL_PATH does not exist: {cfg.model_path}")

        processor = AutoProcessor.from_pretrained(model_ref, trust_remote_code=False)
        model = AutoModelForMultimodalLM.from_pretrained(
            model_ref,
            device_map="auto",
            dtype="auto",
            low_cpu_mem_usage=True,
            trust_remote_code=False,
        )
        model.eval()
        _LOCAL_PROCESSOR, _LOCAL_MODEL = processor, model
        return processor, model


def _transformers_local(prompt: str, cfg: InferenceConfig) -> str:
    import torch

    processor, model = _load_local_model(cfg)
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "Return only valid JSON matching the requested schema. Do not include markdown fences."}],
        },
        {"role": "user", "content": [{"type": "text", "text": prompt}]},
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        enable_thinking=False,
    ).to(model.device)

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=cfg.max_output_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.8,
        )
    generated = output[0][inputs["input_ids"].shape[-1] :]
    return processor.decode(generated, skip_special_tokens=True)


def _gemini(prompt: str) -> str:
    from google import genai

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
    use_enterprise = _truthy(os.getenv("GOOGLE_GENAI_USE_ENTERPRISE"))
    if project and use_enterprise:
        client = genai.Client(enterprise=True, project=project, location=location)
    else:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=key) if key else genai.Client()
    try:
        interaction = client.interactions.create(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            input=prompt,
            response_format={"type": "text", "mime_type": "application/json"},
        )
        return interaction.output_text
    finally:
        client.close()


def generate_structured(prompt: str, schema: type[T]) -> T:
    cfg = get_config()
    if cfg.backend == "static":
        raise RuntimeError("No LLM backend configured")
    if cfg.backend == "openai":
        raw = _openai_compatible(prompt, cfg)
    elif cfg.backend == "transformers":
        raw = _transformers_local(prompt, cfg)
    elif cfg.backend == "gemini":
        raw = _gemini(prompt)
    else:
        raise RuntimeError(f"Unsupported backend: {cfg.backend}")

    payload = extract_json_object(raw)
    return schema.model_validate(payload)
