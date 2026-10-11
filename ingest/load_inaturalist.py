"""
load_inaturalist.py
Loads the saved iNaturalist page files into the raw.inat_observations table.
Each sighting is inserted once. If it already exists, it is replaced only
when iNaturalist's copy is newer, so rerunning never creates duplicates.
"""

import json
from datetime import date, datetime
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb

# Project root. Every file path in this script is built from it.
PROJECT_DIR = Path(r"C:\Users\alexa\OneDrive\Documents\Lucid Root\Monarch Mommas")
RAW_DIR = PROJECT_DIR / "data" / "raw" / "inaturalist"

# Read the database password from .env, which Git ignores.
ENV = dotenv_values(PROJECT_DIR / ".env")
CONN_INFO = {
    "host": "localhost",
    "port": 5433,
    "dbname": "monarch",
    "user": "monarch",
    "password": ENV["POSTGRES_PASSWORD"],
}

# Insert each sighting, or update it only if iNaturalist's copy is newer.
UPSERT = """
INSERT INTO raw.inat_observations
    (observation_id, subject, source_updated_at, payload, run_date)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (observation_id) DO UPDATE SET
    subject           = EXCLUDED.subject,
    source_updated_at = EXCLUDED.source_updated_at,
    payload           = EXCLUDED.payload,
    run_date          = EXCLUDED.run_date,
    loaded_at         = now()
WHERE EXCLUDED.source_updated_at > raw.inat_observations.source_updated_at
"""


def latest_run_dir():
    """Find the most recent harvest folder."""
    runs = sorted(RAW_DIR.glob("run_date=*"))
    if not runs:
        raise FileNotFoundError(f"No harvest runs found in {RAW_DIR}")
    return runs[-1]


def main():
    run_dir = latest_run_dir()
    run_date = date.fromisoformat(run_dir.name.split("=", 1)[1])
    print(f"Loading {run_dir.name}")

    with psycopg.connect(**CONN_INFO) as conn:
        for subject_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
            subject = subject_dir.name
            pages = sorted(subject_dir.glob("page_*.json"))

            for i, page_file in enumerate(pages, start=1):
                records = json.loads(page_file.read_text(encoding="utf-8"))
                rows = [
                    (r["id"], subject, datetime.fromisoformat(r["updated_at"]),
                     Jsonb(r), run_date)
                    for r in records
                ]
                with conn.cursor() as cur:
                    cur.executemany(UPSERT, rows)
                conn.commit()   # save each page so a crash loses at most one page
                if i % 50 == 0 or i == len(pages):
                    print(f"{subject}: {i} of {len(pages)} pages loaded")

        # Count rows per subject to compare against the harvest manifest.
        counts = conn.execute(
            "SELECT subject, count(*) FROM raw.inat_observations "
            "GROUP BY subject ORDER BY subject"
        ).fetchall()

    for subject, n in counts:
        print(f"{subject}: {n} sightings in the table")


if __name__ == "__main__":
    main()