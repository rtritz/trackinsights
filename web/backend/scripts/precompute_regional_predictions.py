"""
Precompute and save regional predictions for all years/genders as JSON.
Run this after sectional results are updated.
"""
import os
import json
from regional_predictions import get_regional_predictions

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '../../frontend/static/data/regional_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]

for year in YEARS:
    for gender in GENDERS:
        print(f"Computing regional predictions for {year} {gender}...")
        preds = get_regional_predictions(year, gender, top_n=None)
        out_path = os.path.join(OUTPUT_DIR, f"regional_predictions_{year}_{gender.lower()}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(preds, f, indent=2)
        print(f"Saved: {out_path}")
