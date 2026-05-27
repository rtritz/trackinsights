"""
Precompute and save state predictions for all years/genders as JSON.
Run this after regional results are updated.
"""
import os
import json
from state_predictions import get_state_predictions

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '../../frontend/static/data/state_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]

for year in YEARS:
    for gender in GENDERS:
        print(f"Computing state predictions for {year} {gender}...")
        preds = get_state_predictions(year, gender, top_n=None)
        out_path = os.path.join(OUTPUT_DIR, f"state_predictions_{year}_{gender.lower()}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(preds, f, indent=2)
        print(f"Saved: {out_path}  (ready={preds['ready']}, regionals_loaded={preds['regionals_loaded']})")
