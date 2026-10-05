import os
import json
import re

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

REGION = "ap-northeast-1"
MODEL_ID = "apac.amazon.nova-micro-v1:0"

# RDS接続
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require",
)

cur = conn.cursor()

# 正解ラベル category はBedrockに渡さない
cur.execute("""
SELECT id, title, content
FROM meeting_minutes
WHERE category IS NOT NULL
ORDER BY id;
""")

rows = cur.fetchall()

documents = [
    {
        "id": row[0],
        "title": row[1],
        "content": row[2]
    }
    for row in rows
]

print(f"Loaded: {len(documents)} meeting minutes")

documents_text = "\n\n".join(
    f"ID: {d['id']}\n"
    f"Title: {d['title']}\n"
    f"Content: {d['content']}"
    for d in documents
)

prompt = f"""
以下の日本語会議議事録を、意味・テーマ・内容の類似性に基づいて
教師なしでグループ化してください。

重要:
- 事前定義されたカテゴリはありません。
- クラスタ数も内容から判断してください。
- 各議事録は必ず1つのクラスタだけに所属させてください。
- 全IDを必ず1回ずつ使用してください。
- 各クラスタに短い日本語名を付けてください。
- 各クラスタについて簡潔な理由を付けてください。
- JSON以外は出力しないでください。

出力形式:
{{
  "clusters": [
    {{
      "cluster_id": 1,
      "cluster_name": "クラスタ名",
      "reason": "分類理由",
      "document_ids": [7, 8, 9]
    }}
  ]
}}

議事録:
{documents_text}
"""

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=REGION
)

response = bedrock.converse(
    modelId=MODEL_ID,
    messages=[
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ],
    inferenceConfig={
        "temperature": 0.0,
        "maxTokens": 4000
    }
)

result_text = response["output"]["message"]["content"][0]["text"].strip()

# Markdownコードブロック対策
result_text = re.sub(r"^```json\s*", "", result_text)
result_text = re.sub(r"^```\s*", "", result_text)
result_text = re.sub(r"\s*```$", "", result_text)

try:
    result = json.loads(result_text)
except json.JSONDecodeError:
    print("\nERROR: Bedrock returned invalid JSON")
    print(result_text)
    raise

# 全30件が1回ずつ分類されたか検証
expected_ids = {d["id"] for d in documents}
returned_ids = []

for cluster in result.get("clusters", []):
    returned_ids.extend(cluster.get("document_ids", []))

returned_set = set(returned_ids)

missing = sorted(expected_ids - returned_set)
unexpected = sorted(returned_set - expected_ids)

duplicates = sorted({
    doc_id
    for doc_id in returned_ids
    if returned_ids.count(doc_id) > 1
})

if unexpected or duplicates:
    raise ValueError(
        f"Invalid clustering result: "
        f"unexpected={unexpected}, "
        f"duplicates={duplicates}"
    )

# Bedrockが一部IDを省略した場合、そのIDだけ既存クラスタへ補完する
if missing:
    print(f"Missing IDs detected: {missing}")
    print("Requesting Bedrock to assign missing documents...")

    cluster_summary = "\n".join(
        f"Cluster {c['cluster_id']}: {c['cluster_name']} - {c['reason']}"
        for c in result["clusters"]
    )

    missing_docs = [
        d for d in documents
        if d["id"] in missing
    ]

    missing_text = "\n\n".join(
        f"ID: {d['id']}\n"
        f"Title: {d['title']}\n"
        f"Content: {d['content']}"
        for d in missing_docs
    )

    repair_prompt = f"""
すでに以下の意味ベースのクラスタが作成されています。

{cluster_summary}

最初の処理で、以下の議事録だけクラスタへの割り当てが漏れました。

{missing_text}

各議事録を、意味的に最も近い既存クラスタへ1つだけ割り当ててください。

新しいクラスタは作らないでください。
全IDを必ず1回ずつ返してください。
JSON以外は出力しないでください。

形式:
{{
  "assignments": [
    {{
      "id": 12,
      "cluster_id": 1
    }}
  ]
}}
"""

    repair_response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": repair_prompt}]
            }
        ],
        inferenceConfig={
            "temperature": 0.0,
            "maxTokens": 1000
        }
    )

    repair_text = (
        repair_response["output"]["message"]["content"][0]["text"]
        .strip()
    )

    repair_text = re.sub(r"^```json\\s*", "", repair_text)
    repair_text = re.sub(r"^```\\s*", "", repair_text)
    repair_text = re.sub(r"\\s*```$", "", repair_text)

    repair = json.loads(repair_text)

    valid_cluster_ids = {
        c["cluster_id"]
        for c in result["clusters"]
    }

    assigned_ids = []

    for assignment in repair["assignments"]:
        doc_id = assignment["id"]
        cluster_id = assignment["cluster_id"]

        if doc_id not in missing:
            raise ValueError(
                f"Unexpected repaired ID: {doc_id}"
            )

        if cluster_id not in valid_cluster_ids:
            raise ValueError(
                f"Invalid repaired cluster: {cluster_id}"
            )

        for cluster in result["clusters"]:
            if cluster["cluster_id"] == cluster_id:
                cluster["document_ids"].append(doc_id)
                assigned_ids.append(doc_id)
                break

    still_missing = sorted(
        set(missing) - set(assigned_ids)
    )

    if still_missing:
        raise ValueError(
            f"Repair failed. Still missing: {still_missing}"
        )

    print(
        f"Missing IDs successfully assigned: "
        f"{sorted(assigned_ids)}"
    )

# 結果表示
print("\n=== AMAZON BEDROCK SEMANTIC CLUSTERING ===")
print(f"Documents: {len(documents)}")
print(f"Clusters: {len(result['clusters'])}")

for cluster in result["clusters"]:
    print()
    print(
        f"Cluster {cluster['cluster_id']}: "
        f"{cluster['cluster_name']}"
    )
    print(f"Reason: {cluster['reason']}")
    print(
        "Document IDs: "
        + ", ".join(map(str, cluster["document_ids"]))
    )

# 保存
os.makedirs("output", exist_ok=True)

with open(
    "output/bedrock_clustering_result.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

with open(
    "output/bedrock_clustering_result.txt",
    "w",
    encoding="utf-8"
) as f:
    f.write("=== AMAZON BEDROCK SEMANTIC CLUSTERING ===\n")
    f.write(f"Documents: {len(documents)}\n")
    f.write(f"Clusters: {len(result['clusters'])}\n\n")

    for cluster in result["clusters"]:
        f.write(
            f"Cluster {cluster['cluster_id']}: "
            f"{cluster['cluster_name']}\n"
        )
        f.write(f"Reason: {cluster['reason']}\n")
        f.write(
            "Document IDs: "
            + ", ".join(map(str, cluster["document_ids"]))
            + "\n\n"
        )

cur.close()
conn.close()

print("\nSaved:")
print("output/bedrock_clustering_result.json")
print("output/bedrock_clustering_result.txt")