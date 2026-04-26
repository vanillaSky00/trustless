# Task 3 — Llama-Factory Fine-Tuning: Complete Process Log

This document records the end-to-end process of supervised fine-tuning a language model on Zero Trust Network (ZTN) anomaly classification — from dataset preparation in Colab to model evaluation on glows.ai.

**Final setup:**
- Model: Qwen2.5-7B-Instruct
- Method: LoRA SFT
- Dataset: 3,000 synthetic examples derived from Task 2 clustering output
- Training environment: glows.ai (Llama-Factory container)
- Data prep / evaluation environment: Google Colab T4


## Stage 1 — Synthetic Dataset Construction (Colab)

### 1.1 Source Data

The starting point is the output of Task 2 clustering: `user_day_features_clustered.csv`. This contains 100,000 user-day behavioral profiles, each with a DBSCAN cluster label and an `is_anomaly` flag. The 2,658 rows flagged as anomalies become the seed material for the data-scarce categories.

### 1.2 Sub-Categorization (Cell A)

Anomalies were partitioned into 5 categories using a priority-ordered rule chain:

```python
def categorize(row):
    if row["is_anomaly"] == 0:
        return "NORMAL"
    if row["last_hour"] >= 22 and row["first_hour"] <= 5:
        return "EXTREME_LATE_NIGHT"
    if row["n_weekend"] >= 3:
        return "WEEKEND_BURST"
    if row["n_distinct_pcs"] >= 4:
        return "MULTI_PC"
    if row["n_after_hours"] >= 5:
        return "AFTER_HOURS"
    return "AFTER_HOURS"
```

The priority order matters: a user-day with both extreme late-night activity *and* multi-PC usage gets categorized as `EXTREME_LATE_NIGHT` (more specific) rather than `MULTI_PC`.

### 1.3 Imbalanced Sampling

Target counts deliberately set to create an 84:1 imbalance ratio between data-rich and data-scarce categories:

| Category | Target | % | Rationale |
|---|---:|---:|---|
| NORMAL | 2,100 | 70.0% | Data-rich — model should learn this perfectly |
| AFTER_HOURS | 600 | 20.0% | Medium volume — should mostly work |
| MULTI_PC | 200 | 6.7% | Data-scarce — expect drift |
| WEEKEND_BURST | 75 | 2.5% | Very scarce — expect significant drift |
| EXTREME_LATE_NIGHT | 25 | 0.8% | Hallucination spotlight |

### 1.4 Schema Definition (Cell B)

Each category was mapped to a deterministic ZTN incident schema:

```python
CATEGORY_SCHEMA = {
    "NORMAL": {
        "risk_level": "LOW",
        "device_trust": "TRUSTED",
        "recommended_action": "ALLOW",
        "confidence_range": (0.85, 0.99),
    },
    "AFTER_HOURS": {
        "risk_level": "MEDIUM",
        "device_trust": "TRUSTED",
        "recommended_action": "MONITOR",
        "confidence_range": (0.70, 0.90),
    },
    "MULTI_PC": {
        "risk_level": "HIGH",
        "device_trust": "UNMANAGED",
        "recommended_action": "STEP_UP_AUTH",
        "confidence_range": (0.75, 0.92),
    },
    "WEEKEND_BURST": {
        "risk_level": "HIGH",
        "device_trust": "UNMANAGED",
        "recommended_action": "STEP_UP_AUTH",
        "confidence_range": (0.80, 0.93),
    },
    "EXTREME_LATE_NIGHT": {
        "risk_level": "CRITICAL",
        "device_trust": "UNMANAGED",
        "recommended_action": "BLOCK_AND_ALERT",
        "confidence_range": (0.88, 0.97),
    },
}
```

### 1.5 Instruction Design (Critical — Two Versions)

**Version 1 (initial):**
```python
INSTRUCTION = (
    "You are a Zero Trust Network analyst. Classify this user-day access event "
    "and output a ZTN incident schema as a single valid JSON object. "
    "The JSON must contain exactly these fields: risk_level, anomaly_type, "
    "device_trust, recommended_action, confidence, rationale."
)
```

This was used for the first training run. Result: model produced JSON with the right field names but free-text values instead of the defined enums.

**Version 2 (after observing failures):**
```python
INSTRUCTION = (
    "You are a Zero Trust Network analyst. Classify this user-day access event "
    "and output a ZTN incident schema as a single valid JSON object. "
    "Use ONLY these exact values:\n"
    "  risk_level: LOW | MEDIUM | HIGH | CRITICAL\n"
    "  anomaly_type: NORMAL | AFTER_HOURS | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT\n"
    "  device_trust: TRUSTED | UNMANAGED\n"
    "  recommended_action: ALLOW | MONITOR | STEP_UP_AUTH | BLOCK_AND_ALERT\n"
    "  confidence: a float between 0.0 and 1.0\n"
    "  rationale: one sentence explanation\n"
    "Output JSON only. No explanation text before or after."
)
```

The explicit enum enumeration in every training instruction was what changed Round 1's near-total failure into Round 2's near-perfect schema compliance.

### 1.6 Alpaca Format Conversion

Llama-Factory expects the Alpaca format (`instruction` / `input` / `output`):

```python
records = []
for _, row in train_df.iterrows():
    records.append({
        "instruction": INSTRUCTION,
        "input": build_input(row),     # behavioral fingerprint string
        "output": build_output(row),   # JSON-serialized schema
    })
```

Sample record:

```json
{
  "instruction": "You are a Zero Trust Network analyst. Classify this user-day access event ...",
  "input": "User: alice | Day: 2011-04-15 | Logons: 2 | Distinct PCs: 1 | After-hours events: 0 | Weekend events: 0 | First hour: 8 | Last hour: 17 | Hour span: 9",
  "output": "{\"risk_level\": \"LOW\", \"anomaly_type\": \"NORMAL\", \"device_trust\": \"TRUSTED\", \"recommended_action\": \"ALLOW\", \"confidence\": 0.92, \"rationale\": \"Behavioral fingerprint matches a dense cluster of routine workforce activity.\"}"
}
```

### 1.7 Dataset Registration File

A second file, `dataset_info.json`, tells Llama-Factory how to read the dataset:

```python
dataset_info = {
    "ztn_sft": {
        "file_name": "ztn_sft.json",
        "formatting": "alpaca",
        "columns": {
            "prompt": "instruction",
            "query": "input",
            "response": "output"
        }
    }
}
```

### 1.8 Bundling for Upload

Both files were zipped for transport:

```python
import shutil
shutil.make_archive("/content/task3_sft_bundle", "zip", "/content/task3_sft")
```

Result: `task3_sft_bundle.zip` containing `ztn_sft.json` (the data) and `dataset_info.json` (the registration block).


## Stage 2 — glows.ai Container Setup

### 2.1 Instance Provisioning

A glows.ai instance was provisioned with the Llama-Factory image preinstalled. The instance exposed three access methods:

| Port | Service |
|---|---|
| SSH (22, mapped to 25519) | Terminal access |
| HTTP 8888 | JupyterLab |
| HTTP 7860 | Llama-Factory Gradio Web UI |

### 2.2 Uploading the Dataset Bundle (SCP)

From a local terminal:

```bash
scp -P 25519 ~/Downloads/task3_sft_bundle.zip root@tw-05.access.glows.ai:/tmp/
```

### 2.3 SSH Access

```bash
ssh -p 25519 root@tw-05.access.glows.ai
```

### 2.4 Locating the Llama-Factory Data Directory

The container's Llama-Factory installation lives at `/LLaMA-Factory`. The data directory:

```bash
cd /LLaMA-Factory/data
ls
# alpaca_en_demo.json, dataset_info.json, ... (existing demo datasets)
```

### 2.5 Unzipping and Placing the Dataset

```bash
unzip /tmp/task3_sft_bundle.zip -d /tmp/sft_bundle/
ls /tmp/sft_bundle/
# dataset_info.json  ztn_sft.json

cp /tmp/sft_bundle/ztn_sft.json /LLaMA-Factory/data/
```

### 2.6 Merging dataset_info.json (Critical Step)

The container ships with a large `dataset_info.json` registering ~80 default datasets. Our `ztn_sft` entry needed to be merged in, not overwritten:

```bash
cd /LLaMA-Factory/data
python3 -c "
import json

with open('dataset_info.json', 'r') as f:
    info = json.load(f)

info['ztn_sft'] = {
    'file_name': 'ztn_sft.json',
    'formatting': 'alpaca',
    'columns': {
        'prompt': 'instruction',
        'query': 'input',
        'response': 'output'
    }
}

with open('dataset_info.json', 'w') as f:
    json.dump(info, f, indent=2)

print('Done. ztn_sft registered.')
"
```

Verification:

```bash
python3 -c "
import json
with open('dataset_info.json') as f:
    info = json.load(f)
print('ztn_sft' in info)
print(json.dumps(info['ztn_sft'], indent=2))
"
# True
# { "file_name": "ztn_sft.json", "formatting": "alpaca", ... }
```


## Stage 3 — Model Acquisition

### 3.1 Initial Failure: LLaMA-3-8B Access Gated

The container had a model directory placeholder:

```bash
ls /LLaMA-Factory/models
# Meta-Llama-3-8B-Instruct

ls -lh /LLaMA-Factory/models/Meta-Llama-3-8B-Instruct/
# total 48K
# -rw-r--r-- 1 root root 7.7K LICENSE
# -rw-r--r-- 1 root root  38K README.md
```

Only LICENSE and README — actual weights were missing. Loading the model in the Web UI failed with:
```
[INFO] tokenization_auto.py:795 >> Could not locate the tokenizer configuration file
```

### 3.2 HuggingFace Authentication

```bash
pip install -q huggingface_hub
huggingface-cli login
# pasted hf_... read token
```

### 3.3 LLaMA-3 Download Failure

```bash
huggingface-cli download \
    meta-llama/Meta-Llama-3-8B-Instruct \
    --local-dir /LLaMA-Factory/models/Meta-Llama-3-8B-Instruct \
    --local-dir-use-symlinks False

# huggingface_hub.errors.GatedRepoError: 403 Client Error
# Cannot access gated repo for url ...meta-llama/Meta-Llama-3-8B-Instruct...
# Access to model meta-llama/Meta-Llama-3-8B-Instruct is restricted
```

The HuggingFace account was not on the Meta-approved access list. Approval typically takes hours to days.

### 3.4 Pivot to Qwen2.5-7B (No Gate)

Qwen models from Alibaba are openly licensed and require no approval:

```bash
huggingface-cli download \
    Qwen/Qwen2.5-7B-Instruct \
    --local-dir /LLaMA-Factory/models/Qwen2.5-7B-Instruct \
    --local-dir-use-symlinks False
```

Download time: ~12 minutes for ~15GB across 17 files.

### 3.5 Verification

```bash
ls /LLaMA-Factory/models/Qwen2.5-7B-Instruct/
# config.json
# generation_config.json
# model-00001-of-00004.safetensors
# model-00002-of-00004.safetensors
# model-00003-of-00004.safetensors
# model-00004-of-00004.safetensors
# tokenizer.json
# tokenizer_config.json
# special_tokens_map.json
# ...
```

The presence of `tokenizer_config.json` confirmed the model was complete.


## Stage 4 — Llama-Factory Web UI Configuration

Accessed via `HTTP Port 7860` on the glows.ai panel.

### 4.1 Top Panel — Model Configuration

| Field | Value | Notes |
|---|---|---|
| Language | en | UI language |
| Model name | `Qwen2.5-7B-Instruct` | Selected from dropdown |
| Model path | `/LLaMA-Factory/models/Qwen2.5-7B-Instruct` | Local path overrides HF download attempt |
| Finetuning method | `lora` | Memory-efficient adapter training |
| Checkpoint path | (empty) | New training run, no resume |
| Quantization bit | `none` | Full precision LoRA fits comfortably |
| Quantization method | `bnb` | Default, unused since quantization=none |
| Chat template | `qwen` | Auto-set when model selected |
| RoPE scaling | `none` | Default cutoff length is sufficient |
| Booster | `auto` | Llama-Factory chooses best optimization |

### 4.2 Train Tab — Stage and Dataset

| Field | Value |
|---|---|
| Stage | Supervised Fine-Tuning |
| Data dir | `data` |
| Dataset | `ztn_sft` (selected from dropdown after registration) |

After selecting, "Preview dataset" was clicked to confirm records render correctly.

### 4.3 Train Tab — Hyperparameters

| Field | Value | Notes |
|---|---|---|
| Learning rate | `2e-4` | Standard LoRA learning rate |
| Epochs | `3` | Sufficient for 3,000 examples |
| Maximum gradient norm | `1.0` | Default gradient clipping |
| Max samples | `3000` | Match dataset size |
| Compute type | `bf16` | Faster than fp16 on modern GPUs |

### 4.4 Train Tab — Sequence and Batch

| Field | Value | Notes |
|---|---|---|
| Cutoff length | `512` | Reduced from default 2048 — inputs are short |
| Batch size | `4` | Per-GPU batch |
| Gradient accumulation | `4` | Effective batch = 16 |
| Val size | `0.05` | 5% reserved for validation loss curve |
| LR scheduler | `cosine` | Smooth decay |

### 4.5 LoRA-Specific Configuration

| Field | Value |
|---|---|
| LoRA rank | `8` |
| LoRA alpha | `16` |
| LoRA dropout | `0.1` |
| LoRA target | `all` |

### 4.6 Output Configuration

| Field | Value |
|---|---|
| Output dir | `ztn_lora_v1` (and later `ztn_lora_v2` for round 2) |
| Save steps | `100` |
| Logging steps | `10` |
| Plot loss | ✅ enabled |

### 4.7 Training Execution

Clicked "Start". The UI displayed:
- Live progress bar
- Loss values printing every 10 steps
- A descending loss curve rendering in real time

Training duration: approximately 12-15 minutes for 3,000 examples × 3 epochs.


## Stage 5 — Model Evaluation (Chat Tab)

### 5.1 Loading the Trained Adapter

In the Web UI's "Chat" tab:

| Field | Value |
|---|---|
| Model name | `Qwen2.5-7B-Instruct` |
| Model path | `/LLaMA-Factory/models/Qwen2.5-7B-Instruct` |
| Adapter path | `/LLaMA-Factory/saves/ztn_lora_v1` (or `_v2`) |
| Finetuning method | `lora` |

Clicked "Load Model" and waited ~30 seconds.

### 5.2 Five Test Queries

Designed to span the full data-rich → data-scarce gradient:

| Query | User-day | Expected category | Training examples |
|---|---|---|---:|
| 1 | MCF0300 (single PC, 8-17 hrs) | NORMAL | 2,100 |
| 2 | JFG1049 (8 after-hours, 2 PCs) | AFTER_HOURS | 600 |
| 3 | DNS1768 (7 PCs, 10 after-hours) | MULTI_PC | 200 |
| 4 | PRH2431 (5 weekend events) | WEEKEND_BURST | 75 |
| 5 | EPI3052 (2-23h, 6 PCs, 10 after-hours) | EXTREME_LATE_NIGHT | 25 |

Each query was the full instruction + behavioral fingerprint string, matching the format the model was trained on.

### 5.3 Two Evaluation Rounds

**Round 1** (instruction without explicit enum list): Model produced JSON with correct field names but free-text values for `anomaly_type`, `recommended_action`, and `confidence`.

**Round 2** (instruction with explicit enum list): Model produced compliant JSON across all categories, with residual errors only in `anomaly_type` for data-scarce categories.

The two rounds together demonstrated that:
1. Prompt engineering (explicit enum list) solves the closed-vocabulary problem
2. Data imbalance still causes category confusion in scarce classes — and this cannot be solved by prompt engineering alone


## Files Produced

### From Colab (Stage 1)
- `/content/task3_sft/ztn_sft.json` — 3,000 alpaca-format records
- `/content/task3_sft/dataset_info.json` — registration block
- `/content/task3_sft_bundle.zip` — upload bundle

### From glows.ai (Stages 2-5)
- `/LLaMA-Factory/data/ztn_sft.json` — uploaded dataset
- `/LLaMA-Factory/models/Qwen2.5-7B-Instruct/` — base model
- `/LLaMA-Factory/saves/ztn_lora_v1/` — round 1 LoRA adapter
- `/LLaMA-Factory/saves/ztn_lora_v2/` — round 2 LoRA adapter (with fixed instruction)
- Loss curves and parameter screenshots from the Web UI


## Key Lessons Learned

1. **Always check model availability before configuring training.** A gated model (LLaMA-3) cost real time before pivoting to an open one (Qwen2.5).

2. **The `instruction` field is part of the training signal.** Putting the enum list inside the instruction field, repeated across all 3,000 examples, was more effective than relying on the model to infer constraints from the output examples alone.

3. **Local model paths override HuggingFace identifiers.** Setting `Model path` to a local directory bypasses HuggingFace entirely — useful when the container has no internet or when the HF version is gated.

4. **Merge, don't replace, `dataset_info.json`.** Llama-Factory ships with many default datasets registered in this file. Overwriting it would break those.

5. **3,000 examples + LoRA rank 8 is underpowered for strict schema enforcement on 7B models** unless the schema is also enumerated explicitly in every training instruction. The signal needs to come from both the input instruction *and* the output examples — neither alone is sufficient.
