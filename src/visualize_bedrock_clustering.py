import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

JSON_FILE = OUTPUT_DIR / "bedrock_clustering_result.json"

BEDROCK_IMAGE = OUTPUT_DIR / "bedrock_clustering_result.png"
COMPARISON_IMAGE = OUTPUT_DIR / "clustering_comparison.png"


# --------------------------------------------------
# Load Bedrock clustering result
# --------------------------------------------------

with open(JSON_FILE, encoding="utf-8-sig") as f:
    result = json.load(f)

clusters = result["clusters"]


# --------------------------------------------------
# Figure 1
# Amazon Bedrock semantic clustering
# --------------------------------------------------

fig, ax = plt.subplots(figsize=(12, 8))

ax.set_xlim(0, 12)
ax.set_ylim(0, 10)
ax.axis("off")

ax.text(
    6,
    9.3,
    "Amazon Bedrock Semantic Clustering",
    ha="center",
    va="center",
    fontsize=22,
    fontweight="bold",
)

ax.text(
    6,
    8.7,
    "Amazon Nova Micro / 30 Japanese Meeting Minutes",
    ha="center",
    va="center",
    fontsize=12,
)

positions = [
    (0.7, 4.0),
    (4.35, 4.0),
    (8.0, 4.0),
]

for cluster, (x, y) in zip(clusters, positions):

    document_ids = sorted(cluster["document_ids"])

    box = FancyBboxPatch(
        (x, y),
        3.3,
        3.2,
        boxstyle="round,pad=0.08",
        linewidth=2,
        fill=False,
    )

    ax.add_patch(box)

    ax.text(
        x + 1.65,
        y + 2.65,
        f"Cluster {cluster['cluster_id']}",
        ha="center",
        fontsize=14,
        fontweight="bold",
    )

    ax.text(
        x + 1.65,
        y + 2.05,
        cluster["cluster_name"],
        ha="center",
        fontsize=14,
    )

    ax.text(
        x + 1.65,
        y + 1.4,
        f"{len(document_ids)} documents",
        ha="center",
        fontsize=12,
    )

    ids_text = ", ".join(str(i) for i in document_ids)

    ax.text(
        x + 1.65,
        y + 0.65,
        f"IDs\n{ids_text}",
        ha="center",
        va="center",
        fontsize=9,
        wrap=True,
    )

ax.text(
    6,
    2.8,
    "No predefined categories were provided to Bedrock",
    ha="center",
    fontsize=12,
)

ax.text(
    6,
    2.3,
    "All 30 documents assigned / Missing: 0 / Duplicates: 0",
    ha="center",
    fontsize=12,
    fontweight="bold",
)

ax.text(
    6,
    1.5,
    "ARI 1.0000    |    NMI 1.0000    |    Agreement 30/30",
    ha="center",
    fontsize=15,
    fontweight="bold",
)

plt.tight_layout()

plt.savefig(
    BEDROCK_IMAGE,
    dpi=180,
    bbox_inches="tight",
)

plt.close()


# --------------------------------------------------
# Figure 2
# HDBSCAN vs Amazon Bedrock
# --------------------------------------------------

methods = [
    "TF-IDF + UMAP\n+ HDBSCAN",
    "Amazon Bedrock\nNova Micro",
]

ari = [
    0.4493,
    1.0000,
]

nmi = [
    0.6184,
    1.0000,
]

x = range(len(methods))
width = 0.32

fig, ax = plt.subplots(figsize=(10, 7))

ari_bars = ax.bar(
    [i - width / 2 for i in x],
    ari,
    width,
    label="ARI",
)

nmi_bars = ax.bar(
    [i + width / 2 for i in x],
    nmi,
    width,
    label="NMI",
)

ax.set_title(
    "Clustering Evaluation Comparison",
    fontsize=18,
    fontweight="bold",
)

ax.set_ylabel("Score")
ax.set_ylim(0, 1.15)

ax.set_xticks(list(x))
ax.set_xticklabels(methods)

ax.legend()

ax.bar_label(
    ari_bars,
    fmt="%.4f",
    padding=3,
)

ax.bar_label(
    nmi_bars,
    fmt="%.4f",
    padding=3,
)

ax.text(
    0.5,
    -0.16,
    "Evaluation dataset: 30 Japanese meeting minutes",
    transform=ax.transAxes,
    ha="center",
    fontsize=10,
)

plt.tight_layout()

plt.savefig(
    COMPARISON_IMAGE,
    dpi=180,
    bbox_inches="tight",
)

plt.close()


print("Created:")
print(BEDROCK_IMAGE)
print(COMPARISON_IMAGE)