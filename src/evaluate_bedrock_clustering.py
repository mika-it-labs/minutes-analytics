import os
import json
import psycopg2
from dotenv import load_dotenv
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require",
)

cur = conn.cursor()

cur.execute("""
SELECT id, category
FROM meeting_minutes
WHERE category IS NOT NULL
ORDER BY id;
""")

rows = cur.fetchall()

with open(
    "output/bedrock_clustering_result.json",
    encoding="utf-8"
) as f:
    result = json.load(f)

bedrock_cluster = {}

for cluster in result["clusters"]:
    for doc_id in cluster["document_ids"]:
        bedrock_cluster[doc_id] = cluster["cluster_id"]

category_to_label = {
    category: i
    for i, category in enumerate(
        sorted({category for _, category in rows})
    )
}

true_labels = []
predicted_labels = []

for doc_id, category in rows:
    true_labels.append(category_to_label[category])
    predicted_labels.append(bedrock_cluster[doc_id])

ari = adjusted_rand_score(
    true_labels,
    predicted_labels
)

nmi = normalized_mutual_info_score(
    true_labels,
    predicted_labels
)

correct = 0

for cluster in result["clusters"]:
    cluster_ids = set(cluster["document_ids"])

    categories = [
        category
        for doc_id, category in rows
        if doc_id in cluster_ids
    ]

    majority = max(
        set(categories),
        key=categories.count
    )

    correct += categories.count(majority)

accuracy = correct / len(rows)

print("=== BEDROCK CLUSTERING EVALUATION ===")
print(f"Documents : {len(rows)}")
print(f"Clusters  : {len(result['clusters'])}")
print(f"ARI       : {ari:.4f}")
print(f"NMI       : {nmi:.4f}")
print(f"Agreement : {correct}/{len(rows)} ({accuracy:.2%})")

with open(
    "output/bedrock_clustering_evaluation.txt",
    "w",
    encoding="utf-8"
) as f:
    f.write("=== BEDROCK CLUSTERING EVALUATION ===\n")
    f.write(f"Documents : {len(rows)}\n")
    f.write(f"Clusters  : {len(result['clusters'])}\n")
    f.write(f"ARI       : {ari:.4f}\n")
    f.write(f"NMI       : {nmi:.4f}\n")
    f.write(
        f"Agreement : {correct}/{len(rows)} "
        f"({accuracy:.2%})\n"
    )

cur.close()
conn.close()