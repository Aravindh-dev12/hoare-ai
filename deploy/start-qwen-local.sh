#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${HOARE_QWEN_MODEL_PATH:?Set HOARE_QWEN_MODEL_PATH to your downloaded Qwen3.5-4B directory}"
PORT="${QWEN_PORT:-8000}"
MAX_MODEL_LEN="${QWEN_MAX_MODEL_LEN:-65536}"

exec vllm serve "$MODEL_PATH" \
  --served-model-name "${HOARE_LLM_MODEL:-Qwen/Qwen3.5-4B}" \
  --port "$PORT" \
  --tensor-parallel-size "${QWEN_TENSOR_PARALLEL_SIZE:-1}" \
  --max-model-len "$MAX_MODEL_LEN" \
  --reasoning-parser qwen3 \
  --language-model-only
