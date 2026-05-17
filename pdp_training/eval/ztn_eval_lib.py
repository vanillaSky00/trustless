import json
from collections import Counter
from pathlib import Path


RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ANOMALY_TYPES = [
    "NORMAL",
    "AFTER_HOURS",
    "MULTI_PC",
    "WEEKEND_BURST",
    "EXTREME_LATE_NIGHT",
]
DEVICE_TRUST = ["TRUSTED", "UNMANAGED"]
ACTIONS = ["ALLOW", "MONITOR", "STEP_UP_AUTH", "BLOCK_AND_ALERT"]
REQUIRED_FIELDS = {
    "risk_level",
    "anomaly_type",
    "device_trust",
    "recommended_action",
    "confidence",
    "rationale",
}

ENUM_FIELDS = {
    "risk_level": RISK_LEVELS,
    "anomaly_type": ANOMALY_TYPES,
    "device_trust": DEVICE_TRUST,
    "recommended_action": ACTIONS,
}

ACTION_SEVERITY = {
    "ALLOW": 0,
    "MONITOR": 1,
    "STEP_UP_AUTH": 2,
    "BLOCK_AND_ALERT": 3,
}

RISK_SEVERITY = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}

ENUM_INSTRUCTION = (
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


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_json_strict(raw):
    try:
        value = json.loads(raw.strip())
    except Exception:
        return None, False
    return value, isinstance(value, dict)


def extract_first_json_object(raw):
    decoder = json.JSONDecoder()
    for idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(value, dict):
            return value, True
    return None, False


def has_free_text_enum_substitution(pred):
    if not isinstance(pred, dict):
        return False
    for field, allowed in ENUM_FIELDS.items():
        value = pred.get(field)
        if value in allowed:
            continue
        if isinstance(value, str):
            return True
    return False


def score_prediction(raw_output, truth):
    strict_pred, strict_json = parse_json_strict(raw_output)
    extracted_pred, extracted_json = extract_first_json_object(raw_output)
    pred = strict_pred if strict_json else extracted_pred
    usable_pred = isinstance(pred, dict)

    result = {
        "json_valid": strict_json,
        "json_object_extractable": extracted_json,
        "extra_prose": bool(extracted_json and not strict_json),
        "exact_fields": False,
        "enum_fields_correct": 0,
        "enum_fields_total": 4,
        "type_fields_correct": 0,
        "type_fields_total": 6,
        "full_schema_compliant": False,
        "extractable_schema_compliant": False,
        "hallucinated_enum_fields": 4,
        "free_text_substitution": False,
        "anomaly_type_correct": False,
        "risk_correct": False,
        "action_correct": False,
        "device_trust_correct": False,
        "under_action": False,
        "over_action": False,
        "severe_false_negative": False,
        "risk_abs_error": None,
        "pred_anomaly_type": None,
        "pred_risk_level": None,
        "pred_recommended_action": None,
        "pred_device_trust": None,
    }

    if not usable_pred:
        return result

    result["exact_fields"] = set(pred.keys()) == REQUIRED_FIELDS

    enum_checks = {
        field: pred.get(field) in allowed for field, allowed in ENUM_FIELDS.items()
    }
    result["enum_fields_correct"] = sum(enum_checks.values())
    result["hallucinated_enum_fields"] = (
        result["enum_fields_total"] - result["enum_fields_correct"]
    )
    result["free_text_substitution"] = has_free_text_enum_substitution(pred)

    type_checks = [
        isinstance(pred.get("risk_level"), str),
        isinstance(pred.get("anomaly_type"), str),
        isinstance(pred.get("device_trust"), str),
        isinstance(pred.get("recommended_action"), str),
        isinstance(pred.get("confidence"), (int, float))
        and 0.0 <= pred.get("confidence") <= 1.0,
        isinstance(pred.get("rationale"), str) and len(pred.get("rationale", "")) > 0,
    ]
    result["type_fields_correct"] = sum(type_checks)

    result["full_schema_compliant"] = (
        result["json_valid"]
        and result["exact_fields"]
        and result["enum_fields_correct"] == result["enum_fields_total"]
        and result["type_fields_correct"] == result["type_fields_total"]
    )
    result["extractable_schema_compliant"] = (
        result["json_object_extractable"]
        and result["exact_fields"]
        and result["enum_fields_correct"] == result["enum_fields_total"]
        and result["type_fields_correct"] == result["type_fields_total"]
    )

    result["pred_anomaly_type"] = pred.get("anomaly_type")
    result["pred_risk_level"] = pred.get("risk_level")
    result["pred_recommended_action"] = pred.get("recommended_action")
    result["pred_device_trust"] = pred.get("device_trust")

    result["anomaly_type_correct"] = (
        pred.get("anomaly_type") == truth["anomaly_type"]
    )
    result["risk_correct"] = pred.get("risk_level") == truth["risk_level"]
    result["action_correct"] = (
        pred.get("recommended_action") == truth["recommended_action"]
    )
    result["device_trust_correct"] = (
        pred.get("device_trust") == truth["device_trust"]
    )

    pred_action = pred.get("recommended_action")
    true_action = truth["recommended_action"]
    if pred_action in ACTION_SEVERITY:
        pred_level = ACTION_SEVERITY[pred_action]
        true_level = ACTION_SEVERITY[true_action]
        result["under_action"] = pred_level < true_level
        result["over_action"] = pred_level > true_level

    pred_risk = pred.get("risk_level")
    true_risk = truth["risk_level"]
    if pred_risk in RISK_SEVERITY:
        pred_level = RISK_SEVERITY[pred_risk]
        true_level = RISK_SEVERITY[true_risk]
        result["risk_abs_error"] = abs(pred_level - true_level)
        result["severe_false_negative"] = (
            true_level >= RISK_SEVERITY["HIGH"]
            and pred_level <= RISK_SEVERITY["MEDIUM"]
        )

    return result


def classification_metrics(y_true, y_pred, labels):
    rows = []
    support_total = len(y_true)
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred))
        support = sum(t == label for t in y_true)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        rows.append(
            {
                "label": label,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
            }
        )

    macro_f1 = sum(row["f1"] for row in rows) / len(rows) if rows else 0.0
    weighted_f1 = (
        sum(row["f1"] * row["support"] for row in rows) / support_total
        if support_total
        else 0.0
    )
    return rows, macro_f1, weighted_f1


def confusion_counts(y_true, y_pred, labels):
    counts = Counter(zip(y_true, y_pred))
    columns = labels + ["__INVALID__"]
    return [
        [counts.get((true_label, pred_label), 0) for pred_label in columns]
        for true_label in labels
    ], columns
