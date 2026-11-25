"""
Precompute the Unofficial State Qualifiers into dashboard_cache.db.

Reads regional results from the database, computes unofficial state qualifiers using the same logic as get_state_qualifiers,
and stores the artifact state_qualifiers_{year}_{gender} for the State Qualifiers page.

Run after Regional meets are scraped. From web/:
    python -m app.jobs.precompute_state_qualifiers
"""

from app import create_app, db  # noqa: E402
from app.queries import current_season, get_state_qualifiers  # noqa: E402
from app.jobs.artifacts import write_artifact  # noqa: E402


GENDERS = ["Boys", "Girls"]

def main(years=None):
    app = create_app()
    with app.app_context():
        for year in years or [current_season()]:
            for gender in GENDERS:
                print(f"Computing unofficial state qualifiers for {year} {gender}...")
                payload = get_state_qualifiers(gender, year)
                name = f"state_qualifiers_{year}_{gender.lower()}"
                write_artifact(name, payload, year=year, gender=gender)
                total = sum(len(e['qualifiers']) for e in payload['events'])
                print(f"  Stored: {name}  (events={len(payload['events'])}, rows={total})")

if __name__ == '__main__':
    main()
