import os

import psycopg2
from dotenv import load_dotenv


load_dotenv()

connection = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    sslmode="require",
)

cursor = connection.cursor()

cursor.execute("""
    SELECT id, meeting_date, title, content
    FROM meeting_minutes
    ORDER BY id;
""")

rows = cursor.fetchall()

print("=== Meeting Minutes ===")

for row in rows:
    print(f"ID: {row[0]}")
    print(f"Date: {row[1]}")
    print(f"Title: {row[2]}")
    print(f"Content: {row[3]}")
    print("-" * 40)

cursor.close()
connection.close()