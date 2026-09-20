"""
Precompute and save regional predictions for all years/genders as JSON.
Run this after sectional results are updated. From web/:
    python -m app.jobs.precompute_regional_predictions
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))

from app.analytics.regional_predictions import get_regional_predictions  # noqa: E402
from app.jobs.artifacts import write_json_artifact  # noqa: E402

OUTPUT_DIR = os.path.join(WEB_DIR, 'app', 'static', 'data', 'regional_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]


def main():
    for year in YEARS:
        for gender in GENDERS:
            print(f"Computing regional predictions for {year} {gender}...")
            preds = get_regional_predictions(year, gender, top_n=None)
            out_path = os.path.join(OUTPUT_DIR, f"regional_predictions_{year}_{gender.lower()}.json")
            write_json_artifact(out_path, preds, year=year, gender=gender)
            print(f"Saved: {out_path}")


if __name__ == '__main__':
    main()
