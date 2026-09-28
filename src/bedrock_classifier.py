import os
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

REGION = "ap-northeast-1"
MODEL_ID = "apac.amazon.nova-micro-v1:0"

VALID_CATEGORIES = {
    "AWS/インフラ",
    "AI/分析",
    "セキュリティ",
}

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require",
)

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=REGION
)

try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, content, category
            FROM meeting_minutes
            WHERE category IS NOT NULL
            ORDER BY id;
        """)

        rows = cur.fetchall()

        print(f"Loaded: {len(rows)} meeting minutes")

        correct = 0
        processed = 0

        for row_id, title, content, human_category in rows:

            prompt = f"""
次の日本語の会議議事録を、必ず以下の3カテゴリのうち
1つだけに分類してください。

AWS/インフラ
AI/分析
セキュリティ

ルール:
- 回答はカテゴリ名だけ
- 説明は不要
- 必ず上記3カテゴリのいずれかを回答

タイトル:
{title}

本文:
{content}
"""

            response = bedrock.converse(
                modelId=MODEL_ID,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "temperature": 0,
                    "maxTokens": 20
                }
            )

            ai_category = (
                response["output"]["message"]["content"][0]["text"]
                .strip()
            )

            if ai_category not in VALID_CATEGORIES:
                print(
                    f"ID={row_id}: INVALID -> {ai_category}"
                )
                continue

            cur.execute("""
                UPDATE meeting_minutes
                SET ai_category = %s
                WHERE id = %s;
            """, (ai_category, row_id))

            match = ai_category == human_category

            if match:
                correct += 1

            processed += 1

            print(
                f"ID={row_id:2} | "
                f"Human={human_category} | "
                f"Bedrock={ai_category} | "
                f"{'OK' if match else 'NG'}"
            )

        conn.commit()

        print("\n=== RESULT ===")
        print(f"Processed : {processed}")
        print(f"Correct   : {correct}")

        if processed:
            print(f"Accuracy  : {correct / processed:.2%}")

finally:
    conn.close()