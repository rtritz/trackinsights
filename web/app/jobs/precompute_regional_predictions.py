"""
Precompute regional predictions for all years/genders into dashboard_cache.db.
Run this after sectional results are updated. From web/:
    python -m app.jobs.precompute_regional_predictions
"""

from app.analytics.regional_predictions import get_regional_predictions  # noqa: E402
from app.jobs.artifacts import write_artifact  # noqa: E402


YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]


def main(years=None):
    for year in years or YEARS:
        for gender in GENDERS:
            print(f"Computing regional predictions for {year} {gender}...")
            preds = get_regional_predictions(year, gender, top_n=None)
            name = f"regional_predictions_{year}_{gender.lower()}"
            write_artifact(name, preds, year=year, gender=gender)
            print(f"Stored: {name}")


if __name__ == '__main__':
    main()
