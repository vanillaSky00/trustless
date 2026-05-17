#!/usr/bin/env python3
import argparse
import json
import random
from pathlib import Path

from ztn_eval_lib import ANOMALY_TYPES, ENUM_INSTRUCTION, write_jsonl


SCREENSHOT_CASES = [
    {
        "case_id": "screenshot_normal_mcf0300",
        "input": (
            "User: MCF0300 | Day: 2011-03-15 | Logons: 2 | Distinct PCs: 1 | "
            "After-hours events: 0 | Weekend events: 0 | First hour: 8 | "
            "Last hour: 17 | Hour span: 9"
        ),
        "expected": {
            "risk_level": "LOW",
            "anomaly_type": "NORMAL",
            "device_trust": "TRUSTED",
            "recommended_action": "ALLOW",
            "confidence": 0.95,
            "rationale": (
                "Behavioral fingerprint matches a dense cluster of routine workforce activity."
            ),
        },
    },
    {
        "case_id": "screenshot_after_hours_jfg1049",
        "input": (
            "User: JFG1049 | Day: 2010-11-03 | Logons: 7 | Distinct PCs: 2 | "
            "After-hours events: 8 | Weekend events: 0 | First hour: 6 | "
            "Last hour: 23 | Hour span: 17"
        ),
        "expected": {
            "risk_level": "MEDIUM",
            "anomaly_type": "AFTER_HOURS",
            "device_trust": "TRUSTED",
            "recommended_action": "MONITOR",
            "confidence": 0.82,
            "rationale": (
                "Anomalous pattern: 8 after-hours events, early start at 6:00, "
                "late end at 23:00."
            ),
        },
    },
    {
        "case_id": "screenshot_multi_pc_dns1768",
        "input": (
            "User: DNS1768 | Day: 2010-12-21 | Logons: 7 | Distinct PCs: 7 | "
            "After-hours events: 10 | Weekend events: 0 | First hour: 5 | "
            "Last hour: 23 | Hour span: 18"
        ),
        "expected": {
            "risk_level": "HIGH",
            "anomaly_type": "MULTI_PC",
            "device_trust": "UNMANAGED",
            "recommended_action": "STEP_UP_AUTH",
            "confidence": 0.88,
            "rationale": (
                "Anomalous pattern: 10 after-hours events, activity across 7 machines, "
                "early start at 5:00."
            ),
        },
    },
    {
        "case_id": "screenshot_weekend_burst_prh2431",
        "input": (
            "User: PRH2431 | Day: 2010-12-18 | Logons: 6 | Distinct PCs: 2 | "
            "After-hours events: 3 | Weekend events: 5 | First hour: 7 | "
            "Last hour: 22 | Hour span: 15"
        ),
        "expected": {
            "risk_level": "HIGH",
            "anomaly_type": "WEEKEND_BURST",
            "device_trust": "UNMANAGED",
            "recommended_action": "STEP_UP_AUTH",
            "confidence": 0.85,
            "rationale": "Anomalous pattern: 5 weekend events, 3 after-hours events.",
        },
    },
    {
        "case_id": "screenshot_extreme_late_night_epi3052",
        "input": (
            "User: EPI3052 | Day: 2010-03-01 | Logons: 6 | Distinct PCs: 6 | "
            "After-hours events: 10 | Weekend events: 0 | First hour: 2 | "
            "Last hour: 23 | Hour span: 21"
        ),
        "expected": {
            "risk_level": "CRITICAL",
            "anomaly_type": "EXTREME_LATE_NIGHT",
            "device_trust": "UNMANAGED",
            "recommended_action": "BLOCK_AND_ALERT",
            "confidence": 0.94,
            "rationale": (
                "Sustained activity from 02:00 to 23:00 across 6 machines with "
                "10 after-hours events indicates extreme behavioral deviation."
            ),
        },
    },
]


def load_training_records(path):
    with Path(path).open("r", encoding="utf-8") as f:
        records = json.load(f)

    parsed = []
    for idx, record in enumerate(records):
        truth = json.loads(record["output"])
        parsed.append(
            {
                "case_id": f"train_{idx:04d}",
                "instruction": ENUM_INSTRUCTION,
                "input": record["input"],
                "expected": truth,
            }
        )
    return parsed


def sample_by_class(
    records,
    per_class_counts,
    rng,
    excluded_case_ids=None,
    allow_partial=False,
):
    excluded_case_ids = set(excluded_case_ids or [])
    by_class = {label: [] for label in ANOMALY_TYPES}
    for record in records:
        if record["case_id"] in excluded_case_ids:
            continue
        by_class[record["expected"]["anomaly_type"]].append(record)

    output = []
    actual_counts = {}
    shortages = {}
    for label, count in per_class_counts.items():
        available = by_class[label]
        if len(available) < count:
            if not allow_partial:
                raise ValueError(
                    f"Need {count} {label} examples, found {len(available)}"
                )
            sample_count = len(available)
            shortages[label] = {"requested": count, "available": len(available)}
        else:
            sample_count = count

        actual_counts[label] = sample_count
        output.extend(rng.sample(available, sample_count))
    rng.shuffle(output)
    return output, actual_counts, shortages


def with_benchmark(records, benchmark):
    output = []
    for idx, record in enumerate(records):
        item = dict(record)
        item["benchmark"] = benchmark
        item["eval_id"] = f"{benchmark}_{idx:03d}"
        output.append(item)
    return output


def write_enum_dataset(records, path):
    enum_records = []
    for record in records:
        enum_records.append(
            {
                "instruction": ENUM_INSTRUCTION,
                "input": record["input"],
                "output": json.dumps(record["expected"], ensure_ascii=False),
            }
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(enum_records, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="/LLaMA-Factory/data/ztn_sft.json")
    parser.add_argument("--out-dir", default="/LLaMA-Factory/eval")
    parser.add_argument("--enum-dataset", default=None)
    parser.add_argument(
        "--exclude-benchmark-from-enum-dataset",
        action="store_true",
        help="Exclude sampled core/rare benchmark records from the enum training file.",
    )
    parser.add_argument(
        "--allow-benchmark-overlap",
        action="store_true",
        help=(
            "Keep requested benchmark sizes even when rare classes overlap. By default, "
            "rare_stress excludes core_balanced records and shrinks if necessary."
        ),
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    records = load_training_records(args.source)

    screenshot = with_benchmark(
        [
            {
                "case_id": case["case_id"],
                "instruction": ENUM_INSTRUCTION,
                "input": case["input"],
                "expected": case["expected"],
            }
            for case in SCREENSHOT_CASES
        ],
        "screenshot_cases",
    )
    core_records, core_counts, core_shortages = sample_by_class(
        records,
        {
            "NORMAL": 20,
            "AFTER_HOURS": 20,
            "MULTI_PC": 20,
            "WEEKEND_BURST": 20,
            "EXTREME_LATE_NIGHT": 20,
        },
        rng,
    )
    core_balanced = with_benchmark(core_records, "core_balanced")

    rare_excluded_ids = set()
    rare_allow_partial = False
    if not args.allow_benchmark_overlap:
        rare_excluded_ids = {record["case_id"] for record in core_balanced}
        rare_allow_partial = True

    rare_records, rare_counts, rare_shortages = sample_by_class(
        records,
        {
            "MULTI_PC": 15,
            "WEEKEND_BURST": 15,
            "EXTREME_LATE_NIGHT": 20,
        },
        rng,
        excluded_case_ids=rare_excluded_ids,
        allow_partial=rare_allow_partial,
    )
    rare_stress = with_benchmark(rare_records, "rare_stress")

    if args.enum_dataset:
        enum_records = records
        if args.exclude_benchmark_from_enum_dataset:
            benchmark_ids = {record["case_id"] for record in core_balanced + rare_stress}
            enum_records = [
                record for record in records if record["case_id"] not in benchmark_ids
            ]
        write_enum_dataset(enum_records, args.enum_dataset)

    write_jsonl(out_dir / "ztn_eval_screenshot_cases.jsonl", screenshot)
    write_jsonl(out_dir / "ztn_eval_core_balanced.jsonl", core_balanced)
    write_jsonl(out_dir / "ztn_eval_rare_stress.jsonl", rare_stress)

    print(f"Wrote {len(screenshot)} screenshot cases")
    print(f"Wrote {len(core_balanced)} core balanced cases: {core_counts}")
    print(f"Wrote {len(rare_stress)} rare stress cases: {rare_counts}")
    if core_shortages:
        print(f"Core balanced shortages: {core_shortages}")
    if rare_shortages:
        print(f"Rare stress shortages after de-duplication: {rare_shortages}")
        print("Use --allow-benchmark-overlap if you need the originally requested size.")
    if args.enum_dataset:
        print(f"Wrote enum-explicit training data to {args.enum_dataset}")
        if args.exclude_benchmark_from_enum_dataset:
            print(f"Enum training records after exclusion: {len(enum_records)}")


if __name__ == "__main__":
    main()
