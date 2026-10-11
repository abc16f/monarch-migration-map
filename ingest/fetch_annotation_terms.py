"""
fetch_annotation_terms.py
Downloads iNaturalist's official list of annotation questions and answers,
such as Life Stage: Larva, and saves it as a CSV lookup table that dbt loads
as a seed. Rerun it if iNaturalist adds new terms.
"""

import csv
from pathlib import Path

import requests

# Project root. Every file path in this script is built from it.
PROJECT_DIR = Path(r"C:\Users\alexa\OneDrive\Documents\Lucid Root\Monarch Mommas")
OUT_FILE = PROJECT_DIR / "dbt" / "seeds" / "inat_annotation_terms.csv"

URL = "https://api.inaturalist.org/v1/controlled_terms"
HEADERS = {"User-Agent": "MonarchMigrationMap/0.1 (Lucid Root portfolio project)"}

# Column names mirror the raw records' field names, so the join is obvious.
FIELDS = ["attribute_id", "attribute_label", "value_id", "value_label"]


def english_label(item):
    """Return the English label, whichever of the API's two formats is used."""
    if item.get("label"):
        return item["label"]
    for entry in item.get("labels", []):
        if entry.get("locale") == "en":
            return entry.get("label")
    return None


def main():
    resp = requests.get(URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    # One row per question-and-answer pair.
    rows = []
    for term in resp.json()["results"]:
        for value in term.get("values", []):
            rows.append({
                "attribute_id": term["id"],
                "attribute_label": english_label(term),
                "value_id": value["id"],
                "value_label": english_label(value),
            })
    rows.sort(key=lambda r: (r["attribute_id"], r["value_id"]))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # Print every pair so the labels can be checked against the data.
    for r in rows:
        print(f'{r["attribute_id"]:>3} {r["attribute_label"]:<25} '
              f'{r["value_id"]:>3} {r["value_label"]}')
    print(f"Saved {len(rows)} pairs to {OUT_FILE}")


if __name__ == "__main__":
    main()