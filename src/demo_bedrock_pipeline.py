
import os
import sys
import json
from pathlib import Path
from collections import Counter

import boto3
import numpy as np
import psycopg2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from matplotlib import font_manager
from scipy.stats import gaussian_kde
from sklearn.feature_extraction.text import TfidfVectorizer
from sudachipy import dictionary, tokenizer
import umap
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

config = dotenv_values(ROOT / ".env.local")

MODEL_ID = "apac.amazon.nova-micro-v1:0"
CATEGORIES = ["AWS/インフラ", "AI/分析", "セキュリティ"]
PREFIX = "[DEMO2026] "

# 完全に架空の議事録
DEMO = {
    "AWS/インフラ": [
        ("VPCネットワーク設計", "VPCのCIDRとパブリックサブネット、プライベートサブネット、ルートテーブルの設計を検討した。"),
        ("EC2サーバー構築", "Amazon EC2とAmazon Linuxを利用したWebサーバー構築、インスタンスタイプの選定を協議した。"),
        ("RDSデータベース", "Amazon RDS for PostgreSQLのバックアップ、DBサブネットグループ、ストレージ設計を確認した。"),
        ("ALB負荷分散", "Application Load Balancerのターゲットグループとヘルスチェックを検討した。"),
        ("Terraform構成管理", "TerraformによるVPCとEC2のコード管理、planとapplyの運用を確認した。"),
        ("S3ストレージ", "Amazon S3のバージョニング、ストレージクラス、ライフサイクル管理を協議した。"),
        ("CloudWatch監視", "Amazon CloudWatchによるEC2のCPU監視とアラーム設定を検討した。"),
        ("Auto Scaling", "EC2 Auto Scalingの起動テンプレートとスケーリングポリシーを設計した。"),
        ("VPC Peering", "異なるVPC間のプライベート通信とルートテーブル設定を確認した。"),
        ("ECSコンテナ構築", "Amazon ECSとDockerを利用したコンテナ基盤、タスク定義とデプロイ方法を検討した。"),
    ],
    "AI/分析": [
        ("自然言語処理", "SudachiPyによる日本語形態素解析と名詞抽出の方法を検討した。"),
        ("TF-IDF分析", "TF-IDFによる文書ベクトル化と単語の重要度分析を実施した。"),
        ("UMAP可視化", "UMAPによる高次元文章ベクトルの二次元圧縮と可視化を検討した。"),
        ("HDBSCAN分析", "HDBSCANによる教師なしクラスタリングとノイズ点の扱いを確認した。"),
        ("LLM自動分類", "大規模言語モデルによる議事録のカテゴリ分類とプロンプト設計を検討した。"),
        ("RAG文書検索", "RAGを利用して関連文書を検索し、検索結果に基づく回答を生成する仕組みを協議した。"),
        ("Pythonデータ分析", "Pythonとpandasでデータを集計し、Matplotlibで分析結果を可視化した。"),
        ("AIモデル評価", "分類モデルのAccuracy、Precision、Recall、F1スコアによる評価を検討した。"),
        ("Embedding検索", "文章Embeddingとコサイン類似度による意味検索を検討した。"),
        ("AIエージェント", "AIエージェントによる外部ツール呼び出しと分析ワークフローを設計した。"),
    ],
    "セキュリティ": [
        ("IAM最小権限", "IAMロールとポリシーを利用した最小権限アクセス制御を協議した。"),
        ("KMS暗号化", "AWS KMSによる暗号鍵管理とTLS通信によるデータ保護を確認した。"),
        ("CloudTrail監査", "AWS CloudTrailによるAPI操作履歴の記録と監査証跡の管理を検討した。"),
        ("脆弱性管理", "サーバーの脆弱性検出と優先順位に応じた修正運用を協議した。"),
        ("セキュリティグループ", "EC2へのアクセスを必要な送信元とポートだけに制限する方法を検討した。"),
        ("AWS WAF", "AWS WAFによるSQLインジェクションと不正HTTPリクエスト対策を確認した。"),
        ("多要素認証", "管理者アカウントへの多要素認証導入と不正ログイン防止策を検討した。"),
        ("インシデント対応", "不正アクセスの検知、初動対応、証拠保全、復旧手順を整理した。"),
        ("GuardDuty検知", "Amazon GuardDutyによる脅威検知と不審なAPI操作の調査を協議した。"),
        ("Secrets Manager", "AWS Secrets Managerによるデータベース認証情報の安全な保管を検討した。"),
    ],
}


def connect_db():
    return psycopg2.connect(
        host=config["DB_HOST"],
        port=int(config["DB_PORT"]),
        dbname=config["DB_NAME"],
        user=config["DB_USER"],
        password=config["DB_PASSWORD"],
        connect_timeout=10,
    )


def get_demo_rows(cur):
    cur.execute("""
        SELECT id, title, content, category, ai_category
        FROM meeting_minutes
        WHERE left(title, %s) = %s
        ORDER BY id
    """, (len(PREFIX), PREFIX))
    return cur.fetchall()


def seed(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE meeting_minutes
                ADD COLUMN IF NOT EXISTS ai_category VARCHAR(50)
            """)

            rows = get_demo_rows(cur)

            if rows:
                if len(rows) != 30:
                    raise RuntimeError(
                        f"既存のDEMO2026データが{len(rows)}件あります。"
                        "安全のため追加を中止します。"
                    )
                print("既存のダミー30件を使用します")
                return

            from datetime import date, timedelta

            index = 0
            for category, items in DEMO.items():
                for title, content in items:
                    cur.execute("""
                        INSERT INTO meeting_minutes
                        (meeting_date, title, content, category, ai_category)
                        VALUES (%s, %s, %s, %s, NULL)
                    """, (
                        date(2026, 9, 1) + timedelta(days=index),
                        PREFIX + title,
                        content,
                        category,
                    ))
                    index += 1

            print(f"RDSにダミー{index}件を登録しました")


def classify(bedrock, title, content):
    prompt = f"""以下は架空の会議議事録です。
最も適切なカテゴリを次の3つから1つだけ選んでください。

AWS/インフラ
AI/分析
セキュリティ

回答はカテゴリ名のみとしてください。

タイトル: {title}
本文: {content}
"""

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {"role": "user", "content": [{"text": prompt}]}
        ],
        inferenceConfig={
            "temperature": 0.0,
            "maxTokens": 100,
        },
    )

    answer = "".join(
        part.get("text", "")
        for part in response["output"]["message"]["content"]
    ).strip()

    if answer in CATEGORIES:
        return answer

    matches = [c for c in CATEGORIES if c in answer]

    if len(matches) == 1:
        return matches[0]

    raise ValueError(f"不正な分類結果: {answer}")


def run_classification(conn):
    session = boto3.Session(
        profile_name=config["AWS_PROFILE"],
        region_name=config["AWS_REGION"],
    )
    bedrock = session.client("bedrock-runtime")

    with conn.cursor() as cur:
        rows = get_demo_rows(cur)

    if len(rows) != 30:
        raise RuntimeError("ダミーデータが30件ではありません")

    for doc_id, title, content, actual, predicted in rows:
        if predicted in CATEGORIES:
            print(f"ID {doc_id}: 既存の分類結果を使用")
            continue

        prediction = classify(bedrock, title, content)

        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE meeting_minutes
                    SET ai_category = %s
                    WHERE id = %s
                """, (prediction, doc_id))

        print(f"ID {doc_id}: {prediction}")

    print("Bedrock分類完了")


def visualize(conn):
    with conn.cursor() as cur:
        rows = get_demo_rows(cur)

    if len(rows) != 30:
        raise RuntimeError("議事録が30件ではありません")

    if any(r[4] not in CATEGORIES for r in rows):
        raise RuntimeError("未分類の議事録があります")

    texts = [r[1] + " " + r[2] for r in rows]
    actual = [r[3] for r in rows]
    predicted = [r[4] for r in rows]

    correct = sum(
        a == p for a, p in zip(actual, predicted)
    )
    accuracy = correct / len(rows) * 100
    counts = Counter(predicted)

    sudachi = dictionary.Dictionary().create()
    mode = tokenizer.Tokenizer.SplitMode.C

    def tokenize(text):
        return [
            m.normalized_form()
            for m in sudachi.tokenize(text, mode)
            if m.part_of_speech()[0]
            in ("名詞", "動詞", "形容詞")
            and len(m.normalized_form()) > 1
        ]

    vectorizer = TfidfVectorizer(
        tokenizer=tokenize,
        token_pattern=None,
        lowercase=False,
    )
    matrix = vectorizer.fit_transform(texts)

    coords = umap.UMAP(
        n_components=2,
        n_neighbors=8,
        min_dist=0.3,
        metric="cosine",
        random_state=42,
    ).fit_transform(matrix)

    for font in ["Yu Gothic", "Meiryo", "MS Gothic"]:
        if any(
            f.name == font
            for f in font_manager.fontManager.ttflist
        ):
            plt.rcParams["font.family"] = font
            break

    plt.rcParams["axes.unicode_minus"] = False

    colors = {
        "AWS/インフラ": "#2780C2",
        "AI/分析": "#29A354",
        "セキュリティ": "#EF8933",
    }

    fig = plt.figure(figsize=(16, 9), facecolor="white")

    fig.text(
        0.055, 0.91,
        "最終結果：議事録カテゴリマップ",
        fontsize=26,
        color="#192554",
        fontweight="bold",
    )

    fig.text(
        0.055, 0.85,
        "ダミー議事録30件 → Amazon Bedrock / Nova Microで自動分類",
        fontsize=15,
        color="#6B7280",
    )

    ax = fig.add_axes([0.07, 0.16, 0.59, 0.61])

    x, y = coords[:, 0], coords[:, 1]

    # データ密度の等高線
    if np.linalg.matrix_rank(np.cov(coords.T)) == 2:
        xx, yy = np.mgrid[
            x.min()-1:x.max()+1:160j,
            y.min()-1:y.max()+1:160j,
        ]

        kde = gaussian_kde(np.vstack([x, y]))
        z = kde(
            np.vstack([xx.ravel(), yy.ravel()])
        ).reshape(xx.shape)

        ax.contourf(
            xx, yy, z,
            levels=12,
            cmap="Greys",
            alpha=0.30,
        )
        ax.contour(
            xx, yy, z,
            levels=12,
            colors="gray",
            linewidths=0.4,
            alpha=0.3,
        )

    for category in CATEGORIES:
        mask = np.array([p == category for p in predicted])

        ax.scatter(
            x[mask],
            y[mask],
            s=95,
            color=colors[category],
            edgecolors="white",
            linewidths=1,
            label=category,
            zorder=3,
        )

    ax.set_title("技術情報マップ（TF-IDF + UMAP）")
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.legend(loc="best", fontsize=10)

    panel = fig.add_axes([0.70, 0.16, 0.27, 0.61])
    panel.set_facecolor("#F2F5F9")
    panel.set_xticks([])
    panel.set_yticks([])

    panel.text(
        0.08, 0.88,
        "読み方",
        fontsize=21,
        color="#192554",
        fontweight="bold",
        transform=panel.transAxes,
    )

    panel.text(
        0.08, 0.74,
        "点1つ ＝ 議事録1件",
        fontsize=14,
        transform=panel.transAxes,
    )

    panel.text(
        0.08, 0.61,
        "色分け ＝ Nova Microの分類",
        fontsize=12,
        transform=panel.transAxes,
    )

    for i, category in enumerate(CATEGORIES):
        panel.text(
            0.10, 0.49 - i * 0.09,
            f"● {category}：{counts[category]}件",
            color=colors[category],
            fontsize=12,
            transform=panel.transAxes,
        )

    panel.text(
        0.08, 0.17,
        "等高線 ＝ データ密度",
        fontsize=13,
        transform=panel.transAxes,
    )

    panel.text(
        0.08, 0.08,
        f"Accuracy：{accuracy:.2f}%",
        fontsize=18,
        color="#192554",
        fontweight="bold",
        transform=panel.transAxes,
    )

    fig.text(
        0.055, 0.07,
        "点の位置：TF-IDF + UMAP ｜ 色：Nova Microの予測カテゴリ",
        fontsize=11,
        color="#6B7280",
    )

    image_path = OUTPUT / "bedrock_classification_map.png"
    fig.savefig(image_path, dpi=180, facecolor="white")
    plt.close(fig)

    report = (
        "Amazon Bedrock / Nova Micro\n"
        "Dataset: Synthetic meeting minutes\n"
        f"Documents: {len(rows)}\n"
        f"Correct: {correct}\n"
        f"Incorrect: {len(rows)-correct}\n"
        f"Accuracy: {accuracy:.2f}%\n"
    )

    (OUTPUT / "demo_classification_evaluation.txt").write_text(
        report, encoding="utf-8"
    )

    print(report)
    print("画像生成:", image_path)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {
        "seed", "classify", "visualize", "all"
    }:
        print(
            "使い方: python src/demo_bedrock_pipeline.py "
            "seed|classify|visualize|all"
        )
        sys.exit(1)

    conn = connect_db()

    try:
        action = sys.argv[1]

        if action in ("seed", "all"):
            seed(conn)

        if action in ("classify", "all"):
            run_classification(conn)

        if action in ("visualize", "all"):
            visualize(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
