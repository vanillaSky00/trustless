# Evaluation Planning: LoRA Fine-Tuning for a Zero Trust PDP Schema Model

This document defines how to evaluate the Task 2 fine-tuning experiments for the PDP / Zero Trust cybersecurity scenario.

The goal is not only to show that training loss decreases. The real question is:

> Does the fine-tuned model produce parseable, policy-safe, schema-compliant cybersecurity decisions, especially on rare high-risk events?


## 1. What We Are Evaluating

### Scenario

The model receives a user-day access behavior record:

```text
User: EPI3052 | Day: 2010-03-01 | Logons: 6 | Distinct PCs: 6 |
After-hours events: 10 | Weekend events: 0 | First hour: 2 | Last hour: 23 | Hour span: 21
```

It must output a strict JSON object:

```json
{
  "risk_level": "CRITICAL",
  "anomaly_type": "EXTREME_LATE_NIGHT",
  "device_trust": "UNMANAGED",
  "recommended_action": "BLOCK_AND_ALERT",
  "confidence": 0.94,
  "rationale": "Sustained activity from 02:00 to 23:00 across 6 machines with 10 after-hours events indicates extreme behavioral deviation."
}
```

### Models / Configurations to Compare

Use the same dataset and test prompts for every configuration.

| Run | Model | LoRA Rank | LoRA Alpha | Learning Rate | Purpose |
|---|---|---:|---:|---:|---|
| Base | Qwen2.5-7B-Instruct, no LoRA | n/a | n/a | n/a | Shows what the base model can do before fine-tuning |
| A | LoRA baseline | 8 | 16 | 2e-4 | Current reference setup |
| B | Higher capacity LoRA | 32 | 64 | 2e-4 | Tests whether larger adapter capacity helps rare classes |
| C | Lower learning rate | 8 | 16 | 5e-5 | Tests whether slower learning improves stability / avoids overfitting |

Optional extra run if time allows:

| Run | Model | LoRA Rank | LoRA Alpha | Learning Rate | Purpose |
|---|---|---:|---:|---:|---|
| D | Higher LR stress test | 8 | 16 | 5e-4 | Shows unstable or over-aggressive learning if loss curve becomes noisy |


## 2. Evaluation Sets

Do not evaluate only on one or two hand-picked examples. Use three small but repeatable benchmark sets.

### Benchmark 1: Core Balanced Test Set

Purpose: compare ordinary performance across all categories.

Recommended size: 100 examples.

| Class | Examples |
|---|---:|
| NORMAL | 20 |
| AFTER_HOURS | 20 |
| MULTI_PC | 20 |
| WEEKEND_BURST | 20 |
| EXTREME_LATE_NIGHT | 20 |

Why balanced? The training data is intentionally imbalanced. A balanced test set prevents the model from looking good simply because it predicts the majority class.

File name suggestion:

```text
ztn_eval_core_balanced.jsonl
```

### Benchmark 2: Rare-Class Stress Set

Purpose: test the exact security problem: rare but important events.

Recommended size: 50 examples.

| Class | Examples |
|---|---:|
| MULTI_PC | 15 |
| WEEKEND_BURST | 15 |
| EXTREME_LATE_NIGHT | 20 |

This is the most important benchmark for your assignment because it exposes whether parameter changes help the rare classes.

File name suggestion:

```text
ztn_eval_rare_stress.jsonl
```

### Benchmark 3: Five Screenshot Cases

Purpose: assignment screenshots and qualitative comparison.

Use the five examples you already wrote in `sft_evaluation.md`:

| Case | Expected Class |
|---|---|
| MCF0300 | NORMAL |
| JFG1049 | AFTER_HOURS |
| DNS1768 | MULTI_PC |
| PRH2431 | WEEKEND_BURST |
| EPI3052 | EXTREME_LATE_NIGHT |

This benchmark is too small for final metrics, but it is perfect for screenshots and explanation.

File name suggestion:

```text
ztn_eval_screenshot_cases.jsonl
```


## 3. Recommended Metrics

Use metrics in layers. This is important because a model can produce valid JSON while still making a bad cybersecurity decision.


## Layer A: Schema / Format Metrics

These metrics answer:

> Can the downstream PDP / PEP system parse and consume the model output?

### 1. JSON Validity Rate

Percentage of outputs that can be parsed as JSON.

```text
json_validity_rate = valid_json_outputs / total_outputs
```

Report this as a percentage.

Why it matters:

If this is low, the model is not usable in an automated PDP pipeline.

### 2. Exact Field Set Rate

Percentage of outputs containing exactly the required fields and no extra fields.

Required fields:

```text
risk_level
anomaly_type
device_trust
recommended_action
confidence
rationale
```

Formula:

```text
exact_field_set_rate = outputs_with_exact_required_fields / total_outputs
```

Why it matters:

Extra or missing fields can break downstream enforcement logic.

### 3. Enum Compliance Rate

Percentage of enum fields that use allowed values.

Allowed values:

```text
risk_level: LOW | MEDIUM | HIGH | CRITICAL
anomaly_type: NORMAL | AFTER_HOURS | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT
device_trust: TRUSTED | UNMANAGED
recommended_action: ALLOW | MONITOR | STEP_UP_AUTH | BLOCK_AND_ALERT
```

Formula:

```text
enum_compliance_rate = compliant_enum_fields / total_enum_fields
```

Why it matters:

This directly measures hallucinated values like `VERY_HIGH`, `UNTRUSTED`, or free-text actions.

### 4. Type Compliance Rate

Percentage of outputs where each field has the correct data type.

Expected types:

| Field | Type |
|---|---|
| risk_level | string |
| anomaly_type | string |
| device_trust | string |
| recommended_action | string |
| confidence | float or int |
| rationale | string |

Most important check:

```text
confidence must be numeric, not "HIGH" or "MEDIUM"
```

### 5. Full Schema Compliance Rate

Strictest schema metric.

An output passes only if:

- Valid JSON
- Exactly six required fields
- All enum fields valid
- `confidence` is numeric and between 0.0 and 1.0
- `rationale` is a non-empty string

Formula:

```text
full_schema_compliance_rate = fully_compliant_outputs / total_outputs
```

Use this as the main format metric.


## Layer B: Classification / Decision Metrics

These metrics answer:

> Is the cybersecurity decision correct?

### 6. Anomaly Type Accuracy

Percentage of examples where `anomaly_type` exactly matches ground truth.

```text
anomaly_type_accuracy = correct_anomaly_type / total_outputs
```

Why it matters:

This is where your rare-class problem appears. In previous runs, `EXTREME_LATE_NIGHT` collapsed into `AFTER_HOURS`.

### 7. Per-Class Recall

For each category, measure how many true examples were correctly recalled.

```text
recall(class) = true_positive_class / total_ground_truth_class
```

Report:

| Class | Recall |
|---|---:|
| NORMAL | |
| AFTER_HOURS | |
| MULTI_PC | |
| WEEKEND_BURST | |
| EXTREME_LATE_NIGHT | |

Most important:

```text
EXTREME_LATE_NIGHT recall
WEEKEND_BURST recall
MULTI_PC recall
```

Why it matters:

Accuracy can hide rare-class failure. Recall shows whether the model misses the events that matter most.

### 8. Macro F1

Average F1 score across all classes, treating each class equally.

Use macro F1 instead of only accuracy because the dataset is imbalanced.

```text
macro_f1 = average(F1_NORMAL, F1_AFTER_HOURS, F1_MULTI_PC, F1_WEEKEND_BURST, F1_EXTREME_LATE_NIGHT)
```

Why it matters:

Macro F1 punishes the model for failing rare classes.

### 9. Weighted F1

F1 score weighted by class frequency.

Why include it:

Weighted F1 shows performance under the real imbalanced distribution. Macro F1 shows fairness across classes.

Report both:

```text
macro_f1: rare-class-sensitive
weighted_f1: real-distribution-sensitive
```

### 10. Confusion Matrix

Make a 5x5 confusion matrix for `anomaly_type`.

Rows: ground truth  
Columns: model prediction

This is the clearest way to show category collapse:

```text
EXTREME_LATE_NIGHT -> AFTER_HOURS
MULTI_PC -> AFTER_HOURS
WEEKEND_BURST -> NORMAL or AFTER_HOURS
```


## Layer C: PDP / Security Metrics

These are the most interesting metrics for your report because they connect ML behavior to Zero Trust consequences.

### 11. Recommended Action Accuracy

Percentage of outputs where `recommended_action` matches ground truth.

```text
action_accuracy = correct_recommended_action / total_outputs
```

Why it matters:

In a PDP, action correctness may matter more than label correctness. For example, if the model predicts:

```text
anomaly_type = AFTER_HOURS
risk_level = CRITICAL
recommended_action = BLOCK_AND_ALERT
```

for an `EXTREME_LATE_NIGHT` case, the label is wrong but the enforcement action is still safe.

### 12. Critical Action Recall

For cases where the correct action is `BLOCK_AND_ALERT`, measure how often the model actually outputs `BLOCK_AND_ALERT`.

```text
critical_action_recall = predicted_BLOCK_AND_ALERT_on_true_critical / total_true_critical
```

This is one of the best cybersecurity metrics for the assignment.

Why it matters:

False negatives on critical events are the most dangerous failure mode.

### 13. Under-Action Rate

Percentage of cases where the model recommends a weaker action than ground truth.

Action severity order:

```text
ALLOW < MONITOR < STEP_UP_AUTH < BLOCK_AND_ALERT
```

Examples:

| Ground Truth | Prediction | Under-action? |
|---|---|---|
| BLOCK_AND_ALERT | MONITOR | yes |
| STEP_UP_AUTH | ALLOW | yes |
| MONITOR | STEP_UP_AUTH | no, this is over-action |

Formula:

```text
under_action_rate = under_action_outputs / total_outputs
```

Why it matters:

In security, under-action is usually worse than over-action.

### 14. Over-Action Rate

Percentage of cases where the model recommends a stricter action than ground truth.

```text
over_action_rate = over_action_outputs / total_outputs
```

Why it matters:

Over-action causes user friction, unnecessary alerts, and analyst fatigue.

### 15. Risk Ordinal Error

Map risk levels to numbers:

```text
LOW = 0
MEDIUM = 1
HIGH = 2
CRITICAL = 3
```

Then calculate average absolute error:

```text
risk_mae = mean(abs(predicted_risk_number - true_risk_number))
```

Why it matters:

This captures near misses. Predicting `HIGH` instead of `CRITICAL` is less bad than predicting `LOW`.

### 16. Severe False Negative Rate

For true high-severity cases, count outputs that are predicted too safely.

Define severe cases as:

```text
true risk_level in {HIGH, CRITICAL}
```

Define severe false negative as:

```text
true risk is HIGH or CRITICAL
predicted risk is LOW or MEDIUM
```

Formula:

```text
severe_false_negative_rate = severe_cases_predicted_low_or_medium / total_severe_cases
```

This should be highlighted in the final report.


## Layer D: Hallucination Metrics

These metrics answer:

> Is the model inventing values outside the policy schema?

### 17. Hallucinated Enum Rate

Percentage of enum fields with values outside the allowed set.

Examples of hallucinated enum values:

```text
VERY_HIGH
UNTRUSTED
INVESTIGATE
LOCK_ACCOUNT
User Logon from Multiple Devices
```

Formula:

```text
hallucinated_enum_rate = invalid_enum_fields / total_enum_fields
```

### 18. Free-Text Substitution Rate

Percentage of outputs where a closed enum field contains a sentence or phrase instead of an enum.

Example:

```json
"recommended_action": "Investigate the user's activity and consider additional authentication steps."
```

Why it matters:

This was a major Round 1 failure. It is useful evidence that explicit enum instructions improved the model.

### 19. Extra-Prose Rate

Percentage of responses that include text before or after the JSON object.

Example failure:

```text
Here is the JSON:
{ ... }
```

Why it matters:

Even if the JSON is correct, extra prose can break strict parsers.


## Layer E: Training Dynamics / Parameter Impact Metrics

These metrics answer:

> How did the parameter changes affect learning behavior?

### 20. Final Training Loss

Record final training loss from Llama-Factory.

Use this table:

| Run | Final Train Loss |
|---|---:|
| A: rank 8, lr 2e-4 | |
| B: rank 32, lr 2e-4 | |
| C: rank 8, lr 5e-5 | |

### 21. Final Validation Loss

If `val_size = 0.05`, record final validation loss.

| Run | Final Eval Loss |
|---|---:|
| A | |
| B | |
| C | |

### 22. Train-Eval Loss Gap

```text
loss_gap = final_eval_loss - final_train_loss
```

Interpretation:

| Pattern | Meaning |
|---|---|
| Train loss down, eval loss down | good learning |
| Train loss down, eval loss flat/up | possible overfitting |
| Loss noisy or spikes | learning rate may be too high |
| Loss barely changes | learning rate too low or adapter capacity too small |

### 23. Convergence Speed

Measure approximately how many steps it takes before the loss curve flattens.

```text
convergence_step = first step where loss stops improving meaningfully
```

Useful comparison:

| Run | Convergence Behavior |
|---|---|
| Rank 8 | baseline |
| Rank 32 | may learn faster / lower loss |
| LR 5e-5 | may learn slower but smoother |

### 24. Training Cost

Record:

- Total training time
- GPU memory if visible
- Steps per second or samples per second if available

Why it matters:

If rank 32 improves rare-class recall by only 1 percent but doubles training time, that is an important tradeoff.


## 4. Minimum Metric Set for the Assignment

If time is limited, report these eight metrics:

| Metric | Why It Matters |
|---|---|
| Full schema compliance rate | Can the PDP parse the output? |
| Hallucinated enum rate | Does the model invent invalid policy values? |
| Anomaly type accuracy | Does it identify the right incident category? |
| Macro F1 | Does it handle rare classes? |
| EXTREME_LATE_NIGHT recall | Does it catch the rarest critical case? |
| Recommended action accuracy | Does it choose the correct enforcement action? |
| Severe false negative rate | Does it miss high-risk events? |
| Final eval loss | Did parameter changes improve training dynamics? |

This is enough to make the evaluation strong.


## 5. Main Comparison Tables for the Report

### Table 1: Parameter Configurations

| Run | Rank | Alpha | Learning Rate | Epochs | Final Train Loss | Final Eval Loss |
|---|---:|---:|---:|---:|---:|---:|
| A | 8 | 16 | 2e-4 | 3 | | |
| B | 32 | 64 | 2e-4 | 3 | | |
| C | 8 | 16 | 5e-5 | 3 | | |

### Table 2: Schema Quality

| Run | JSON Validity | Exact Fields | Enum Compliance | Type Compliance | Full Schema Compliance |
|---|---:|---:|---:|---:|---:|
| Base | | | | | |
| A | | | | | |
| B | | | | | |
| C | | | | | |

### Table 3: Classification Quality

| Run | Anomaly Accuracy | Macro F1 | Weighted F1 | EXTREME Recall | Rare-Class Recall Avg |
|---|---:|---:|---:|---:|---:|
| Base | | | | | |
| A | | | | | |
| B | | | | | |
| C | | | | | |

Rare-class recall average:

```text
mean(recall_MULTI_PC, recall_WEEKEND_BURST, recall_EXTREME_LATE_NIGHT)
```

### Table 4: PDP Safety Metrics

| Run | Action Accuracy | Critical Action Recall | Under-Action Rate | Over-Action Rate | Severe False Negative Rate |
|---|---:|---:|---:|---:|---:|
| Base | | | | | |
| A | | | | | |
| B | | | | | |
| C | | | | | |

### Table 5: Five Screenshot Cases

| Case | Expected | Base | Run A | Run B | Run C |
|---|---|---|---|---|---|
| NORMAL | ALLOW / LOW / NORMAL | | | | |
| AFTER_HOURS | MONITOR / MEDIUM / AFTER_HOURS | | | | |
| MULTI_PC | STEP_UP_AUTH / HIGH / MULTI_PC | | | | |
| WEEKEND_BURST | STEP_UP_AUTH / HIGH / WEEKEND_BURST | | | | |
| EXTREME_LATE_NIGHT | BLOCK_AND_ALERT / CRITICAL / EXTREME_LATE_NIGHT | | | | |


## 6. Suggested Benchmark Strategy

### Best Benchmark for This Assignment

Use an internal CERT-derived benchmark.

Reason:

Your task is not general cybersecurity Q&A. It is structured PDP decision generation from behavioral telemetry. Public cybersecurity benchmarks usually test different abilities, such as vulnerability knowledge, malware analysis, or security exam questions. They are not aligned with your schema output task.

The strongest benchmark is therefore:

```text
Held-out CERT-derived user-day behavior examples
```

with known deterministic labels from your category rules.

### Baselines to Include

Use these baselines:

| Baseline | Why Include It |
|---|---|
| Base Qwen2.5-7B-Instruct without LoRA | Shows improvement from fine-tuning |
| Base Qwen2.5-7B-Instruct with explicit enum prompt only | Separates prompt engineering from fine-tuning |
| Rule-based labeler from your category function | Upper-bound reference for deterministic labels |
| LoRA rank 8, lr 2e-4 | Current baseline training config |

The rule-based labeler is not a fair AI competitor because it generated the labels. Treat it as the oracle / ground-truth generator.

### External Benchmarks

External cybersecurity benchmarks are optional and should not replace your internal benchmark.

Use them only as discussion context, for example:

```text
General cybersecurity benchmarks are useful for measuring security knowledge,
but they do not evaluate strict JSON schema compliance or PDP action safety.
Therefore, this project uses a task-specific CERT-derived benchmark.
```

This is a good methodological choice, not a weakness.


## 7. Evaluation Procedure

Use the same generation settings for every model.

Recommended settings:

```text
temperature = 0
top_p = 1.0
max_new_tokens = 256
repetition_penalty = 1.0
```

Why:

Deterministic decoding makes the comparison about model training, not sampling randomness.

Steps:

1. Load base model or LoRA adapter.
2. Run every evaluation prompt.
3. Save raw output exactly as produced.
4. Parse output as JSON.
5. Score schema metrics.
6. Score classification metrics.
7. Score PDP safety metrics.
8. Build comparison tables.
9. Take screenshots of representative examples.

Suggested output file structure:

```text
eval_outputs/
  base_outputs.jsonl
  rank8_lr2e4_outputs.jsonl
  rank32_lr2e4_outputs.jsonl
  rank8_lr5e5_outputs.jsonl
  metrics_summary.csv
  confusion_matrix_rank8_lr2e4.png
  confusion_matrix_rank32_lr2e4.png
  confusion_matrix_rank8_lr5e5.png
```


## 8. Simple Scoring Logic

For each example, assign:

```text
schema_score: 0 to 6 fields correct
decision_score: 0 to 4 main decision fields correct
safety_error: under-action / over-action / exact
```

Decision fields:

```text
risk_level
anomaly_type
device_trust
recommended_action
```

Example:

Ground truth:

```json
{
  "risk_level": "CRITICAL",
  "anomaly_type": "EXTREME_LATE_NIGHT",
  "device_trust": "UNMANAGED",
  "recommended_action": "BLOCK_AND_ALERT"
}
```

Prediction:

```json
{
  "risk_level": "CRITICAL",
  "anomaly_type": "AFTER_HOURS",
  "device_trust": "UNMANAGED",
  "recommended_action": "BLOCK_AND_ALERT"
}
```

Interpretation:

```text
Schema: pass
Decision score: 3/4
Security action: safe
SOC label: wrong
```

This is exactly the kind of nuanced result your project should discuss.


## 9. Python Evaluator Sketch

This is the logic the evaluator should implement.

```python
import json
from collections import Counter, defaultdict

RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ANOMALY_TYPES = ["NORMAL", "AFTER_HOURS", "MULTI_PC", "WEEKEND_BURST", "EXTREME_LATE_NIGHT"]
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

def parse_json(raw):
    try:
        return json.loads(raw), True
    except Exception:
        return None, False

def score_one(raw_output, truth):
    pred, valid_json = parse_json(raw_output)

    result = {
        "valid_json": valid_json,
        "exact_fields": False,
        "enum_fields_correct": 0,
        "enum_fields_total": 4,
        "type_fields_correct": 0,
        "type_fields_total": 6,
        "full_schema_compliant": False,
        "anomaly_type_correct": False,
        "risk_correct": False,
        "action_correct": False,
        "device_trust_correct": False,
        "under_action": False,
        "over_action": False,
        "severe_false_negative": False,
        "risk_abs_error": None,
    }

    if not valid_json or not isinstance(pred, dict):
        return result

    result["exact_fields"] = set(pred.keys()) == REQUIRED_FIELDS

    enum_checks = [
        pred.get("risk_level") in RISK_LEVELS,
        pred.get("anomaly_type") in ANOMALY_TYPES,
        pred.get("device_trust") in DEVICE_TRUST,
        pred.get("recommended_action") in ACTIONS,
    ]
    result["enum_fields_correct"] = sum(enum_checks)

    type_checks = [
        isinstance(pred.get("risk_level"), str),
        isinstance(pred.get("anomaly_type"), str),
        isinstance(pred.get("device_trust"), str),
        isinstance(pred.get("recommended_action"), str),
        isinstance(pred.get("confidence"), (int, float)) and 0.0 <= pred.get("confidence") <= 1.0,
        isinstance(pred.get("rationale"), str) and len(pred.get("rationale", "")) > 0,
    ]
    result["type_fields_correct"] = sum(type_checks)

    result["full_schema_compliant"] = (
        result["exact_fields"]
        and result["enum_fields_correct"] == result["enum_fields_total"]
        and result["type_fields_correct"] == result["type_fields_total"]
    )

    result["anomaly_type_correct"] = pred.get("anomaly_type") == truth["anomaly_type"]
    result["risk_correct"] = pred.get("risk_level") == truth["risk_level"]
    result["action_correct"] = pred.get("recommended_action") == truth["recommended_action"]
    result["device_trust_correct"] = pred.get("device_trust") == truth["device_trust"]

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
```


## 10. How to Interpret Likely Results

### If Rank 32 Improves Rare-Class Recall

Conclusion:

```text
Increasing LoRA rank gave the adapter more capacity to represent minority cybersecurity categories.
This improved rare-class recall, but may increase training time and overfitting risk.
```

### If Rank 32 Only Improves Loss, Not Outputs

Conclusion:

```text
Lower loss did not translate into better PDP behavior. This shows why task-specific metrics
are necessary; loss alone is insufficient for cybersecurity evaluation.
```

### If Lower LR Gives Smoother Loss but Worse Accuracy

Conclusion:

```text
The lower learning rate stabilized the loss curve but underfit the task within three epochs.
For this dataset size, 5e-5 may require more epochs.
```

### If Lower LR Improves Schema Compliance

Conclusion:

```text
A lower learning rate reduced output instability and helped preserve strict schema behavior,
but must be checked against rare-class recall.
```

### If All Fine-Tuned Models Still Miss EXTREME_LATE_NIGHT

Conclusion:

```text
Parameter tuning alone cannot solve severe data scarcity. The rarest class needs more examples,
oversampling, class-balanced sampling, or targeted synthetic augmentation.
```


## 11. Recommended Final Claim

The final report should not say:

```text
Fine-tuning solved the cybersecurity task.
```

A stronger and more honest claim is:

```text
Fine-tuning substantially improved schema compliance and PDP action consistency,
but rare-class recall remained the limiting factor. LoRA parameter changes affected
training dynamics and sometimes improved minority-class behavior, but the dominant
constraint was still class imbalance in critical cybersecurity events.
```


## 12. Screenshot Checklist

Include these screenshots in the assignment:

| Screenshot | Purpose |
|---|---|
| Llama-Factory config for Run A | Baseline parameter setup |
| Llama-Factory config for Run B | Shows changed LoRA rank / alpha |
| Llama-Factory config for Run C | Shows changed learning rate |
| Loss curve for Run A | Baseline learning dynamics |
| Loss curve for Run B | Capacity comparison |
| Loss curve for Run C | Learning-rate comparison |
| Base model output on EXTREME_LATE_NIGHT | Before fine-tuning failure |
| Best LoRA output on EXTREME_LATE_NIGHT | After fine-tuning improvement |
| Output comparison table | Before vs after, config vs config |


## 13. Priority Order

If time is short:

1. Run Base, A, B, C on the five screenshot cases.
2. Compute schema compliance and action correctness manually.
3. Run at least the 100-example balanced benchmark if possible.
4. Add confusion matrix and macro F1 if time allows.
5. Discuss loss curves last, because loss is supportive evidence, not the main evaluation.


## 14. The Key Evaluation Insight

The hardest part is separating three different things:

| Question | Metric |
|---|---|
| Did the model learn to speak JSON? | Full schema compliance |
| Did the model choose the right incident label? | Anomaly type accuracy / macro F1 |
| Did the model make a safe PDP decision? | Action accuracy / under-action rate / severe false negative rate |

For cybersecurity, the third question is the most important.

An output can be:

```text
schema-valid but security-wrong
label-wrong but action-safe
low-loss but operationally unsafe
```

That is why this evaluation plan uses schema metrics, classification metrics, and PDP safety metrics together.
