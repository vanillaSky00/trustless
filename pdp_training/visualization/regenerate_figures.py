#!/usr/bin/env python3
"""
Regenerate the eval figures with a dark, minimalistic palette.

Inputs (read-only): ../eval/outputs/<benchmark>/{metrics_summary.csv, confusion_*.csv}
Outputs:            ./figures/<benchmark>_{schema,classification,pdp_safety}.png
                    ./figures/confusion_<benchmark>_<run>.png

The set of figures and their semantics mirror eval/plot_ztn_metrics.py exactly.
Only the visual styling is changed.
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

HERE = Path(__file__).resolve().parent
EVAL_OUT = HERE.parent / "eval" / "outputs"
OUT_DIR = HERE / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ----- palette (match the HTML) -----
BG      = "#0a0b0e"
PANEL   = "#0f1115"
LINE    = "#232832"
TEXT    = "#e6e8ec"
DIM     = "#9aa3b2"
MUTE    = "#6b7382"

RUN_COLORS = {
    "base":            "#6e7887",
    "A_r8_a16_lr2e4":  "#7c9cff",
    "B_r32_a64_lr2e4": "#f0b86e",
    "C_r8_a16_lr5e5":  "#ff7a7a",
}
RUN_LABELS = {
    "base":            "Base",
    "A_r8_a16_lr2e4":  "Run A · r=8 α=16 lr=2e-4",
    "B_r32_a64_lr2e4": "Run B · r=32 α=64 lr=2e-4",
    "C_r8_a16_lr5e5":  "Run C · r=8 α=16 lr=5e-5",
}
RUN_ORDER = ["base", "A_r8_a16_lr2e4", "B_r32_a64_lr2e4", "C_r8_a16_lr5e5"]

BENCHMARKS = ["core_balanced", "rare_stress", "screenshot_cases"]

# heatmap cmap that matches the HTML CM gradient
CM_CMAP = LinearSegmentedColormap.from_list(
    "darkblue",
    [
        (0.00, "#14171d"),
        (0.30, "#1f2a44"),
        (0.55, "#2a3656"),
        (0.80, "#3d5fb8"),
        (1.00, "#6e90ff"),
    ],
)


def apply_dark_style():
    mpl.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor":   PANEL,
        "savefig.facecolor": BG,
        "savefig.edgecolor": BG,
        "axes.edgecolor":   LINE,
        "axes.labelcolor":  DIM,
        "axes.titlecolor":  TEXT,
        "axes.titleweight": "600",
        "axes.titlesize":   14,
        "axes.titlepad":    14,
        "axes.labelsize":   11,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.spines.left":  False,
        "axes.spines.bottom": True,
        "axes.grid":         True,
        "grid.color":        "#1c212a",
        "grid.linewidth":    0.8,
        "grid.alpha":        1.0,
        "xtick.color":       DIM,
        "ytick.color":       DIM,
        "xtick.labelsize":   9.5,
        "ytick.labelsize":   9.5,
        "xtick.major.size":  0,
        "ytick.major.size":  0,
        "text.color":        TEXT,
        "legend.facecolor":  PANEL,
        "legend.edgecolor":  LINE,
        "legend.labelcolor": TEXT,
        "legend.fontsize":   9,
        "legend.borderpad":  0.6,
        "legend.handlelength": 1.2,
        "font.family":       "DejaVu Sans",
        "figure.dpi":        140,
        "savefig.dpi":       220,
        "savefig.bbox":      "tight",
    })


def order_runs(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["run_name"].isin(RUN_ORDER)].copy()
    df["__o"] = df["run_name"].map({r: i for i, r in enumerate(RUN_ORDER)})
    df = df.sort_values("__o").drop(columns="__o")
    return df.reset_index(drop=True)


def grouped_bar(df: pd.DataFrame, metric_cols, title: str, out_path: Path, ylim=(0, 1.05)):
    df = order_runs(df)
    runs = df["run_name"].tolist()
    n_runs = len(runs)
    n_metrics = len(metric_cols)

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    x = np.arange(n_metrics)
    width = 0.78 / max(n_runs, 1)
    offset_start = -(n_runs - 1) / 2 * width

    for i, run in enumerate(runs):
        vals = [df.loc[df["run_name"] == run, m].iloc[0] for m in metric_cols]
        bars = ax.bar(
            x + offset_start + i * width,
            vals,
            width=width * 0.94,
            color=RUN_COLORS[run],
            label=RUN_LABELS[run],
            edgecolor="none",
            zorder=3,
        )
        for b, v in zip(bars, vals):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.018,
                f"{v*100:.0f}%",
                ha="center", va="bottom",
                fontsize=8, color=DIM,
            )

    ax.set_xticks(x)
    pretty = [m.replace("_", " ").replace("rate", "").replace("recall avg", "recall (avg)").strip() for m in metric_cols]
    ax.set_xticklabels(pretty, color=DIM)
    ax.set_ylim(*ylim)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_yticklabels([f"{int(t*100)}%" for t in np.arange(0, 1.01, 0.2)])
    ax.set_title(title, loc="left")
    ax.set_axisbelow(True)
    ax.grid(axis="x", visible=False)
    ax.spines["bottom"].set_color(LINE)
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=4, frameon=True)
    leg.get_frame().set_linewidth(1.0)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def confusion_plot(csv_path: Path, out_path: Path, run: str):
    df = pd.read_csv(csv_path)
    labels = df["truth"].tolist()
    cols = [c for c in df.columns if c not in ("truth", "__INVALID__")]
    values = df[cols].to_numpy()

    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    vmax = max(values.max(), 1)
    im = ax.imshow(values, cmap=CM_CMAP, vmin=0, vmax=vmax, aspect="auto")

    for r in range(values.shape[0]):
        for c in range(values.shape[1]):
            v = int(values[r, c])
            ratio = v / vmax if vmax else 0
            color = TEXT if ratio > 0.45 else (MUTE if v == 0 else DIM)
            weight = "bold" if r == c and v > 0 else "normal"
            ax.text(c, r, v, ha="center", va="center", fontsize=10, color=color, fontweight=weight)

    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([c.replace("_", "\n") for c in cols], color=DIM, fontsize=9)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels([l.replace("_", " ") for l in labels], color=DIM, fontsize=9)
    ax.set_xlabel("Predicted anomaly_type", color=DIM)
    ax.set_ylabel("True anomaly_type", color=DIM)
    title = f"{RUN_LABELS[run]}  ·  {csv_path.stem.replace('confusion_', '')}"
    ax.set_title(title, loc="left", fontsize=12)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)

    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cb.outline.set_edgecolor(LINE)
    cb.ax.yaxis.set_tick_params(color=DIM, labelcolor=DIM)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def process_benchmark(bench: str) -> None:
    bench_dir = EVAL_OUT / bench
    metrics_csv = bench_dir / "metrics_summary.csv"
    if not metrics_csv.exists():
        print(f"  ! missing {metrics_csv}")
        return
    df = pd.read_csv(metrics_csv)
    df = df[df["benchmark"] == bench].copy()

    # Schema quality
    grouped_bar(
        df,
        [
            "json_validity_rate",
            "exact_field_set_rate",
            "enum_compliance_rate",
            "full_schema_compliance_rate",
            "hallucinated_enum_rate",
        ],
        f"Schema quality — {bench}",
        OUT_DIR / f"{bench}_schema_quality.png",
    )

    # Classification quality
    grouped_bar(
        df,
        [
            "anomaly_accuracy",
            "macro_f1",
            "rare_class_recall_avg",
            "extreme_late_night_recall",
        ],
        f"Classification quality — {bench}",
        OUT_DIR / f"{bench}_classification_quality.png",
    )

    # PDP safety
    grouped_bar(
        df,
        [
            "action_accuracy",
            "severe_false_negative_rate",
            "over_action_rate",
            "under_action_rate",
        ],
        f"PDP safety — {bench}",
        OUT_DIR / f"{bench}_pdp_safety.png",
    )

    # Confusion matrices
    for run in RUN_ORDER:
        cm_csv = bench_dir / f"confusion_{bench}_{run}.csv"
        if not cm_csv.exists():
            print(f"    skip (missing) {cm_csv.name}")
            continue
        confusion_plot(cm_csv, OUT_DIR / f"confusion_{bench}_{run}.png", run)


def main() -> None:
    apply_dark_style()
    print(f"Writing figures to {OUT_DIR}")
    for bench in BENCHMARKS:
        print(f"- {bench}")
        process_benchmark(bench)
    print("Done.")


if __name__ == "__main__":
    main()
