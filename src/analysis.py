import os
from collections import Counter, defaultdict

import hdbscan
import matplotlib.pyplot as plt
import psycopg2
import umap
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from sudachipy import dictionary, tokenizer


# =========================================================
# Configuration
# =========================================================

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": "require",
}

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================================================
# Japanese tokenizer
# =========================================================

tokenizer_obj = dictionary.Dictionary().create()
split_mode = tokenizer.Tokenizer.SplitMode.C


def tokenize_japanese(text):
    words = []

    for morpheme in tokenizer_obj.tokenize(text, split_mode):
        pos = morpheme.part_of_speech()[0]

        if pos in {"名詞", "動詞", "形容詞"}:
            word = morpheme.normalized_form()

            if len(word) > 1:
                words.append(word)

    return words


# =========================================================
# RDS
# =========================================================

def get_meeting_minutes():
    connection = psycopg2.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, meeting_date, title, content, category
                FROM meeting_minutes
                WHERE category IS NOT NULL
                ORDER BY id;
                """
            )

            return cursor.fetchall()

    finally:
        connection.close()


# =========================================================
# TF-IDF
# =========================================================

def create_tfidf(rows):
    documents = [row[3] for row in rows]

    vectorizer = TfidfVectorizer(
        tokenizer=tokenize_japanese,
        token_pattern=None,
        lowercase=False,
    )

    matrix = vectorizer.fit_transform(documents)

    print(
        f"TF-IDF matrix: "
        f"{matrix.shape[0]} documents x "
        f"{matrix.shape[1]} terms"
    )

    return vectorizer, matrix


# =========================================================
# UMAP
# =========================================================

def run_umap(tfidf_matrix):
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=5,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )

    return reducer.fit_transform(tfidf_matrix)


# =========================================================
# HDBSCAN
# =========================================================

def run_hdbscan(embedding):
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=3,
        min_samples=2,
        metric="euclidean",
    )

    return clusterer.fit_predict(embedding)


# =========================================================
# Evaluation
# =========================================================

def evaluate_clustering(rows, labels):
    true_categories = [row[4] for row in rows]

    ari = adjusted_rand_score(true_categories, labels)
    nmi = normalized_mutual_info_score(
        true_categories,
        labels
    )

    print("\n=== Clustering Evaluation ===")
    print(f"Adjusted Rand Index (ARI): {ari:.4f}")
    print(f"Normalized Mutual Information (NMI): {nmi:.4f}")

    print("\n=== Category / Cluster Comparison ===")

    comparison = defaultdict(Counter)

    for category, label in zip(true_categories, labels):
        comparison[category][label] += 1

    for category, counts in comparison.items():
        print(f"\n{category}")

        for label, count in sorted(counts.items()):
            cluster_name = (
                "Noise"
                if label == -1
                else f"Cluster {label}"
            )

            print(f"  {cluster_name}: {count}")

    return ari, nmi


# =========================================================
# Cluster keywords
# =========================================================

def show_cluster_keywords(vectorizer, tfidf_matrix, labels):
    feature_names = vectorizer.get_feature_names_out()

    print("\n=== Cluster Important Keywords ===")

    valid_clusters = sorted(
        label
        for label in set(labels)
        if label != -1
    )

    for cluster_id in valid_clusters:
        indices = [
            index
            for index, label in enumerate(labels)
            if label == cluster_id
        ]

        cluster_matrix = tfidf_matrix[indices]

        mean_scores = (
            cluster_matrix.mean(axis=0)
            .A1
        )

        ranking = sorted(
            zip(feature_names, mean_scores),
            key=lambda item: item[1],
            reverse=True,
        )[:10]

        print(f"\nCluster {cluster_id}")

        for rank, (word, score) in enumerate(
            ranking,
            start=1,
        ):
            print(
                f"{rank:2}. "
                f"{word:<15} "
                f"{score:.4f}"
            )


# =========================================================
# UMAP visualization
# =========================================================

def save_umap_plot(rows, embedding, labels):
    plt.figure(figsize=(10, 7))

    scatter = plt.scatter(
        embedding[:, 0],
        embedding[:, 1],
        c=labels,
        s=80,
    )

    for row, point in zip(rows, embedding):
        meeting_id = row[0]

        plt.annotate(
            str(meeting_id),
            (point[0], point[1]),
            fontsize=8,
        )

    plt.title("Meeting Minutes Clustering: UMAP + HDBSCAN")
    plt.xlabel("UMAP 1")
    plt.ylabel("UMAP 2")
    plt.colorbar(
        scatter,
        label="HDBSCAN Cluster"
    )

    plt.tight_layout()

    path = os.path.join(
        OUTPUT_DIR,
        "umap_clusters.png",
    )

    plt.savefig(path, dpi=150)
    plt.close()

    print(f"Saved: {path}")


# =========================================================
# TF-IDF heatmap
# =========================================================

def save_tfidf_heatmap(rows, vectorizer, tfidf_matrix):
    feature_names = vectorizer.get_feature_names_out()

    mean_scores = tfidf_matrix.mean(axis=0).A1

    top_indices = mean_scores.argsort()[-15:][::-1]
    top_terms = feature_names[top_indices]

    heatmap_data = (
        tfidf_matrix[:, top_indices]
        .toarray()
    )

    plt.figure(figsize=(12, 9))

    image = plt.imshow(
        heatmap_data,
        aspect="auto",
        interpolation="nearest",
    )

    plt.colorbar(
        image,
        label="TF-IDF Score",
    )

    plt.xticks(
        range(len(top_terms)),
        top_terms,
        rotation=45,
        ha="right",
    )

    meeting_ids = [
        f"ID {row[0]}"
        for row in rows
    ]

    plt.yticks(
        range(len(meeting_ids)),
        meeting_ids,
    )

    plt.title("TF-IDF Heatmap: Top Terms")
    plt.xlabel("Terms")
    plt.ylabel("Meeting Minutes")

    plt.tight_layout()

    path = os.path.join(
        OUTPUT_DIR,
        "tfidf_heatmap.png",
    )

    plt.savefig(path, dpi=150)
    plt.close()

    print(f"Saved: {path}")


# =========================================================
# Results
# =========================================================

def show_cluster_results(rows, embedding, labels):
    print("\n=== UMAP + HDBSCAN Results ===")

    for row, point, label in zip(
        rows,
        embedding,
        labels,
    ):
        meeting_id = row[0]
        title = row[2]
        category = row[4]

        cluster_name = (
            "Noise"
            if label == -1
            else f"Cluster {label}"
        )

        print(
            f"ID={meeting_id:<3} "
            f"{cluster_name:<10} "
            f"Category={category:<12} "
            f"UMAP=({point[0]:.3f}, {point[1]:.3f}) "
            f"Title={title}"
        )


# =========================================================
# Main
# =========================================================

def main():
    rows = get_meeting_minutes()

    print(
        f"Loaded {len(rows)} labeled meeting minutes from RDS."
    )

    if not rows:
        print("No labeled meeting minutes found.")
        return

    vectorizer, tfidf_matrix = create_tfidf(rows)

    embedding = run_umap(tfidf_matrix)

    labels = run_hdbscan(embedding)

    show_cluster_results(
        rows,
        embedding,
        labels,
    )

    evaluate_clustering(
        rows,
        labels,
    )

    show_cluster_keywords(
        vectorizer,
        tfidf_matrix,
        labels,
    )

    save_umap_plot(
        rows,
        embedding,
        labels,
    )

    save_tfidf_heatmap(
        rows,
        vectorizer,
        tfidf_matrix,
    )

    print("\n=== Analysis Complete ===")
    print("Check the output directory.")


if __name__ == "__main__":
    main()