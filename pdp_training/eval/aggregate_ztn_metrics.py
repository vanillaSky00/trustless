#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

from ztn_eval_lib import (
    ACTIONS,
    ANOMALY_TYPES,
    classification_metrics,
    confusion_counts,
    read_jsonl,
)


def pct(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def clean_pred_label(value):
    return value if value in ANOMALY_TYPES else "__INVALID__"


def summarize(records):
    n = len(records)
    scores = [record["score"] for record in records]
    y_true = [record["expected"]["anomaly_type"] for record in records]
    y_pred = [clean_pred_label(score.get("pred_anomaly_type")) for score in scores]
    class_rows, macro_f1, weighted_f1 = classification_metrics(
        y_true, y_pred, ANOMALY_TYPES
    )
    recall_by_class = {row["label"]: row["recall"] for row in class_rows}

    severe_cases = [
        record
        for record in records
        if record["expected"]["risk_level"] in {"HIGH", "CRITICAL"}
    ]
    true_critical_action = [
        record
        for record in records
        if record["expected"]["recommended_action"] == "BLOCK_AND_ALERT"
    ]
    risk_errors = [
        score["risk_abs_error"]
        for score in scores
        if score.get("risk_abs_error") is not None
    ]

    row = {
        "run_name": records[0]["run_name"] if records else "",
        "benchmark": records[0]["benchmark"] if records else "",
        "n": n,
        "json_validity_rate": pct(sum(s["json_valid"] for s in scores), n),
        "json_object_extractable_rate": pct(
            sum(s["json_object_extractable"] for s in scores), n
        ),
        "extra_prose_rate": pct(sum(s["extra_prose"] for s in scores), n),
        "exact_field_set_rate": pct(sum(s["exact_fields"] for s in scores), n),
        "enum_compliance_rate": pct(
            sum(s["enum_fields_correct"] for s in scores),
            sum(s["enum_fields_total"] for s in scores),
        ),
        "type_compliance_rate": pct(
            sum(s["type_fields_correct"] for s in scores),
            sum(s["type_fields_total"] for s in scores),
        ),
        "full_schema_compliance_rate": pct(
            sum(s["full_schema_compliant"] for s in scores), n
        ),
        "extractable_schema_compliance_rate": pct(
            sum(s.get("extractable_schema_compliant", False) for s in scores), n
        ),
        "hallucinated_enum_rate": pct(
            sum(s["hallucinated_enum_fields"] for s in scores),
            sum(s["enum_fields_total"] for s in scores),
        ),
        "free_text_substitution_rate": pct(
            sum(s["free_text_substitution"] for s in scores), n
        ),
        "anomaly_accuracy": pct(sum(s["anomaly_type_correct"] for s in scores), n),
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "rare_class_recall_avg": sum(
            recall_by_class[label]
            for label in ["MULTI_PC", "WEEKEND_BURST", "EXTREME_LATE_NIGHT"]
        )
        / 3,
        "extreme_late_night_recall": recall_by_class["EXTREME_LATE_NIGHT"],
        "action_accuracy": pct(sum(s["action_correct"] for s in scores), n),
        "critical_action_recall": pct(
            sum(
                record["score"].get("pred_recommended_action") == "BLOCK_AND_ALERT"
                for record in true_critical_action
            ),
            len(true_critical_action),
        ),
        "under_action_rate": pct(sum(s["under_action"] for s in scores), n),
        "over_action_rate": pct(sum(s["over_action"] for s in scores), n),
        "severe_false_negative_rate": pct(
            sum(record["score"]["severe_false_negative"] for record in severe_cases),
            len(severe_cases),
        ),
        "risk_mae": sum(risk_errors) / len(risk_errors) if risk_errors else "",
    }

    for class_row in class_rows:
        label = class_row["label"].lower()
        row[f"recall_{label}"] = class_row["recall"]
        row[f"f1_{label}"] = class_row["f1"]

    return row, y_true, y_pred


def write_confusion(path, y_true, y_pred):
    matrix, columns = confusion_counts(y_true, y_pred, ANOMALY_TYPES)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["truth"] + columns)
        for label, row in zip(ANOMALY_TYPES, matrix):
            writer.writerow([label] + row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    jsonl_files = sorted(input_dir.glob("*.jsonl"))
    rows = []
    for path in jsonl_files:
        records = list(read_jsonl(path))
        if not records:
            continue
        row, y_true, y_pred = summarize(records)
        rows.append(row)
        confusion_path = input_dir / f"confusion_{row['benchmark']}_{row['run_name']}.csv"
        write_confusion(confusion_path, y_true, y_pred)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    json_output = output.with_suffix(".json")
    json_output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Wrote {json_output}")


if __name__ == "__main__":
    main()
