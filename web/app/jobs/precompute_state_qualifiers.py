"""
Precompute and save the Unofficial State Qualifiers as JSON.

Reads regional results from the database, computes unofficial state qualifiers using the same logic as get_state_qualifiers,
and writes state_qualifiers_{year}_{gender}.json for the State Qualifiers page.

Run after Regional meets are scraped. From web/:
    python -m app.jobs.precompute_state_qualifiers
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))

from app import create_app, db  # noqa: E402
from app.queries import get_state_qualifiers  # noqa: E402
from app.jobs.artifacts import write_json_artifact  # noqa: E402

OUTPUT_DIR = os.path.join(WEB_DIR, 'app', 'static', 'data', 'state_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]
GENDERS = ["Boys", "Girls"]

def main():
    app = create_app()
    with app.app_context():
        for year in YEARS:
            for gender in GENDERS:
                print(f"Computing unofficial state qualifiers for {year} {gender}...")
                payload = get_state_qualifiers(gender, year)
                out_path = os.path.join(
                    OUTPUT_DIR,
                    f"state_qualifiers_{year}_{gender.lower()}.json",
                )
                write_json_artifact(out_path, payload)
                total = sum(len(e['qualifiers']) for e in payload['events'])
                print(f"  Saved: {out_path}  (events={len(payload['events'])}, rows={total})")

if __name__ == '__main__':
    main()
