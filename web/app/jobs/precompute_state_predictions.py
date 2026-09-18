"""
Precompute and save state predictions for all years/genders as JSON.
Run this after regional results are updated. From web/:
    python -m app.jobs.precompute_state_predictions
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from app.analytics.state_predictions import get_state_predictions  # noqa: E402

OUTPUT_DIR = os.path.join(WEB_DIR, 'app', 'static', 'data', 'state_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]  # Add more years as needed
GENDERS = ["Boys", "Girls"]


def main():
    for year in YEARS:
        for gender in GENDERS:
            print(f"Computing state predictions for {year} {gender}...")
            preds = get_state_predictions(year, gender, top_n=None)
            out_path = os.path.join(OUTPUT_DIR, f"state_predictions_{year}_{gender.lower()}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(preds, f, indent=2)
            print(f"Saved: {out_path}  (ready={preds['ready']}, regionals_loaded={preds['regionals_loaded']})")


if __name__ == '__main__':
    main()
