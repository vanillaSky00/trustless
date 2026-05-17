# Remote Benchmark Workflow

Use this after the three LoRA training runs finish on the glows server.

## 1. Upload the evaluation toolkit

From the local project directory:

```bash
scp -r -P <PORT> eval root@<GLOWS_HOST>:/LLaMA-Factory/
```

## 2. Prepare benchmark files on the server

```bash
ssh -p <PORT> root@<GLOWS_HOST>
cd /LLaMA-Factory

python3 eval/prepare_ztn_eval_sets.py \
  --source data/ztn_sft.json \
  --out-dir eval \
  --enum-dataset data/ztn_sft_enum.json
```

This writes:

```text
/LLaMA-Factory/eval/ztn_eval_screenshot_cases.jsonl
/LLaMA-Factory/eval/ztn_eval_core_balanced.jsonl
/LLaMA-Factory/eval/ztn_eval_rare_stress.jsonl
/LLaMA-Factory/data/ztn_sft_enum.json
```

Make sure `data/dataset_info.json` has a `ztn_sft_enum` entry before training.

By default, `rare_stress` excludes records already used in `core_balanced`.
Because the current file has only 25 `EXTREME_LATE_NIGHT` records, the
independent `rare_stress` set will be smaller than the original 50-example
target. This is better for clean comparison. If you need the exact requested
benchmark size and accept overlap, add:

```bash
--allow-benchmark-overlap
```

If you have a larger source file with enough rare examples and want a cleaner
held-out benchmark, create the training file with benchmark records removed:

```bash
python3 eval/prepare_ztn_eval_sets.py \
  --source data/ztn_sft.json \
  --out-dir eval \
  --enum-dataset data/ztn_sft_enum.json \
  --exclude-benchmark-from-enum-dataset
```

For the current 3,000-example file, be careful with this option because
`EXTREME_LATE_NIGHT` has only 25 examples. Removing benchmark records can leave
too little rare-class signal for training. If you only have `ztn_sft.json`, it is
usually better to train on all 3,000 examples and describe the benchmark as a
repeatable internal comparison rather than a fully held-out generalization test.

## 3. Run benchmarks

```bash
cd /LLaMA-Factory
chmod +x eval/evaluation.sh

eval/evaluation.sh screenshot_cases
eval/evaluation.sh core_balanced
eval/evaluation.sh rare_stress
```

If your trained adapters are under:

```text
/LLaMA-Factory/finetuing_models/
```

the script will use that folder automatically. To be explicit:

```bash
ADAPTER_ROOT=/LLaMA-Factory/finetuing_models eval/evaluation.sh core_balanced
```

The default adapter directory names are:

```text
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr2e4
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r32_a64_lr2e4
/LLaMA-Factory/finetuing_models/qwen2.5_7b_ztn_r8_a16_lr5e5
```

If `/LLaMA-Factory/models/Qwen2.5-7B-Instruct` does not exist, the script falls
back to the HuggingFace/cache id:

```text
Qwen/Qwen2.5-7B-Instruct
```

You can also set it explicitly:

```bash
BASE_MODEL=Qwen/Qwen2.5-7B-Instruct \
ADAPTER_ROOT=/LLaMA-Factory/finetuing_models \
eval/evaluation.sh screenshot_cases
```

If Hugging Face asks for authentication, pass a token through the environment:

```bash
export HF_TOKEN=hf_your_token_here

BASE_MODEL=Qwen/Qwen2.5-7B-Instruct \
ADAPTER_ROOT=/LLaMA-Factory/finetuing_models \
eval/evaluation.sh screenshot_cases
```

The lower-level Python script also accepts `--hf-token` or `--token`, but the
environment variable is safer because it avoids putting the token directly into
your shell history.

Do not set `BASE_MODEL` to the LoRA adapter directory unless you exported a
fully merged model. A LoRA folder with `adapter_model.safetensors` still needs
the original base model.

To evaluate only one trained adapter, use `RUN_FILTER`:

```bash
RUN_FILTER=C_r8_a16_lr5e5 \
ADAPTER_ROOT=/LLaMA-Factory/finetuing_models \
eval/evaluation.sh screenshot_cases
```

Run names are:

```text
base
A_r8_a16_lr2e4
B_r32_a64_lr2e4
C_r8_a16_lr5e5
```

Treat `screenshot_cases` as a five-case smoke test for screenshots, not a
statistical benchmark. Use `core_balanced` and `rare_stress` for the report's
main metrics.

Each run evaluates:

```text
base
A_r8_a16_lr2e4
B_r32_a64_lr2e4
C_r8_a16_lr5e5
```

Generation is deterministic: `do_sample=False`, equivalent to temperature 0.

Schema metric note:

```text
full_schema_compliance_rate = strict JSON only, no markdown/prose wrapper
extractable_schema_compliance_rate = valid schema if the first JSON object can be extracted
json_object_extractable_rate = parser can find a JSON object somewhere in the output
```

## 4. Outputs

For each benchmark:

```text
/LLaMA-Factory/eval/outputs/<benchmark>/
  base.jsonl
  A_r8_a16_lr2e4.jsonl
  B_r32_a64_lr2e4.jsonl
  C_r8_a16_lr5e5.jsonl
  metrics_summary.csv
  metrics_summary.json
  confusion_<benchmark>_<run>.csv
  figures/
```

The plotting script uses pandas and matplotlib. The canvas settings are defined first in `plot_ztn_metrics.py` through `plt.rcParams.update(CANVAS)`.

## 5. Download results

On the remote server:

```bash
cd /LLaMA-Factory
tar -czf /tmp/ztn_eval_outputs.tar.gz eval/outputs
```

From local:

```bash
scp -P <PORT> \
  root@<GLOWS_HOST>:/tmp/ztn_eval_outputs.tar.gz \
  /Users/harris/workshop/fintune/trustless/pdp_training/
```

```
tar -xzf ztn_eval_outputs.tar.gz
```

## 6. If a dependency is missing

Most LLaMA-Factory images already include `transformers`, `peft`, and `torch`.
If plotting fails, install:

```bash
pip install pandas matplotlib
```
