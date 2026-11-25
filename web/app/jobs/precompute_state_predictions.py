"""
Precompute state predictions for all years/genders into dashboard_cache.db.
Run this after regional results are updated. From web/:
    python -m app.jobs.precompute_state_predictions
"""

from app.analytics.state_predictions import get_state_predictions  # noqa: E402
from app.jobs.artifacts import write_artifact  # noqa: E402


YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]


def main(years=None):
    for year in years or YEARS:
        for gender in GENDERS:
            print(f"Computing state predictions for {year} {gender}...")
            preds = get_state_predictions(year, gender, top_n=None)
            name = f"state_predictions_{year}_{gender.lower()}"
            write_artifact(name, preds, year=year, gender=gender)
            print(f"Stored: {name}  (ready={preds['ready']}, regionals_loaded={preds['regionals_loaded']})")


if __name__ == '__main__':
    main()
