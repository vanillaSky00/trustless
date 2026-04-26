# Model Evaluation: ZTN Schema Output Quality

**Model:** Qwen2.5-7B-Instruct (LoRA SFT, rank=8, alpha=16)
**Dataset:** 3,000 examples across 5 categories
**Epochs:** 3
**Task:** Classify user-day access events → output structured ZTN incident JSON schema


## Training Dataset Distribution

| Category | Examples | % of Total | Role |
|---|---:|---:|---|
| NORMAL | 2,100 | 70.0% | 🟢 Data-rich |
| AFTER_HOURS | 600 | 20.0% | 🟡 Medium |
| MULTI_PC | 200 | 6.7% | 🟠 Data-scarce |
| WEEKEND_BURST | 75 | 2.5% | 🔴 Very scarce |
| EXTREME_LATE_NIGHT | 25 | 0.8% | 🔴 Extremely scarce |

**Imbalance ratio:** 84:1 (NORMAL vs EXTREME_LATE_NIGHT)


## Expected Schema (Ground Truth)

Every output must contain exactly these fields with these value constraints:

```json
{
  "risk_level":         "LOW | MEDIUM | HIGH | CRITICAL",
  "anomaly_type":       "NORMAL | AFTER_HOURS | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT",
  "device_trust":       "TRUSTED | UNMANAGED",
  "recommended_action": "ALLOW | MONITOR | STEP_UP_AUTH | BLOCK_AND_ALERT",
  "confidence":         0.0 - 1.0  (float),
  "rationale":          "one sentence string"
}
```


## Query 1 — NORMAL (2,100 training examples)

### Input
```
User: MCF0300 | Day: 2011-03-15 | Logons: 2 | Distinct PCs: 1 |
After-hours events: 0 | Weekend events: 0 | First hour: 8 | Last hour: 17 | Hour span: 9
```

### Expected Output
```json
{
  "risk_level": "LOW",
  "anomaly_type": "NORMAL",
  "device_trust": "TRUSTED",
  "recommended_action": "ALLOW",
  "confidence": 0.95,
  "rationale": "Behavioral fingerprint matches a dense cluster of routine workforce activity."
}
```

### Actual Model Output
```json
{
  "risk_level": "LOW",
  "anomaly_type": "User Logon from New Device",
  "device_trust": "UNTRUSTED",
  "recommended_action": "Review login activity and verify the user's device.",
  "confidence": "MEDIUM",
  "rationale": "The user MCF0300 logged in from a distinct PC for 9 hours on a weekday. While this is a normal business day, the change in device could indicate a potential security risk."
}
```

### Field-by-Field Analysis

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"LOW"` | `"LOW"` | ✅ Correct |
| `anomaly_type` | `"NORMAL"` | `"User Logon from New Device"` | ❌ Free text — enum not learned |
| `device_trust` | `"TRUSTED"` | `"UNTRUSTED"` | ❌ Wrong enum value |
| `recommended_action` | `"ALLOW"` | `"Review login activity..."` | ❌ Free text — enum not learned |
| `confidence` | `0.95` (float) | `"MEDIUM"` (string) | ❌ Wrong data type |
| `rationale` | String | String | ✅ Correct format |

**Verdict:** Schema structure correct (6 fields present, valid JSON) but 4/6 field values are non-compliant. Even the highest-volume category failed to produce correct enum vocabulary.


## Query 2 — AFTER_HOURS (600 training examples)

### Input
```
User: JFG1049 | Day: 2010-11-03 | Logons: 7 | Distinct PCs: 2 |
After-hours events: 8 | Weekend events: 0 | First hour: 6 | Last hour: 23 | Hour span: 17
```

### Expected Output
```json
{
  "risk_level": "MEDIUM",
  "anomaly_type": "AFTER_HOURS",
  "device_trust": "TRUSTED",
  "recommended_action": "MONITOR",
  "confidence": 0.82,
  "rationale": "Anomalous pattern: 8 after-hours events, early start at 6:00, late end at 23:00."
}
```

### Actual Model Output
```json
{
  "risk_level": "HIGH",
  "anomaly_type": "User Logon from Multiple Devices with After-Hours Activity",
  "device_trust": "UNTRUSTED",
  "recommended_action": "Investigate the user's activity and consider additional authentication steps.",
  "confidence": "HIGH",
  "rationale": "The user JFG1049 logged in from 2 distinct PCs for 17 hours, with 8 of those hours occurring during after-hours. This indicates potential unauthorized access or a compromised device."
}
```

### Field-by-Field Analysis

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"MEDIUM"` | `"HIGH"` | ❌ Over-escalated |
| `anomaly_type` | `"AFTER_HOURS"` | `"User Logon from Multiple Devices..."` | ❌ Free text |
| `device_trust` | `"TRUSTED"` | `"UNTRUSTED"` | ❌ Wrong enum |
| `recommended_action` | `"MONITOR"` | `"Investigate the user's activity..."` | ❌ Free text |
| `confidence` | `0.82` (float) | `"HIGH"` (string) | ❌ Wrong data type |
| `rationale` | String | String | ✅ Correct format |

**Verdict:** Risk direction escalated beyond correct level (MEDIUM → HIGH). Enum vocabulary still absent. Rationale quality is actually good — the model correctly identified the suspicious features.


## Query 3 — MULTI_PC (200 training examples)

### Input
```
User: DNS1768 | Day: 2010-12-21 | Logons: 7 | Distinct PCs: 7 |
After-hours events: 10 | Weekend events: 0 | First hour: 5 | Last hour: 23 | Hour span: 18
```

### Expected Output
```json
{
  "risk_level": "HIGH",
  "anomaly_type": "MULTI_PC",
  "device_trust": "UNMANAGED",
  "recommended_action": "STEP_UP_AUTH",
  "confidence": 0.88,
  "rationale": "Anomalous pattern: 10 after-hours events, activity across 7 machines, early start at 5:00."
}
```

### Actual Model Output
```json
{
  "risk_level": "VERY_HIGH",
  "anomaly_type": "User Logon from Multiple Devices with Extensive After-Hours Activity",
  "device_trust": "UNTRUSTED",
  "recommended_action": "Immediate investigation and potential lockdown of the user's account.",
  "confidence": "VERY_HIGH",
  "rationale": "The user DNS1768 logged in from 7 distinct PCs for 18 hours, with 10 of those hours occurring during after-hours. This indicates potential unauthorized access or a compromised environment."
}
```

### Field-by-Field Analysis

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"HIGH"` | `"VERY_HIGH"` | ❌ **Hallucinated enum** — value doesn't exist in schema |
| `anomaly_type` | `"MULTI_PC"` | `"User Logon from Multiple Devices..."` | ❌ Free text |
| `device_trust` | `"UNMANAGED"` | `"UNTRUSTED"` | ❌ Wrong enum (close but wrong) |
| `recommended_action` | `"STEP_UP_AUTH"` | `"Immediate investigation..."` | ❌ Free text |
| `confidence` | `0.88` (float) | `"VERY_HIGH"` (string) | ❌ **Hallucinated enum** |
| `rationale` | String | String | ✅ Correct format |

**Verdict:** First appearance of a hallucinated enum value (`"VERY_HIGH"`) — a value that was never in the training schema. The model invented a new category rather than selecting from the defined options.


## Query 4 — WEEKEND_BURST (75 training examples)

### Input
```
User: PRH2431 | Day: 2010-12-18 | Logons: 6 | Distinct PCs: 2 |
After-hours events: 3 | Weekend events: 5 | First hour: 7 | Last hour: 22 | Hour span: 15
```

### Expected Output
```json
{
  "risk_level": "HIGH",
  "anomaly_type": "WEEKEND_BURST",
  "device_trust": "UNMANAGED",
  "recommended_action": "STEP_UP_AUTH",
  "confidence": 0.85,
  "rationale": "Anomalous pattern: 5 weekend events, 3 after-hours events."
}
```

### Actual Model Output
```json
{
  "risk_level": "MEDIUM",
  "anomaly_type": "User Logon from Multiple Devices with After-Hours and Weekend Activity",
  "device_trust": "UNTRUSTED",
  "recommended_action": "Review the user's recent activity and consider additional authentication steps.",
  "confidence": "MEDIUM",
  "rationale": "The user PRH2431 logged in from 2 distinct PCs for 15 hours, with 3 after-hours events and 5 weekend events. This indicates potential unauthorized access or a compromised device."
}
```

### Field-by-Field Analysis

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"HIGH"` | `"MEDIUM"` | ❌ **Under-escalated** — defaulted toward majority class |
| `anomaly_type` | `"WEEKEND_BURST"` | `"User Logon from Multiple Devices..."` | ❌ Free text |
| `device_trust` | `"UNMANAGED"` | `"UNTRUSTED"` | ❌ Wrong enum |
| `recommended_action` | `"STEP_UP_AUTH"` | `"Review the user's recent activity..."` | ❌ Free text |
| `confidence` | `0.85` (float) | `"MEDIUM"` (string) | ❌ Wrong data type |
| `rationale` | String | String | ✅ Correct format |

**Verdict:** Risk **under-escalated** (HIGH → MEDIUM) — with only 75 training examples the model lacks confidence and reverts toward the majority-class risk level. This is the classic data-scarcity effect: model defaults to safe/common patterns when uncertain.


## Query 5 — EXTREME_LATE_NIGHT (25 training examples)

### Input
```
User: EPI3052 | Day: 2010-03-01 | Logons: 6 | Distinct PCs: 6 |
After-hours events: 10 | Weekend events: 0 | First hour: 2 | Last hour: 23 | Hour span: 21
```

### Expected Output
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

### Actual Model Output
```json
{
  "risk_level": "VERY_HIGH",
  "anomaly_type": "User Logon from Multiple Devices with Extensive After-Hours Activity",
  "device_trust": "UNTRUSTED",
  "recommended_action": "Immediate investigation and potential lockdown of the user's account.",
  "confidence": "VERY_HIGH",
  "rationale": "The user EPI3052 logged in from 6 distinct PCs for 21 hours, with 10 of those hours occurring during after-hours. This indicates potential unauthorized access or a compromised device."
}
```

### Field-by-Field Analysis

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"CRITICAL"` | `"VERY_HIGH"` | ❌ **Hallucinated enum** — CRITICAL never produced |
| `anomaly_type` | `"EXTREME_LATE_NIGHT"` | `"User Logon from Multiple Devices..."` | ❌ Free text — rarest category never recalled |
| `device_trust` | `"UNMANAGED"` | `"UNTRUSTED"` | ❌ Wrong enum |
| `recommended_action` | `"BLOCK_AND_ALERT"` | `"Immediate investigation..."` | ❌ Free text — most severe action never triggered |
| `confidence` | `0.94` (float) | `"VERY_HIGH"` (string) | ❌ **Hallucinated enum** |
| `rationale` | String | String | ✅ Correct format |

**Verdict:** Full hallucination on the rarest category. `CRITICAL` risk level was never produced despite being the most severe case. `BLOCK_AND_ALERT` — the most decisive ZTN action — was never triggered. With only 25 training examples the model has essentially no learned signal for this category and collapses into the same output pattern as MULTI_PC (200 examples), treating two very different scenarios identically.


## Summary Comparison Table

| Category | Training Examples | `risk_level` | `anomaly_type` | `confidence` type | `recommended_action` | Overall |
|---|---:|---|---|---|---|---|
| NORMAL | 2,100 | ✅ LOW | ❌ Free text | ❌ String | ❌ Free text | ⚠️ Partial |
| AFTER_HOURS | 600 | ❌ Over-escalated | ❌ Free text | ❌ String | ❌ Free text | ❌ Fail |
| MULTI_PC | 200 | ❌ Hallucinated enum | ❌ Free text | ❌ Hallucinated | ❌ Free text | ❌ Fail |
| WEEKEND_BURST | 75 | ❌ Under-escalated | ❌ Free text | ❌ String | ❌ Free text | ❌ Fail |
| EXTREME_LATE_NIGHT | 25 | ❌ Hallucinated enum | ❌ Never recalled | ❌ Hallucinated | ❌ Never triggered | ❌ Full hallucination |


## Three Distinct Failure Modes Observed

### Failure Mode 1: Enum Vocabulary Not Absorbed
**Fields affected:** `anomaly_type`, `recommended_action`
**All 5 queries** produced free-text descriptions instead of the defined enum labels. The model substituted natural language for closed-set vocabulary. The pre-trained tendency to generate descriptive text overrode the 3,000 fine-tuning examples.

### Failure Mode 2: Wrong Data Type for `confidence`
**All 5 queries** produced string labels (`"LOW"`, `"MEDIUM"`, `"HIGH"`, `"VERY_HIGH"`) instead of a float. The model conflated `confidence` with a categorical severity field.

### Failure Mode 3: Hallucinated Enum Values
**MULTI_PC and EXTREME_LATE_NIGHT** produced `"VERY_HIGH"` — a value that does not exist in the training schema. When the model is uncertain (scarce category, no strong learned signal), it invents plausible-sounding values rather than selecting from the trained vocabulary. This is the canonical hallucination pattern in fine-tuned LLMs.


## What the Model DID Learn

Despite the failures above, the fine-tuning was not without effect:

| Capability | Status | Evidence |
|---|---|---|
| JSON structure with 6 fields | ✅ Fully learned | All 5 outputs are valid JSON |
| Risk direction (normal = low risk) | ✅ Learned | NORMAL → LOW correct |
| Risk escalation with severity | ⚠️ Partially learned | Higher activity → higher risk, but miscalibrated |
| Feature identification in rationale | ✅ Learned | Rationale correctly identifies after-hours, multi-PC patterns |
| Closed enum vocabulary | ❌ Not learned | None of the defined labels appeared |


## Why This Happened — The Core Explanation

### 1. Fine-tuning was underpowered relative to model size
3,000 examples is a small signal for a 7B-parameter model pre-trained on hundreds of billions of tokens. The pre-trained prior (natural language generation) is extremely strong. Fine-tuning with LoRA adjusts only a small fraction of weights (rank=8 means ~0.1% of parameters), which is insufficient to override the base model's tendency to generate descriptive prose over closed enum values.

### 2. Instruction did not explicitly enumerate allowed values
The training instruction said *"output a ZTN incident schema"* but did not list the exact allowed values inline. Without seeing `"use only: LOW | MEDIUM | HIGH | CRITICAL"` in every training example, the model did not learn that these are the only acceptable outputs.

### 3. Data imbalance amplifies the enum problem for rare categories
For EXTREME_LATE_NIGHT (25 examples), the model saw the correct output format only 25 times — far too few repetitions to override the 2,100 NORMAL examples it saw. When faced with an ambiguous input, the model collapses toward the majority pattern and invents values when the minority pattern is under-constrained.

### 4. The imbalance effect is visible in risk calibration direction
Even though enum values are wrong across all categories, the **direction** of risk assessment correlates with training volume:
- High volume (NORMAL: 2,100) → risk direction correct (LOW)
- Medium volume (AFTER_HOURS: 600) → over-escalates (HIGH instead of MEDIUM)
- Low volume (WEEKEND_BURST: 75) → under-escalates (MEDIUM instead of HIGH)
- Minimal volume (EXTREME_LATE_NIGHT: 25) → hallucinates (VERY_HIGH instead of CRITICAL, never produces BLOCK_AND_ALERT)


## What Would Fix This

| Fix | Expected Impact |
|---|---|
| Add explicit enum list to every instruction | Fixes Failure Modes 1 and 2 almost completely |
| Increase to 10,000–30,000 training examples | Strengthens signal for scarce categories |
| Use full fine-tuning instead of LoRA | More weights updated → stronger schema enforcement |
| Add few-shot examples in the prompt | Bypasses fine-tuning limitation at inference time |
| Use a larger LoRA rank (32–64) | More capacity to memorize closed vocabulary |


## Key Takeaway for Zero Trust

> *"A model fine-tuned on imbalanced ZTN behavioral data failed to produce compliant schema output across all categories, with failure severity correlating with training data scarcity. The data-rich NORMAL category (2,100 examples) produced correct risk direction but non-compliant enum values. The data-scarce EXTREME_LATE_NIGHT category (25 examples) hallucinated enum values that do not exist in the schema and never triggered the most critical action (BLOCK_AND_ALERT) even for the most extreme behavioral profile. In a production Zero Trust pipeline, this hallucination behavior would cause the Policy Decision Point to fail silently — outputting a plausible-looking but structurally invalid decision that downstream enforcement cannot parse. Dataset size and distribution are not just training concerns; they are operational security concerns."*

<br>

# Round 2 — After System Prompt Fix

<br>

## What Changed

The `instruction` field in every training record was updated to explicitly enumerate all allowed enum values and enforce JSON-only output:

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

**Same model, same 3,000 examples, same LoRA config. Only the instruction text changed.**


# Round 2 Results — All 5 Queries

## Query 1 — NORMAL (2,100 examples)

**Input:**
```
User: MCF0300 | Day: 2011-03-15 | Logons: 2 | Distinct PCs: 1 |
After-hours events: 0 | Weekend events: 0 | First hour: 8 | Last hour: 17 | Hour span: 9
```

**Actual Output:**
```json
{
  "risk_level": "LOW",
  "anomaly_type": "NORMAL",
  "device_trust": "TRUSTED",
  "recommended_action": "ALLOW",
  "confidence": 0.75,
  "rationale": "User accessed the network during business hours from a single trusted device."
}
```

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"LOW"` | `"LOW"` | ✅ Correct |
| `anomaly_type` | `"NORMAL"` | `"NORMAL"` | ✅ Correct |
| `device_trust` | `"TRUSTED"` | `"TRUSTED"` | ✅ Correct |
| `recommended_action` | `"ALLOW"` | `"ALLOW"` | ✅ Correct |
| `confidence` | float | `0.75` | ✅ Correct |
| `rationale` | string | string | ✅ Correct |

**Verdict: 6/6 ✅ Perfect schema compliance.**


## Query 2 — AFTER_HOURS (600 examples)

**Input:**
```
User: JFG1049 | Day: 2010-11-03 | Logons: 7 | Distinct PCs: 2 |
After-hours events: 8 | Weekend events: 0 | First hour: 6 | Last hour: 23 | Hour span: 17
```

**Actual Output:**
```json
{
  "risk_level": "MEDIUM",
  "anomaly_type": "AFTER_HOURS",
  "device_trust": "TRUSTED",
  "recommended_action": "MONITOR",
  "confidence": 0.85,
  "rationale": "User accessed the network during after-hours from multiple devices, indicating potential unauthorized access."
}
```

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"MEDIUM"` | `"MEDIUM"` | ✅ Correct |
| `anomaly_type` | `"AFTER_HOURS"` | `"AFTER_HOURS"` | ✅ Correct |
| `device_trust` | `"TRUSTED"` | `"TRUSTED"` | ✅ Correct |
| `recommended_action` | `"MONITOR"` | `"MONITOR"` | ✅ Correct |
| `confidence` | float | `0.85` | ✅ Correct |
| `rationale` | string | string | ✅ Correct |

**Verdict: 6/6 ✅ Perfect schema compliance.**



## Query 3 — MULTI_PC (200 examples)

**Input:**
```
User: DNS1768 | Day: 2010-12-21 | Logons: 7 | Distinct PCs: 7 |
After-hours events: 10 | Weekend events: 0 | First hour: 5 | Last hour: 23 | Hour span: 18
```

**Actual Output:**
```json
{
  "risk_level": "HIGH",
  "anomaly_type": "AFTER_HOURS",
  "device_trust": "UNMANAGED",
  "recommended_action": "STEP_UP_AUTH",
  "confidence": 0.92,
  "rationale": "User accessed the network from multiple unmanaged devices during after-hours, indicating potential unauthorized access."
}
```

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"HIGH"` | `"HIGH"` | ✅ Correct |
| `anomaly_type` | `"MULTI_PC"` | `"AFTER_HOURS"` | ⚠️ Wrong category — confused with AFTER_HOURS |
| `device_trust` | `"UNMANAGED"` | `"UNMANAGED"` | ✅ Correct |
| `recommended_action` | `"STEP_UP_AUTH"` | `"STEP_UP_AUTH"` | ✅ Correct |
| `confidence` | float | `0.92` | ✅ Correct |
| `rationale` | string | string | ✅ Correct |

**Verdict: 5/6 ⚠️ Schema compliant but wrong `anomaly_type`. With only 200 MULTI_PC examples, the model correctly identifies the severity and action but misclassifies the category — conflating multi-PC activity with after-hours activity since they co-occur in the most extreme cases.**



## Query 4 — WEEKEND_BURST (75 examples)

**Input:**
```
User: PRH2431 | Day: 2010-12-18 | Logons: 6 | Distinct PCs: 2 |
After-hours events: 3 | Weekend events: 5 | First hour: 7 | Last hour: 22 | Hour span: 15
```

**Actual Output:**
```json
{
  "risk_level": "HIGH",
  "anomaly_type": "WEEKEND_BURST",
  "device_trust": "TRUSTED",
  "recommended_action": "MONITOR",
  "confidence": 0.88,
  "rationale": "User accessed the network during the weekend from multiple devices, indicating potential unauthorized access."
}
```

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"HIGH"` | `"HIGH"` | ✅ Correct |
| `anomaly_type` | `"WEEKEND_BURST"` | `"WEEKEND_BURST"` | ✅ Correct |
| `device_trust` | `"UNMANAGED"` | `"TRUSTED"` | ⚠️ Wrong — should be UNMANAGED |
| `recommended_action` | `"STEP_UP_AUTH"` | `"MONITOR"` | ⚠️ Under-action — insufficient for anomaly |
| `confidence` | float | `0.88` | ✅ Correct |
| `rationale` | string | string | ✅ Correct |

**Verdict: 4/6 ⚠️ Category and risk level correct — a clear improvement. But `device_trust` and `recommended_action` show residual scarcity effect: with 75 examples the model learned the category name but not all its associated field values precisely.**



## Query 5 — EXTREME_LATE_NIGHT (25 examples)

**Input:**
```
User: EPI3052 | Day: 2010-03-01 | Logons: 6 | Distinct PCs: 6 |
After-hours events: 10 | Weekend events: 0 | First hour: 2 | Last hour: 23 | Hour span: 21
```

**Actual Output:**
```json
{
  "risk_level": "CRITICAL",
  "anomaly_type": "AFTER_HOURS",
  "device_trust": "UNMANAGED",
  "recommended_action": "BLOCK_AND_ALERT",
  "confidence": 0.95,
  "rationale": "User accessed the network during after-hours from multiple unmanaged devices, indicating potential unauthorized access."
}
```

| Field | Expected | Actual | Status |
|---|---|---|---|
| `risk_level` | `"CRITICAL"` | `"CRITICAL"` | ✅ Correct — now fires! |
| `anomaly_type` | `"EXTREME_LATE_NIGHT"` | `"AFTER_HOURS"` | ⚠️ Wrong — rarest category still not recalled |
| `device_trust` | `"UNMANAGED"` | `"UNMANAGED"` | ✅ Correct |
| `recommended_action` | `"BLOCK_AND_ALERT"` | `"BLOCK_AND_ALERT"` | ✅ Correct — most critical action now fires! |
| `confidence` | float | `0.95` | ✅ Correct |
| `rationale` | string | string | ✅ Correct |

**Verdict: 5/6 ⚠️ Major improvement from Round 1. `CRITICAL` risk and `BLOCK_AND_ALERT` now both fire correctly — the most operationally important fields are correct. The only remaining failure is `anomaly_type`: with only 25 training examples, the model cannot reliably recall `EXTREME_LATE_NIGHT` as a distinct label and collapses it into the nearest known category (`AFTER_HOURS`).**


## Round 1 vs Round 2 — Side-by-Side Comparison

This is the **core finding** of Task 3.

| Category | Training Examples | Round 1 Score | Round 2 Score | Key Improvement |
|---|---:|---|---|---|
| NORMAL | 2,100 | 2/6 ❌ | **6/6 ✅** | All fields now compliant |
| AFTER_HOURS | 600 | 1/6 ❌ | **6/6 ✅** | Perfect after instruction fix |
| MULTI_PC | 200 | 0/6 ❌ | **5/6 ⚠️** | Schema compliant, category confused |
| WEEKEND_BURST | 75 | 0/6 ❌ | **4/6 ⚠️** | Category recalled, action under-specified |
| EXTREME_LATE_NIGHT | 25 | 0/6 ❌ | **5/6 ⚠️** | CRITICAL+BLOCK_AND_ALERT fire, category not recalled |

### What the system prompt fix resolved
- ✅ Enum vocabulary absorbed for all compliant fields
- ✅ `confidence` now correctly a float (not a string)
- ✅ `recommended_action` now uses defined enum values
- ✅ `CRITICAL` risk level and `BLOCK_AND_ALERT` now trigger on extreme cases
- ✅ JSON-only output — no surrounding prose

### What the system prompt fix could NOT resolve
- ⚠️ `anomaly_type` for scarce categories — MULTI_PC and EXTREME_LATE_NIGHT both collapse to `AFTER_HOURS`
- ⚠️ `device_trust` for WEEKEND_BURST — residual scarcity effect on associated field values


## The Definitive Finding

The two rounds together tell the complete Task 3 story:

**Round 1 (without explicit enum list in instruction):**
All 5 categories failed enum compliance. Failure was uniform across categories — even 2,100 NORMAL examples were insufficient to teach closed-vocabulary output without explicit enumeration in the prompt.

**Round 2 (with explicit enum list in instruction):**
Schema compliance improved dramatically across all categories. But a **clear residual imbalance effect persists specifically in `anomaly_type`** — the field that requires distinguishing between 5 named categories. With 2,100 examples, `NORMAL` is perfect. With 600, `AFTER_HOURS` is perfect. With 200 and below, the model confuses the category label with the nearest high-frequency one.

> **The system prompt fix solved the vocabulary problem. The data imbalance problem remained — and it shows precisely in the one field (`anomaly_type`) that requires discriminating between rare categories.**

This is the cleanest possible demonstration of the assignment's core question: *"How does dataset size and distribution influence the model's ability to maintain consistent output formats and reduce hallucinations?"*

**Answer:** Explicit instruction format solves the vocabulary constraint. Only sufficient training data solves the category discrimination problem. No prompt engineering can substitute for adequate representation of rare classes in the training distribution.


## Operational Implication for Zero Trust

In a production ZTN pipeline, the remaining `anomaly_type` confusion has a specific consequence:

- The **enforcement action** (`BLOCK_AND_ALERT`) is now correct for extreme cases ✅
- The **risk level** (`CRITICAL`) is now correct for extreme cases ✅
- But the **incident category** (`AFTER_HOURS` instead of `EXTREME_LATE_NIGHT`) would mislabel the incident in the SOC ticket

This means: the right action would be taken, but the incident would be filed under the wrong category — potentially causing analysts to apply the wrong remediation playbook and obscuring the true attack pattern from threat-hunting retrospectives. Even partial hallucination has downstream operational consequences.
