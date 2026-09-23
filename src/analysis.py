import os

import psycopg2
from dotenv import load_dotenv
from sudachipy import dictionary, tokenizer
from sklearn.feature_extraction.text import TfidfVectorizer


# -----------------------------
# Environment variables
# -----------------------------

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": "require",
}


# -----------------------------
# Japanese tokenizer
# -----------------------------

tokenizer_obj = dictionary.Dictionary().create()
split_mode = tokenizer.Tokenizer.SplitMode.C


def tokenize_japanese(text):
    """
    Extract meaningful Japanese words using SudachiPy.
    """

    words = []

    for morpheme in tokenizer_obj.tokenize(text, split_mode):
        pos = morpheme.part_of_speech()[0]

        # Keep nouns, verbs and adjectives
        if pos in {"名詞", "動詞", "形容詞"}:
            normalized = morpheme.normalized_form()

            if len(normalized) > 1:
                words.append(normalized)

    return words


# -----------------------------
# Get meeting minutes from RDS
# -----------------------------

def get_meeting_minutes():
    connection = psycopg2.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, meeting_date, title, content
                FROM meeting_minutes
                ORDER BY id;
                """
            )

            return cursor.fetchall()

    finally:
        connection.close()


# -----------------------------
# TF-IDF analysis
# -----------------------------

def analyze_tfidf(rows):
    documents = [row[3] for row in rows]

    vectorizer = TfidfVectorizer(
        tokenizer=tokenize_japanese,
        token_pattern=None,
        lowercase=False,
    )

    matrix = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out()

    print("\n=== TF-IDF Keyword Ranking ===")

    for index, row in enumerate(rows):
        meeting_id = row[0]
        meeting_date = row[1]
        title = row[2]

        scores = matrix[index].toarray().flatten()

        ranking = sorted(
            zip(feature_names, scores),
            key=lambda item: item[1],
            reverse=True,
        )

        # Remove zero-score terms and keep top 10
        ranking = [
            (word, score)
            for word, score in ranking
            if score > 0
        ][:10]

        print(f"\nID: {meeting_id}")
        print(f"Date: {meeting_date}")
        print(f"Title: {title}")
        print("-" * 50)

        for rank, (word, score) in enumerate(ranking, start=1):
            print(f"{rank:2}. {word:<15} {score:.4f}")


# -----------------------------
# Main
# -----------------------------

def main():
    rows = get_meeting_minutes()

    print(f"Loaded {len(rows)} meeting minutes from RDS.")

    if not rows:
        print("No meeting minutes found.")
        return

    analyze_tfidf(rows)


if __name__ == "__main__":
    main()