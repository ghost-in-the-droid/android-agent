#!/usr/bin/env bash
# Fetches the tiny Phase 0 model (SmolLM2-360M-Instruct Q4_K_M, ~270 MB) used to
# prove the on-device pipeline in the simulator. The production default
# (Gemma-4 E2B, Android parity) is downloaded on first run inside the app.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="SmolLM2-360M-Instruct-Q4_K_M.gguf"
URL="https://huggingface.co/bartowski/SmolLM2-360M-Instruct-GGUF/resolve/main/${MODEL}"

mkdir -p models GhostLLM/Resources
if [[ ! -f "models/${MODEL}" ]]; then
  echo "Downloading ${MODEL} ..."
  curl -fL --retry 3 -o "models/${MODEL}" "${URL}"
fi
# The app bundles the model as a resource for the simulator Phase 0 proof.
cp "models/${MODEL}" "GhostLLM/Resources/${MODEL}"
echo "Model ready: GhostLLM/Resources/${MODEL} ($(stat -f %z "GhostLLM/Resources/${MODEL}") bytes)"
