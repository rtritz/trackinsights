"""
Precompute and save regional predictions for all years/genders as JSON.
Run this after sectional results are updated. From web/:
    python -m backend.jobs.precompute_regional_predictions
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend.analytics.regional_predictions import get_regional_predictions  # noqa: E402

OUTPUT_DIR = os.path.join(WEB_DIR, 'frontend', 'static', 'data', 'regional_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]


def main():
    for year in YEARS:
        for gender in GENDERS:
            print(f"Computing regional predictions for {year} {gender}...")
            preds = get_regional_predictions(year, gender, top_n=None)
            out_path = os.path.join(OUTPUT_DIR, f"regional_predictions_{year}_{gender.lower()}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(preds, f, indent=2)
            print(f"Saved: {out_path}")


if __name__ == '__main__':
    main()
