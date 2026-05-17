# Evaluation Output Analysis

Generated from `eval/outputs/` after running:

- `screenshot_cases`, 5 examples
- `core_balanced`, 100 examples
- `rare_stress`, 35 examples

Models compared:

| Run | Meaning |
|---|---|
| `base` | Qwen2.5-7B-Instruct without LoRA |
| `A_r8_a16_lr2e4` | Baseline LoRA, rank 8, alpha 16, lr 2e-4 |
| `B_r32_a64_lr2e4` | Higher-capacity LoRA, rank 32, alpha 64, lr 2e-4 |
| `C_r8_a16_lr5e5` | Lower-learning-rate LoRA, rank 8, alpha 16, lr 5e-5 |

## Important Validation Caveat

These benchmark files were generated from `ztn_sft.json`. If the three LoRA
models were trained on `ztn_sft_enum.json` made from the same records, then this
is not a fully held-out validation set. It is better described as an internal,
repeatable benchmark over known training-distribution examples.

This matters because the reported scores can be optimistic. The results are
still useful for comparing A/B/C under identical conditions, checking schema
compliance, and finding parameter-specific failure modes. They should not be
presented as final evidence of generalization to unseen CERT user-day records.

Suggested report wording:

> Because the rarest class contained only 25 examples, the benchmark was used as
> a repeatable internal comparison across LoRA configurations rather than a fully
> held-out test set. The main conclusion is therefore about relative behavior
> between LoRA settings, not absolute generalization performance.

## High-Level Result

All models achieved perfect schema compliance on these benchmark files:

| Benchmark | Schema result |
|---|---|
| `screenshot_cases` | 100% full schema compliance for all runs |
| `core_balanced` | 100% full schema compliance for all runs |
| `rare_stress` | 100% full schema compliance for all runs |

That means the major problem is no longer JSON validity or enum hallucination.
The remaining problem is decision quality: choosing the right `anomaly_type`,
`risk_level`, and `recommended_action`.

Overall, Run A is the best balanced model. Run C is best at catching
`EXTREME_LATE_NIGHT`, but it over-predicts that class and hurts `MULTI_PC`.
Run B does not improve the task despite higher LoRA rank.

## Core Balanced Benchmark

`core_balanced` has 100 examples, 20 per class.

| Run | Anomaly Acc. | Macro F1 | Rare Recall Avg | EXTREME Recall | Action Acc. | Severe FN |
|---|---:|---:|---:|---:|---:|---:|
| `base` | 40.0% | 30.2% | 5.0% | 0.0% | 37.0% | 100.0% |
| `A_r8_a16_lr2e4` | 71.0% | 71.2% | 56.7% | 45.0% | 75.0% | 15.0% |
| `B_r32_a64_lr2e4` | 61.0% | 54.5% | 41.7% | 0.0% | 66.0% | 0.0% |
| `C_r8_a16_lr5e5` | 65.0% | 60.1% | 53.3% | 95.0% | 57.0% | 20.0% |

Confusion-matrix highlights:

| Run | NORMAL | AFTER_HOURS | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT |
|---|---:|---:|---:|---:|---:|
| `base` | 19/20 | 18/20 | 0/20 | 3/20 | 0/20 |
| `A_r8_a16_lr2e4` | 20/20 | 17/20 | 9/20 | 16/20 | 9/20 |
| `B_r32_a64_lr2e4` | 20/20 | 16/20 | 5/20 | 20/20 | 0/20 |
| `C_r8_a16_lr5e5` | 20/20 | 13/20 | 2/20 | 11/20 | 19/20 |

Interpretation:

- The base model mostly collapses suspicious behavior into `AFTER_HOURS` and
  never catches `EXTREME_LATE_NIGHT`.
- Run A gives the best overall classification and action behavior.
- Run B improves safety in one narrow sense: severe false negatives are 0%.
  But it does this by over-escalating. Its over-action rate is 30.0%, and it
  completely misses `EXTREME_LATE_NIGHT` as a label.
- Run C strongly learns `EXTREME_LATE_NIGHT` with 19/20 recall, but it damages
  `MULTI_PC` badly. It predicts many `MULTI_PC` examples as
  `EXTREME_LATE_NIGHT`, which is often safe but not label-correct.

## Rare Stress Benchmark

`rare_stress` has 35 examples:

| Class | Count |
|---|---:|
| `MULTI_PC` | 15 |
| `WEEKEND_BURST` | 15 |
| `EXTREME_LATE_NIGHT` | 5 |

Because this benchmark has no `NORMAL` or `AFTER_HOURS` ground-truth examples,
the reported macro F1 is less meaningful here. The current metric code averages
macro F1 over all five classes, including classes with zero support. For this
benchmark, weighted F1, rare-class recall average, and the per-class confusion
matrix are more useful.

| Run | Anomaly Acc. | Weighted F1 | Rare Recall Avg | EXTREME Recall | Action Acc. | Severe FN |
|---|---:|---:|---:|---:|---:|---:|
| `base` | 14.3% | 22.1% | 15.6% | 20.0% | 2.9% | 94.3% |
| `A_r8_a16_lr2e4` | 74.3% | 83.2% | 66.7% | 40.0% | 40.0% | 8.6% |
| `B_r32_a64_lr2e4` | 54.3% | 61.2% | 46.7% | 20.0% | 28.6% | 2.9% |
| `C_r8_a16_lr5e5` | 42.9% | 44.8% | 51.1% | 80.0% | 31.4% | 20.0% |

Confusion-matrix highlights:

| Run | MULTI_PC | WEEKEND_BURST | EXTREME_LATE_NIGHT |
|---|---:|---:|---:|
| `base` | 0/15 | 4/15 | 1/5 |
| `A_r8_a16_lr2e4` | 9/15 | 15/15 | 2/5 |
| `B_r32_a64_lr2e4` | 3/15 | 15/15 | 1/5 |
| `C_r8_a16_lr5e5` | 1/15 | 10/15 | 4/5 |

Interpretation:

- Run A is clearly strongest on rare stress overall. It is the only model that
  keeps reasonable `MULTI_PC` recall while also getting perfect
  `WEEKEND_BURST` recall.
- Run C is best at `EXTREME_LATE_NIGHT`, but it sacrifices `MULTI_PC`.
  Thirteen of fifteen `MULTI_PC` examples are predicted as
  `EXTREME_LATE_NIGHT`.
- Run B again does not justify the higher LoRA rank. It preserves
  `WEEKEND_BURST`, but underperforms Run A on `MULTI_PC` and
  `EXTREME_LATE_NIGHT`.
- The base model is unsafe on rare stress: severe false negative rate is 94.3%,
  and action accuracy is only 2.9%.

## Screenshot Cases

The five screenshot cases are useful for qualitative examples, not statistics.
With only one example per class, recall and macro F1 jump in 0/1 steps.

| Run | Anomaly Acc. | Macro F1 | EXTREME Recall | Action Acc. | Severe FN |
|---|---:|---:|---:|---:|---:|
| `base` | 40.0% | 28.0% | 0.0% | 40.0% | 100.0% |
| `A_r8_a16_lr2e4` | 60.0% | 50.0% | 0.0% | 60.0% | 0.0% |
| `B_r32_a64_lr2e4` | 60.0% | 50.0% | 0.0% | 40.0% | 0.0% |
| `C_r8_a16_lr5e5` | 80.0% | 73.3% | 100.0% | 80.0% | 0.0% |

Run C looks best on this tiny set because it catches the single
`EXTREME_LATE_NIGHT` screenshot case. However, the larger benchmarks show that
this comes with a tradeoff: Run C often confuses `MULTI_PC` with
`EXTREME_LATE_NIGHT`.

## Parameter Conclusions

### Run A: Best Overall Choice

Run A, the baseline LoRA configuration, is the strongest general model:

- Best core-balanced anomaly accuracy: 71.0%
- Best core-balanced macro F1: 71.2%
- Best core-balanced action accuracy: 75.0%
- Best rare-stress anomaly accuracy: 74.3%
- Best rare-stress weighted F1: 83.2%

This is the best candidate to report as the main fine-tuned model.

### Run B: Higher Rank Did Not Help

Run B increased LoRA rank from 8 to 32 and alpha from 16 to 64, keeping the
LoRA scale constant. This should test additional adapter capacity. In these
results, it did not improve the task:

- Core-balanced anomaly accuracy dropped from 71.0% to 61.0%.
- Core-balanced macro F1 dropped from 71.2% to 54.5%.
- EXTREME_LATE_NIGHT recall dropped from 45.0% to 0.0% on core-balanced.
- Rare-stress weighted F1 dropped from 83.2% to 61.2%.

The higher-rank adapter appears to over-escalate decisions rather than improve
class separation. It has low severe false negatives, but that comes with high
over-action.

### Run C: Better Critical Recall, Worse Balance

Run C lowers the learning rate to 5e-5. It changes behavior strongly:

- Core-balanced EXTREME_LATE_NIGHT recall rises to 95.0%.
- Rare-stress EXTREME_LATE_NIGHT recall rises to 80.0%.
- But core-balanced MULTI_PC recall falls to 10.0%.
- Rare-stress MULTI_PC recall falls to 6.7%.

This run is useful evidence that lower learning rate changed the decision
boundary, but it is not the best overall PDP model. It over-detects the rarest
critical class and collapses many multi-device cases into
`EXTREME_LATE_NIGHT`.

## Security Interpretation

For a Zero Trust PDP, label accuracy and action safety are not the same thing.
Some wrong labels are still operationally safe if the action is strict enough.

Examples:

- Predicting `AFTER_HOURS` for true `EXTREME_LATE_NIGHT` is label-wrong.
- If the action is still `BLOCK_AND_ALERT`, the PDP action may be safe.
- If the action is `MONITOR`, it is a severe false negative.

This is why severe false negative rate and under-action rate matter.

The base model is clearly unsafe because it mostly recommends weak actions on
rare/severe cases. Fine-tuning reduces this risk substantially. Run A is the
best balance between correctness and safety. Run B and C reduce some safety
risks but introduce more over-action or class collapse.

## Recommended Report Claim

Use this as the main conclusion:

> Fine-tuning substantially improved schema-compliant PDP decision generation
> over the base Qwen2.5-7B-Instruct model. The baseline LoRA setting
> (`rank=8`, `alpha=16`, `lr=2e-4`) produced the best overall balance of
> anomaly classification, rare-class recall, and action accuracy. Increasing
> LoRA rank did not improve this task, while lowering the learning rate improved
> `EXTREME_LATE_NIGHT` recall but caused over-prediction of that class and worse
> `MULTI_PC` behavior.

Also include this limitation:

> Since the benchmark examples are derived from the same source file used to
> train the adapters, the evaluation is an internal comparison rather than a
> fully held-out test. Future work should regenerate additional rare examples or
> reserve a stratified test split before training.

## Recommendation

Use `A_r8_a16_lr2e4` as the main reported model.

Use `C_r8_a16_lr5e5` as an ablation showing the tradeoff between critical-event
recall and class balance.

Do not present `B_r32_a64_lr2e4` as an improvement. It is valuable as a negative
result: more adapter capacity did not automatically improve rare cybersecurity
classification.

For a stronger final evaluation, the next step should be to generate or reserve
a truly held-out benchmark before training, especially for:

- `MULTI_PC`
- `WEEKEND_BURST`
- `EXTREME_LATE_NIGHT`

The current results are still useful, but the honest interpretation is:

> Parameter tuning changed the model's behavior, but the dominant limitation is
> still rare-class scarcity and overlap between training and benchmark data.
