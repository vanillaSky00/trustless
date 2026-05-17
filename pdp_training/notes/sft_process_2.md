# Next Step: Training and Evaluation Plan on glows RTX 4090

This plan assumes the remote machine is:

```text
GPU: NVIDIA GeForce RTX 4090, 24 GB VRAM
Image: Ubuntu 20.04, CUDA 12.4, PyTorch 2.6.0, Python 3.11
Tooling: LLaMA-Factory, JupyterLab/VNC
Training task: SFT with LoRA
Dataset: ztn_sft.json, Alpaca format, 3,000 examples
```

The short recommendation:

> Use the current dataset as the imbalanced cybersecurity benchmark, but create an enum-explicit copy before serious parameter experiments. Train LoRA adapters first, evaluate all adapters on the same benchmark, and only export/merge the full model after choosing the best adapter.


## 1. Important Dataset Check

The current local file:

```text
/Users/harris/workshop/fintune/trustless/pdp_training/ztn_sft.json
```

has 3,000 examples:

| Class | Count |
|---|---:|
| NORMAL | 2,100 |
| AFTER_HOURS | 600 |
| MULTI_PC | 200 |
| WEEKEND_BURST | 75 |
| EXTREME_LATE_NIGHT | 25 |

This is good for the assignment because it creates a realistic rare-event cybersecurity problem.

However, the current file uses the older vague instruction:

```text
The JSON must contain exactly these fields: risk_level, anomaly_type,
device_trust, recommended_action, confidence, rationale.
```

Your previous evaluation showed that this causes enum hallucination. Before the new training runs, create a v2 dataset with explicit enum constraints in every instruction.

Primary training dataset should be:

```text
ztn_sft_enum.json
```

not the original `ztn_sft.json`.


## 2. Experiment Strategy

Do not start with augmentation. First run a clean parameter-impact study.

Use one fixed dataset:

```text
ztn_sft_enum
```

Use one fixed base model:

```text
Qwen2.5-7B-Instruct
```

Then compare parameter configurations:

| Run | LoRA Rank | LoRA Alpha | Learning Rate | Why |
|---|---:|---:|---:|---|
| A baseline | 8 | 16 | 2e-4 | Your reference setup |
| B higher capacity | 32 | 64 | 2e-4 | Tests whether more LoRA capacity helps rare classes |
| C lower learning rate | 8 | 16 | 5e-5 | Tests whether smoother learning improves schema stability |

Optional only if time allows:

| Run | LoRA Rank | LoRA Alpha | Learning Rate | Why |
|---|---:|---:|---:|---|
| D stress test | 8 | 16 | 5e-4 | Tests whether too-high LR makes loss/output unstable |

This satisfies the assignment requirement to adjust at least two parameters:

- LoRA rank / alpha
- Learning rate


## 3. Recommended Training Settings for RTX 4090 24 GB

Qwen2.5-7B-Instruct with LoRA should fit on a 24 GB 4090 using short sequence length.

Use these defaults:

| Setting | Value |
|---|---|
| Fine-tuning type | `lora` |
| Stage | `sft` |
| Template | `qwen` |
| Cutoff length | `512` |
| Epochs | `3` |
| Per-device train batch size | `4` |
| Gradient accumulation | `4` |
| Effective batch size | `16` |
| Validation size | `0.05` |
| Scheduler | `cosine` |
| Warmup ratio | `0.05` |
| Max grad norm | `1.0` |
| Precision | `bf16` |
| LoRA target | `all` |
| LoRA dropout | `0.1` |
| Save strategy | `epoch` |
| Save total limit | `2` |
| Plot loss | `true` |

If you hit CUDA out-of-memory:

1. Reduce `per_device_train_batch_size` from `4` to `2`.
2. Keep `gradient_accumulation_steps` higher so effective batch stays similar.
3. If still OOM, use QLoRA with `quantization_bit: 4`.

Do not use QLoRA unless needed. Plain LoRA with bf16 is cleaner for the assignment.


## 4. Remote Setup Checklist

On the glows server:

```bash
cd /LLaMA-Factory
nvidia-smi
python --version
llamafactory-cli version || llamafactory-cli --help
```

Expected:

```text
RTX 4090 visible
Python 3.11
LLaMA-Factory CLI available
```

Start the WebUI if you want the screenshots:

```bash
cd /LLaMA-Factory
llamafactory-cli webui
```

Use the WebUI for assignment screenshots, but prefer CLI/YAML for the actual repeated experiments because it is easier to reproduce.


## 5. Upload Dataset to Remote

From your local machine:

```bash
scp -P <PORT> \
  /Users/harris/workshop/fintune/trustless/pdp_training/ztn_sft.json \
  root@<GLOWS_HOST>:/tmp/ztn_sft.json
```

On the remote server:

```bash
cd /LLaMA-Factory
cp /tmp/ztn_sft.json data/ztn_sft.json
```

Create the enum-explicit v2 copy:

```bash
cd /LLaMA-Factory
python3 - <<'PY'
import json

src = "data/ztn_sft.json"
dst = "data/ztn_sft_enum.json"

enum_instruction = (
    "You are a Zero Trust Network analyst. Classify this user-day access event "
    "and output a ZTA incident schema as a single valid JSON object. "
    "Use ONLY these exact values:\n"
    "  risk_level: LOW | MEDIUM | HIGH | CRITICAL\n"
    "  anomaly_type: NORMAL | AFTER_HOURS | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT\n"
    "  device_trust: TRUSTED | UNMANAGED\n"
    "  recommended_action: ALLOW | MONITOR | STEP_UP_AUTH | BLOCK_AND_ALERT\n"
    "  confidence: a float between 0.0 and 1.0\n"
    "  rationale: one sentence explanation\n"
    "Output JSON only. No explanation text before or after."
)

with open(src, "r") as f:
    records = json.load(f)

for record in records:
    record["instruction"] = enum_instruction

with open(dst, "w") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)

print(f"Wrote {len(records)} records to {dst}")
PY
```

Register both datasets in LLaMA-Factory:

```bash
cd /LLaMA-Factory
python3 - <<'PY'
import json
from pathlib import Path

path = Path("data/dataset_info.json")
info = json.loads(path.read_text())

info["ztn_sft"] = {
    "file_name": "ztn_sft.json",
    "formatting": "alpaca",
    "columns": {
        "prompt": "instruction",
        "query": "input",
        "response": "output"
    }
}

info["ztn_sft_enum"] = {
    "file_name": "ztn_sft_enum.json",
    "formatting": "alpaca",
    "columns": {
        "prompt": "instruction",
        "query": "input",
        "response": "output"
    }
}

path.write_text(json.dumps(info, indent=2, ensure_ascii=False))
print("Registered ztn_sft and ztn_sft_enum")
PY
```

Check:

```bash
python3 - <<'PY'
import json
info = json.load(open("/LLaMA-Factory/data/dataset_info.json"))
print(info["ztn_sft_enum"])
PY
```


## 6. Model Setup

Recommended base model:

```text
Qwen/Qwen2.5-7B-Instruct
```

If the model is not already downloaded:

```bash
cd /LLaMA-Factory
mkdir -p models
huggingface-cli download Qwen/Qwen2.5-7B-Instruct \
  --local-dir models/Qwen2.5-7B-Instruct \
  --local-dir-use-symlinks False
```

Use local path in all configs:

```text
/LLaMA-Factory/models/Qwen2.5-7B-Instruct
```

This avoids accidental re-downloads.


## 7. Create Training Configs

Create a config folder:

```bash
cd /LLaMA-Factory
mkdir -p configs/ztn_pdp
```

### Run A: Baseline LoRA

Save as:

```text
/LLaMA-Factory/configs/ztn_pdp/qwen2.5_7b_ztn_r8_a16_lr2e4.yaml
```

```yaml
model_name_or_path: /LLaMA-Factory/models/Qwen2.5-7B-Instruct
trust_remote_code: true

stage: sft
do_train: true
finetuning_type: lora
lora_rank: 8
lora_alpha: 16
lora_dropout: 0.1
lora_target: all

dataset_dir: /LLaMA-Factory/data
dataset: ztn_sft_enum
template: qwen
cutoff_len: 512
max_samples: 3000
preprocessing_num_workers: 8
dataloader_num_workers: 4

output_dir: /LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr2e4
logging_steps: 10
save_strategy: epoch
save_total_limit: 2
plot_loss: true
overwrite_output_dir: true
save_only_model: false
report_to: none

per_device_train_batch_size: 4
gradient_accumulation_steps: 4
learning_rate: 2.0e-4
num_train_epochs: 3.0
lr_scheduler_type: cosine
warmup_ratio: 0.05
max_grad_norm: 1.0
bf16: true

val_size: 0.05
per_device_eval_batch_size: 4
eval_strategy: steps
eval_steps: 50
```

### Run B: Higher LoRA Capacity

Copy Run A and change:

```yaml
lora_rank: 32
lora_alpha: 64
output_dir: /LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r32_a64_lr2e4
```

Save as:

```text
/LLaMA-Factory/configs/ztn_pdp/qwen2.5_7b_ztn_r32_a64_lr2e4.yaml
```

### Run C: Lower Learning Rate

Copy Run A and change:

```yaml
learning_rate: 5.0e-5
output_dir: /LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr5e5
```

Save as:

```text
/LLaMA-Factory/configs/ztn_pdp/qwen2.5_7b_ztn_r8_a16_lr5e5.yaml
```


## 8. Run Training

Run one experiment at a time:

```bash
cd /LLaMA-Factory
llamafactory-cli train configs/ztn_pdp/qwen2.5_7b_ztn_r8_a16_lr2e4.yaml
```

Then:

```bash
llamafactory-cli train configs/ztn_pdp/qwen2.5_7b_ztn_r32_a64_lr2e4.yaml
llamafactory-cli train configs/ztn_pdp/qwen2.5_7b_ztn_r8_a16_lr5e5.yaml
```

Watch:

```bash
nvidia-smi
```

Expected result after each run:

```text
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr2e4
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r32_a64_lr2e4
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr5e5
```

Each directory should contain the LoRA adapter, training state, logs, and loss plot.


## 9. What Screenshots to Capture

For the assignment, use the LLaMA-Factory WebUI to capture:

| Screenshot | Why |
|---|---|
| Run A parameter interface | baseline config |
| Run B parameter interface | changed rank / alpha |
| Run C parameter interface | changed learning rate |
| Run A loss curve | baseline training behavior |
| Run B loss curve | higher-rank comparison |
| Run C loss curve | lower-LR comparison |
| Chat output before fine-tuning | base model failure |
| Chat output after fine-tuning | trained adapter improvement |
| Output comparison table | final evidence |

CLI runs are better for repeatability, but screenshots from WebUI are still useful for the report.


## 10. Evaluation Plan After Training

Do not rely only on manual chat screenshots. Use a repeatable benchmark.

Create:

```text
/LLaMA-Factory/eval/ztn_eval_screenshot_cases.jsonl
/LLaMA-Factory/eval/ztn_eval_core_balanced.jsonl
/LLaMA-Factory/eval/ztn_eval_rare_stress.jsonl
```

Minimum benchmark:

| Benchmark | Size | Purpose |
|---|---:|---|
| Screenshot cases | 5 | Assignment screenshots |
| Core balanced | 100 | Fair comparison across all classes |
| Rare stress | 50 | Tests rare cybersecurity failures |

Generation settings:

```text
temperature = 0
top_p = 1.0
max_new_tokens = 256
```

Main metrics:

| Metric | Why |
|---|---|
| Full schema compliance | Can the PDP parse it? |
| Hallucinated enum rate | Does it invent invalid policy values? |
| Anomaly type accuracy | Does it label incidents correctly? |
| Macro F1 | Does it handle rare classes? |
| EXTREME_LATE_NIGHT recall | Does it catch the rarest critical case? |
| Recommended action accuracy | Does it choose the right enforcement action? |
| Under-action rate | Does it make unsafe permissive decisions? |
| Severe false negative rate | Does it miss HIGH/CRITICAL cases? |
| Final eval loss | How did parameters affect training dynamics? |

Use the more detailed metric definitions in:

```text
/Users/harris/workshop/fintune/trustless/pdp_training/evaluation_planning.md
```


## 11. Recommended evaluation.sh Design

Yes, create an `evaluation.sh`. It should run the same benchmark against all adapters.

Recommended remote structure:

```text
/LLaMA-Factory/eval/
  evaluation.sh
  run_ztn_eval.py
  aggregate_metrics.py
  ztn_eval_screenshot_cases.jsonl
  ztn_eval_core_balanced.jsonl
  ztn_eval_rare_stress.jsonl
  outputs/
```

The shell script should look like this:

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_MODEL="/LLaMA-Factory/models/Qwen2.5-7B-Instruct"
EVAL_FILE="/LLaMA-Factory/eval/ztn_eval_core_balanced.jsonl"
OUT_DIR="/LLaMA-Factory/eval/outputs"

mkdir -p "$OUT_DIR"

declare -A ADAPTERS=(
  ["base"]=""
  ["r8_a16_lr2e4"]="/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr2e4"
  ["r32_a64_lr2e4"]="/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r32_a64_lr2e4"
  ["r8_a16_lr5e5"]="/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr5e5"
)

for NAME in "${!ADAPTERS[@]}"; do
  ADAPTER="${ADAPTERS[$NAME]}"
  echo "Evaluating $NAME"

  if [[ -z "$ADAPTER" ]]; then
    python /LLaMA-Factory/eval/run_ztn_eval.py \
      --model "$BASE_MODEL" \
      --eval-file "$EVAL_FILE" \
      --output "$OUT_DIR/${NAME}.jsonl"
  else
    python /LLaMA-Factory/eval/run_ztn_eval.py \
      --model "$BASE_MODEL" \
      --adapter "$ADAPTER" \
      --eval-file "$EVAL_FILE" \
      --output "$OUT_DIR/${NAME}.jsonl"
  fi
done

python /LLaMA-Factory/eval/aggregate_metrics.py \
  --input-dir "$OUT_DIR" \
  --output "$OUT_DIR/metrics_summary.csv"
```

`run_ztn_eval.py` should use Transformers + PEFT directly. This is easier than clicking WebUI for every example and gives you reproducible numbers.

The evaluator should save raw outputs, parsed JSON, ground truth, and per-example metric flags.


## 12. Getting the Trained Model Back From Remote

There are three possible artifacts:

### Option A: Download LoRA adapters only

This is the recommended option.

Why:

- Smallest files
- Best for assignment evidence
- Keeps each experiment separate
- Avoids downloading the full base model repeatedly

Expected size:

```text
Rank 8 adapter: tens to low hundreds of MB
Rank 32 adapter: roughly 4x rank 8
```

Package adapters:

```bash
cd /LLaMA-Factory
tar -czf /tmp/ztn_pdp_lora_adapters.tar.gz finetuing_models eval/outputs
```

Download:

```bash
scp -P <PORT> \
  root@<GLOWS_HOST>:/tmp/ztn_pdp_lora_adapters.tar.gz \
  /Users/harris/workshop/fintune/trustless/pdp_training/
```

### Option B: Export one merged model

Only do this after choosing the best adapter.

Why:

- Easier deployment
- Does not require loading base + adapter separately
- But much larger

Expected size for Qwen2.5-7B bf16:

```text
around 15-16 GB
```

Create:

```text
/LLaMA-Factory/configs/ztn_pdp/export_best.yaml
```

Example:

```yaml
model_name_or_path: /LLaMA-Factory/models/Qwen2.5-7B-Instruct
adapter_name_or_path: /LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr2e4
template: qwen
trust_remote_code: true

export_dir: /LLaMA-Factory/exported/ztn_pdp_qwen2.5_7b_best_merged
export_size: 5
export_device: cpu
export_legacy_format: false
```

Run:

```bash
cd /LLaMA-Factory
llamafactory-cli export configs/ztn_pdp/export_best.yaml
```

If CPU RAM is too low during export, try:

```yaml
export_device: cuda
```

Package the merged model:

```bash
cd /LLaMA-Factory
tar -czf /tmp/ztn_pdp_qwen2.5_7b_best_merged.tar.gz exported/ztn_pdp_qwen2.5_7b_best_merged
```

Download:

```bash
scp -P <PORT> \
  root@<GLOWS_HOST>:/tmp/ztn_pdp_qwen2.5_7b_best_merged.tar.gz \
  /Users/harris/workshop/fintune/trustless/pdp_training/
```

### Option C: Export a quantized model

Only do this if you want local deployment later.

Expected size:

```text
4-bit quantized 7B model: roughly 4-6 GB
```

For this assignment, quantization is optional. It adds another variable, so do not use quantized export for the main comparison unless your goal is deployment.


## 13. Should You Augment the Dataset?

Recommendation:

```text
Not before the first parameter study.
```

Reason:

The assignment asks for parameter impact. If you change the dataset and parameters at the same time, the comparison becomes muddy.

Use this order:

1. Train Run A/B/C on the same `ztn_sft_enum` dataset.
2. Evaluate all three.
3. If rare-class recall is still poor, create an augmented rare-class dataset as a separate extension.

Optional augmented dataset:

```text
ztn_sft_enum_aug_rare.json
```

Suggested target counts:

| Class | Current | Augmented target |
|---|---:|---:|
| NORMAL | 2,100 | 2,100 |
| AFTER_HOURS | 600 | 600 |
| MULTI_PC | 200 | 600 |
| WEEKEND_BURST | 75 | 600 |
| EXTREME_LATE_NIGHT | 25 | 600 |

This would test:

> Does class-balanced rare-event augmentation improve cybersecurity recall more than LoRA parameter tuning?

That is a cool extension, but it should be separate from the required parameter-impact experiment.


## 14. Final Report Story

Your final report can use this structure:

1. Scenario: Zero Trust PDP incident schema generation.
2. Dataset: CERT-derived user-day behavior, intentionally imbalanced.
3. Training: Qwen2.5-7B-Instruct + LoRA SFT in LLaMA-Factory.
4. Parameter configs: rank/alpha and learning rate changes.
5. Loss curve comparison: Run A/B/C.
6. Benchmark comparison: schema, hallucination, rare recall, action safety.
7. Output screenshots: before fine-tune, after fine-tune, config differences.
8. Conclusion: LoRA improves structured output, but rare-event recall is the core security challenge.

Strong final claim:

```text
The fine-tuned model became much better at producing parseable PDP decisions, but the
highest-risk cybersecurity categories remained the hardest because they were the rarest.
Higher LoRA capacity and learning-rate changes affected training behavior, but data
representation still dominated rare-event recall.
```


## 15. Priority Checklist

Do this in order:

1. Upload `ztn_sft.json` to glows.
2. Create `ztn_sft_enum.json` on remote.
3. Register `ztn_sft_enum` in `data/dataset_info.json`.
4. Download or verify Qwen2.5-7B-Instruct.
5. Create YAML configs for Run A/B/C.
6. Train Run A.
7. Train Run B.
8. Train Run C.
9. Screenshot LLaMA-Factory configs and loss curves.
10. Run `evaluation.sh` on all adapters.
11. Compare schema compliance, hallucination rate, macro F1, rare recall, action safety.
12. Download LoRA adapters and evaluation outputs.
13. Export one merged model only if needed.
14. Add optional augmented-data experiment if time remains.


## 16. References Checked

- LLaMA-Factory SFT uses `llamafactory-cli train <config.yaml>` and supports overriding YAML parameters from CLI.
- LLaMA-Factory WebUI supports training, evaluation/chat, and export screens, useful for screenshots.
- LLaMA-Factory LoRA export uses `llamafactory-cli export <merge_config.yaml>`.
- Custom datasets are registered through `data/dataset_info.json`.

Useful docs:

- [LLaMA-Factory Supervised Fine-tuning](https://llamafactory.readthedocs.io/en/latest/getting_started/sft.html)
- [LLaMA-Factory WebUI](https://llamafactory.readthedocs.io/en/latest/getting_started/webui.html)
- [LLaMA-Factory Model Saving, LoRA Merging, and Quantization](https://llamafactory.readthedocs.io/en/latest/getting_started/merge_lora.html)
- [LLaMA-Factory Data Preparation](https://llamafactory.readthedocs.io/en/latest/getting_started/data_preparation.html)
