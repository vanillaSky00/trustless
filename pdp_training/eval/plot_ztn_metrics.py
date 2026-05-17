#!/usr/bin/env python3
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


CANVAS = {
    "figure.figsize": (10, 5.8),
    "figure.dpi": 140,
    "savefig.dpi": 220,
    "savefig.bbox": "tight",
    "axes.titlesize": 14,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
}
plt.rcParams.update(CANVAS)

RUN_ORDER = ["base", "A_r8_a16_lr2e4", "B_r32_a64_lr2e4", "C_r8_a16_lr5e5"]
PALETTE = ["#4C78A8", "#59A14F", "#F28E2B", "#E15759", "#B07AA1"]


def ordered(df):
    present = [name for name in RUN_ORDER if name in set(df["run_name"])]
    rest = sorted(set(df["run_name"]) - set(present))
    order = present + rest
    return df.set_index("run_name").loc[order].reset_index()


def bar_plot(df, columns, title, output):
    plot_df = ordered(df)[["run_name"] + columns]
    ax = plot_df.plot(
        x="run_name",
        y=columns,
        kind="bar",
        color=PALETTE[: len(columns)],
        width=0.78,
    )
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower right")
    ax.tick_params(axis="x", rotation=20)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def plot_confusion(csv_path, output):
    df = pd.read_csv(csv_path)
    labels = df["truth"].tolist()
    values = df.drop(columns=["truth"]).to_numpy()
    columns = df.drop(columns=["truth"]).columns.tolist()

    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    image = ax.imshow(values, cmap="Blues")
    ax.set_title(csv_path.stem.replace("confusion_", "Confusion "))
    ax.set_xlabel("Predicted anomaly_type")
    ax.set_ylabel("True anomaly_type")
    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    for row_idx, row in enumerate(values):
        for col_idx, value in enumerate(row):
            ax.text(col_idx, row_idx, int(value), ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--benchmark", default="core_balanced")
    parser.add_argument("--confusion-dir", default=None)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(args.metrics)
    metrics = metrics[metrics["benchmark"] == args.benchmark].copy()
    if metrics.empty:
        raise ValueError(f"No rows found for benchmark={args.benchmark}")

    bar_plot(
        metrics,
        [
            "json_validity_rate",
            "json_object_extractable_rate",
            "full_schema_compliance_rate",
            "extractable_schema_compliance_rate",
            "hallucinated_enum_rate",
        ],
        f"Schema Quality: {args.benchmark}",
        out_dir / f"{args.benchmark}_schema_quality.png",
    )
    bar_plot(
        metrics,
        [
            "anomaly_accuracy",
            "macro_f1",
            "rare_class_recall_avg",
            "extreme_late_night_recall",
        ],
        f"Classification Quality: {args.benchmark}",
        out_dir / f"{args.benchmark}_classification_quality.png",
    )
    bar_plot(
        metrics,
        [
            "action_accuracy",
            "under_action_rate",
            "severe_false_negative_rate",
        ],
        f"PDP Safety Metrics: {args.benchmark}",
        out_dir / f"{args.benchmark}_pdp_safety.png",
    )

    confusion_dir = Path(args.confusion_dir) if args.confusion_dir else Path(args.metrics).parent
    for csv_path in sorted(confusion_dir.glob(f"confusion_{args.benchmark}_*.csv")):
        plot_confusion(csv_path, out_dir / f"{csv_path.stem}.png")

    print(f"Wrote figures to {out_dir}")


if __name__ == "__main__":
    main()
