#!/usr/bin/env bash
set -euo pipefail

BENCHMARK="${1:-core_balanced}"

if [[ -z "${BASE_MODEL:-}" ]]; then
  if [[ -d "/LLaMA-Factory/models/Qwen2.5-7B-Instruct" ]]; then
    BASE_MODEL="/LLaMA-Factory/models/Qwen2.5-7B-Instruct"
  else
    BASE_MODEL="Qwen/Qwen2.5-7B-Instruct"
  fi
fi
EVAL_ROOT="${EVAL_ROOT:-/LLaMA-Factory/eval}"
OUT_ROOT="${OUT_ROOT:-$EVAL_ROOT/outputs/$BENCHMARK}"
RUN_FILTER="${RUN_FILTER:-}"
if [[ -z "${HF_TOKEN:-}" && -n "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  HF_TOKEN="$HUGGING_FACE_HUB_TOKEN"
fi

TOKEN_ARGS=()
if [[ -n "${HF_TOKEN:-}" ]]; then
  TOKEN_ARGS=(--hf-token "$HF_TOKEN")
fi

if [[ -z "${ADAPTER_ROOT:-}" ]]; then
  if [[ -d "/LLaMA-Factory/finetuing_models" ]]; then
    ADAPTER_ROOT="/LLaMA-Factory/finetuing_models"
  else
    ADAPTER_ROOT="/LLaMA-Factory/saves/ztn_pdp"
  fi
fi

case "$BENCHMARK" in
  screenshot_cases)
    EVAL_FILE="$EVAL_ROOT/ztn_eval_screenshot_cases.jsonl"
    ;;
  core_balanced)
    EVAL_FILE="$EVAL_ROOT/ztn_eval_core_balanced.jsonl"
    ;;
  rare_stress)
    EVAL_FILE="$EVAL_ROOT/ztn_eval_rare_stress.jsonl"
    ;;
  *)
    echo "Unknown benchmark: $BENCHMARK"
    echo "Use: screenshot_cases, core_balanced, or rare_stress"
    exit 1
    ;;
esac

mkdir -p "$OUT_ROOT"

RUN_NAMES=(
  "base"
  "A_r8_a16_lr2e4"
  "B_r32_a64_lr2e4"
  "C_r8_a16_lr5e5"
)

ADAPTERS=(
  ""
  "${A_ADAPTER:-$ADAPTER_ROOT/qwen2.5_7b_ztn_r8_a16_lr2e4}"
  "${B_ADAPTER:-$ADAPTER_ROOT/qwen2.5_7b_ztn_r32_a64_lr2e4}"
  "${C_ADAPTER:-$ADAPTER_ROOT/qwen2.5_7b_ztn_r8_a16_lr5e5}"
)

should_run() {
  local name="$1"
  local selected

  if [[ -z "$RUN_FILTER" ]]; then
    return 0
  fi

  IFS=',' read -ra selected <<< "$RUN_FILTER"
  for item in "${selected[@]}"; do
    if [[ "$item" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

for idx in "${!RUN_NAMES[@]}"; do
  NAME="${RUN_NAMES[$idx]}"
  ADAPTER="${ADAPTERS[$idx]}"
  OUTPUT="$OUT_ROOT/${NAME}.jsonl"

  if ! should_run "$NAME"; then
    continue
  fi

  echo "Evaluating $NAME on $BENCHMARK"

  if [[ -z "$ADAPTER" ]]; then
    python3 "$EVAL_ROOT/run_ztn_eval.py" \
      --model "$BASE_MODEL" \
      --eval-file "$EVAL_FILE" \
      --output "$OUTPUT" \
      --run-name "$NAME" \
      "${TOKEN_ARGS[@]}"
  else
    if [[ ! -d "$ADAPTER" ]]; then
      echo "Missing adapter directory for $NAME: $ADAPTER"
      echo "Set ADAPTER_ROOT, A_ADAPTER, B_ADAPTER, or C_ADAPTER if your paths differ."
      exit 1
    fi

    python3 "$EVAL_ROOT/run_ztn_eval.py" \
      --model "$BASE_MODEL" \
      --adapter "$ADAPTER" \
      --eval-file "$EVAL_FILE" \
      --output "$OUTPUT" \
      --run-name "$NAME" \
      "${TOKEN_ARGS[@]}"
  fi
done

python3 "$EVAL_ROOT/aggregate_ztn_metrics.py" \
  --input-dir "$OUT_ROOT" \
  --output "$OUT_ROOT/metrics_summary.csv"

python3 "$EVAL_ROOT/plot_ztn_metrics.py" \
  --metrics "$OUT_ROOT/metrics_summary.csv" \
  --output-dir "$OUT_ROOT/figures" \
  --benchmark "$BENCHMARK" \
  --confusion-dir "$OUT_ROOT"

echo "Done. Outputs are in $OUT_ROOT"
