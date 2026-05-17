#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from ztn_eval_lib import read_jsonl, score_prediction, write_jsonl


def build_prompt(tokenizer, instruction, user_input):
    content = f"{instruction}\n\nInput:\n{user_input}"
    messages = [{"role": "user", "content": content}]
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    return content


def load_model(model_path, adapter_path=None, hf_token=None):
    auth_kwargs = {"token": hf_token} if hf_token else {}
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        use_fast=True,
        **auth_kwargs,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
        **auth_kwargs,
    )
    if adapter_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    return tokenizer, model


def generation_eos_token_ids(tokenizer):
    token_ids = []
    candidates = [tokenizer.eos_token_id]
    try:
        candidates.append(tokenizer.convert_tokens_to_ids("<|im_end|>"))
    except Exception:
        pass

    for token_id in candidates:
        if isinstance(token_id, int) and token_id >= 0 and token_id not in token_ids:
            token_ids.append(token_id)
    return token_ids or tokenizer.eos_token_id


@torch.inference_mode()
def generate_one(
    tokenizer,
    model,
    instruction,
    user_input,
    max_new_tokens,
):
    prompt = build_prompt(tokenizer, instruction, user_input)
    encoded = tokenizer(prompt, return_tensors="pt")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    input_len = encoded["input_ids"].shape[-1]
    output_ids = model.generate(
        **encoded,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=generation_eos_token_ids(tokenizer),
    )
    new_tokens = output_ids[0][input_len:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--eval-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--hf-token",
        "--token",
        dest="hf_token",
        default=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        help="Hugging Face token for loading gated/private models.",
    )
    args = parser.parse_args()

    eval_records = list(read_jsonl(args.eval_file))
    if args.limit:
        eval_records = eval_records[: args.limit]

    tokenizer, model = load_model(args.model, args.adapter, args.hf_token)
    output_records = []
    start = time.time()
    benchmark = Path(args.eval_file).stem.replace("ztn_eval_", "")

    for idx, record in enumerate(eval_records, 1):
        raw_output = generate_one(
            tokenizer=tokenizer,
            model=model,
            instruction=record["instruction"],
            user_input=record["input"],
            max_new_tokens=args.max_new_tokens,
        )
        score = score_prediction(raw_output, record["expected"])
        output_records.append(
            {
                "run_name": args.run_name,
                "benchmark": record.get("benchmark", benchmark),
                "eval_id": record.get("eval_id"),
                "case_id": record.get("case_id"),
                "input": record["input"],
                "expected": record["expected"],
                "raw_output": raw_output,
                "score": score,
            }
        )
        expected_label = record["expected"]["anomaly_type"]
        pred_label = score.get("pred_anomaly_type")
        print(
            f"[{args.run_name}] {idx}/{len(eval_records)} "
            f"expected={expected_label} pred={pred_label}"
        )

    elapsed = time.time() - start
    write_jsonl(args.output, output_records)
    meta_path = Path(args.output).with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "run_name": args.run_name,
                "benchmark": benchmark,
                "model": args.model,
                "adapter": args.adapter,
                "num_examples": len(output_records),
                "elapsed_seconds": elapsed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    print(f"Elapsed seconds: {elapsed:.1f}")


if __name__ == "__main__":
    main()
