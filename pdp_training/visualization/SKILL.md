---
name: benchmark-dark-dashboard
description: Build a dark, minimalistic single-page HTML dashboard from benchmark eval outputs (metrics_summary.csv + confusion_*.csv). Re-renders matplotlib figures in a dark palette, embeds them in an article-style HTML page with interactive benchmark-tab swapping, KPI tiles, configuration cards, confusion-matrix grid, and a per-run summary table. Use when the user has new benchmark results and wants a polished, self-contained visualization to share.
when_to_use: >
  User has run an eval / benchmark sweep that produced per-run metrics CSVs and confusion-matrix CSVs,
  and asks for a "visualization", "dashboard", "report page", or to compare runs visually.
  Especially when they want a dark theme, figures that work in a single shared HTML file,
  or an offline-friendly report with run-level comparison.
---

# Dark Benchmark Dashboard Skill

This skill describes the exact inputs, outputs, and reliable usage pattern for `visualization/regenerate_figures.py` and `visualization/index.html`.

It is intentionally precise: the script is designed for the existing PDP benchmark output shape and uses hard-coded benchmark/run names, so the guidance here is the safest way to reuse the dashboard without breaking it.

---

## 1. Inputs the skill expects

Layout under `eval/outputs/`:

```
eval/outputs/
└── <benchmark>/
    ├── metrics_summary.csv
    ├── metrics_summary.json
    ├── confusion_<benchmark>_<run>.csv
```

`metrics_summary.csv` must include at least these columns:

- run_name
- benchmark
- n
- json_validity_rate
- exact_field_set_rate
- enum_compliance_rate
- full_schema_compliance_rate
- hallucinated_enum_rate
- anomaly_accuracy
- macro_f1
- rare_class_recall_avg
- extreme_late_night_recall
- action_accuracy
- severe_false_negative_rate
- over_action_rate
- under_action_rate

Extra columns are fine; missing columns will cause the script to fail in the corresponding chart.

The confusion CSVs must have:
- a first column named `truth`
- one or more predicted class columns
- optional `__INVALID__` column, which is dropped before plotting

This script expects the run names defined in `RUN_ORDER`, so if your dataset uses other run IDs, add them to `RUN_ORDER`, `RUN_COLORS`, and `RUN_LABELS` in `visualization/regenerate_figures.py`.

---

## 2. Outputs the skill produces

```
visualization/
├── index.html
├── regenerate_figures.py
├── SKILL.md
└── figures/
    ├── <bench>_schema_quality.png
    ├── <bench>_classification_quality.png
    ├── <bench>_pdp_safety.png
    └── confusion_<bench>_<run>.png
```

The page is built from those PNGs and the static HTML/CSS/JS in `visualization/index.html`. It is offline-portable and does not require any CDN or build tool.

---

## 3. Recommended workflow

### Step 1 — regenerate figures

```bash
cd visualization
python3 regenerate_figures.py
```

The script reads `../eval/outputs/<benchmark>/metrics_summary.csv` and `confusion_<benchmark>_<run>.csv` files and writes the rendered PNGs into `visualization/figures/`.

**Required Python packages**: `matplotlib`, `pandas`, `numpy`.

If package installation fails on macOS due to PEP 668, use a project-local environment or `--break-system-packages` only for this visualization step.

### Step 2 — open the HTML

```bash
open visualization/index.html
```

No additional build step is required. The HTML works from `file://` as long as the browser permits local image access.

---

## 4. Practical reliability notes

- The script assumes metric values are ratios in `[0, 1]` and formats bar labels as percentages. If your metrics are already percentages or raw values, update `grouped_bar()` in `visualization/regenerate_figures.py`.
- `visualization/regenerate_figures.py` is not schema-flexible: it processes the hard-coded `BENCHMARKS`, `RUN_ORDER`, and metric column groups defined in the script.
- If your benchmark directory names differ, update `BENCHMARKS`.
- If your run IDs differ, update `RUN_ORDER`, `RUN_COLORS`, and `RUN_LABELS`.
- If you want to plot additional or different metrics, update the metric lists inside `process_benchmark()`.
- The HTML and script assume generated PNGs are in `visualization/figures/` relative to `index.html`.
- The confusion-matrix loader drops `__INVALID__` automatically; keep that column optional rather than required.

---

## 5. Design tokens and palette

The dashboard is built from a coordinated dark palette that should stay consistent between the script and the HTML.

### Background / surfaces

| Token | Hex | Purpose |
|---|---|---|
| `--bg` | `#0a0b0e` | Page background, figure background |
| `--bg-1` | `#0f1115` | Card/figure panel surface |
| `--bg-2` | `#14171d` | Elevated surface, inline code |
| `--bg-3` | `#1a1e26` | Active tab pills |
| `--line` | `#232832` | Borders, axis lines |
| `--line-2` | `#2c333f` | Secondary borders |

### Text

| Token | Hex | Purpose |
|---|---|---|
| `--text` | `#e6e8ec` | Primary text |
| `--text-dim` | `#9aa3b2` | Labels, axis annotations |
| `--text-mute` | `#6b7382` | Secondary notes, zero values |

### Run colors

| Run | Hex |
|---|---|
| Base | `#6e7887` |
| Run A | `#7c9cff` |
| Run B | `#f0b86e` |
| Run C | `#ff7a7a` |

### Semantic accents

| Token | Hex |
|---|---|
| `--good` | `#4ade80` |
| `--warn` | `#facc15` |
| `--bad` | `#ef4444` |
| `--crit` | `#f472b6` |

### Confusion heatmap gradient

```
0.00 #14171d
0.30 #1f2a44
0.55 #2a3656
0.80 #3d5fb8
1.00 #6e90ff
```

Use text contrast rules similar to the script: numbers above the threshold are light, zeros are muted, and small values use a dim secondary text.

---

## 6. Matplotlib dark styling

The script uses a dark rcParams profile to keep the figure PNGs visually aligned with the HTML.

Key styling decisions:
- only the bottom spine remains visible
- axis labels use a muted text color
- grid lines are very subtle
- legend and figure backgrounds match the page background
- high DPI output for sharp Retina display rendering

### Bar chart pattern

- metrics are x-axis groups
- runs are the legend entries
- bar labels are placed slightly above each bar
- percentage formatting assumes ratio inputs
