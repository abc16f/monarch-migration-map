"""
harvest_inaturalist.py
Pulls monarch and milkweed sightings from the iNaturalist API for eastern
North America over the last 12 months, and saves each page of results as
untouched JSON. Nothing is cleaned here; cleaning happens later in dbt.
If a run stops partway, rerunning on the same day picks up where it left off.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# Project root. Every file path in this script is built from it.
PROJECT_DIR = Path(r"C:\Users\alexa\OneDrive\Documents\Lucid Root\Monarch Mommas")
RAW_DIR = PROJECT_DIR / "data" / "raw" / "inaturalist"

API = "https://api.inaturalist.org/v1"
PAUSE_SECONDS = 1.0   # stay at about one request per second
PER_PAGE = 200        # the most records the API returns per page
MAX_TRIES = 6         # attempts per request before giving up

# One shared connection, reused for every request instead of reconnecting.
# iNaturalist asks scripts to identify themselves in the User-Agent.
SESSION = requests.Session()
SESSION.headers.update(
    {"User-Agent": "MonarchMigrationMap/0.1 (Lucid Root portfolio project)"}
)

# Rough box around the eastern monarch route: central Mexico to southern
# Canada, east of the Rockies. Tighten once real sightings show the edges.
BBOX = {"swlat": 15, "swlng": -106, "nelat": 55, "nelng": -52}

# Scientific name and rank to look up for each map layer.
SUBJECTS = {
    "monarch": ("Danaus plexippus", "species"),
    "milkweed": ("Asclepias", "genus"),
}

# Network failures worth retrying: dropped connections, timeouts, SSL drops.
RETRYABLE_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.SSLError,
)


def get_json(url, params):
    """Send one request, waiting longer and retrying on busy servers or dropped connections."""
    for attempt in range(1, MAX_TRIES + 1):
        wait = PAUSE_SECONDS * 2 ** attempt
        try:
            resp = SESSION.get(url, params=params, timeout=60)
        except RETRYABLE_ERRORS as err:
            print(f"  connection problem ({type(err).__name__}), retry {attempt} in {wait:.0f}s")
            time.sleep(wait)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            print(f"  server busy ({resp.status_code}), retry {attempt} in {wait:.0f}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Gave up after {MAX_TRIES} tries: {url}")


def lookup_taxon_id(name, rank):
    """Find iNaturalist's numeric ID for an exact scientific name."""
    data = get_json(f"{API}/taxa", {"q": name, "rank": rank, "is_active": "true"})
    matches = [t for t in data["results"] if t["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one match for {name}, found {len(matches)}")
    return matches[0]["id"]


def resume_point(out_dir):
    """Count pages already saved today and find the last sighting ID in them."""
    saved = sorted(out_dir.glob("page_*.json"))
    if not saved:
        return 0, 0, 0
    total = 0
    for f in saved:
        total += len(json.loads(f.read_text(encoding="utf-8")))
    last_page = json.loads(saved[-1].read_text(encoding="utf-8"))
    return len(saved), total, last_page[-1]["id"]


def harvest(subject, taxon_id, d1, d2, run_dir):
    """Page through every sighting for one taxon, saving each page as JSON."""
    out_dir = run_dir / subject
    out_dir.mkdir(parents=True, exist_ok=True)

    page_num, total, last_id = resume_point(out_dir)
    if page_num:
        print(f"{subject}: resuming after page {page_num} ({total} sightings saved)")

    params = {
        "taxon_id": taxon_id,
        "d1": d1.isoformat(),          # earliest date observed
        "d2": d2.isoformat(),          # latest date observed
        "order_by": "id",
        "order": "asc",
        "per_page": PER_PAGE,
        "id_above": last_id,
        **BBOX,
    }

    while True:
        results = get_json(f"{API}/observations", params)["results"]
        if not results:
            break
        page_num += 1
        total += len(results)
        page_file = out_dir / f"page_{page_num:05d}.json"
        page_file.write_text(json.dumps(results), encoding="utf-8")
        print(f"{subject}: page {page_num}, {total} sightings so far")

        # Ask for the next batch after the last ID received. This gets
        # around the API's 10,000-record limit on page numbers.
        params["id_above"] = results[-1]["id"]
        if len(results) < PER_PAGE:
            break
        time.sleep(PAUSE_SECONDS)

    return {"taxon_id": taxon_id, "pages": page_num,
            "sightings": total, "max_id": params["id_above"]}


def main():
    d2 = date.today()
    d1 = d2 - timedelta(days=365)
    run_dir = RAW_DIR / f"run_date={d2.isoformat()}"

    # A manifest records what each run asked for and what came back.
    manifest = {"run_date": d2.isoformat(), "observed_from": d1.isoformat(),
                "observed_to": d2.isoformat(), "bbox": BBOX, "subjects": {}}

    for subject, (name, rank) in SUBJECTS.items():
        taxon_id = lookup_taxon_id(name, rank)
        time.sleep(PAUSE_SECONDS)
        manifest["subjects"][subject] = harvest(subject, taxon_id, d1, d2, run_dir)

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()