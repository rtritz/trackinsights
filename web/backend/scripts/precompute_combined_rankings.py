"""
Precompute and save the Combined Regional Rankings as JSON.

For each (year, gender), this assembles the unofficial regional qualifier list
from all 8 regionals into a single per-event ranked list (best-to-worst),
de-duplicates by athlete/school, and writes the result to a JSON file the API
can serve quickly without hitting the database.

Run this after sectional results are updated.
"""
import os
import sys
import json

# Ensure 'backend' is importable when running this script directly
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend import create_app  # noqa: E402
from backend.queries import get_regional_qualifiers  # noqa: E402


OUTPUT_DIR = os.path.join(WEB_DIR, 'frontend', 'static', 'data', 'regional_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]
GENDERS = ["Boys", "Girls"]
FIELD_EVENTS = {"High Jump", "Long Jump", "Triple Jump", "Shot Put", "Discus", "Pole Vault"}


def build_combined_payload(gender: str, year: int) -> dict:
    combined: dict[str, list[dict]] = {}
    event_meta: dict[str, dict] = {}

    for regional_num in range(1, 9):
        try:
            payload = get_regional_qualifiers(gender=gender, regional_num=regional_num, year=year)
        except Exception as exc:
            print(f"  WARN regional {regional_num}: {exc}")
            continue
        for event_block in payload.get('events', []):
            event_name = event_block.get('event')
            if not event_name:
                continue
            if event_name not in combined:
                combined[event_name] = []
                event_meta[event_name] = {
                    'event': event_name,
                    'event_type': event_block.get('event_type'),
                    'standard_mark': event_block.get('standard_mark'),
                }
            for row in event_block.get('qualifiers', []):
                if row.get('is_placeholder'):
                    continue
                enriched = dict(row)
                enriched['regional_num'] = regional_num
                combined[event_name].append(enriched)

    events_out = []
    for event_name, rows in combined.items():
        is_field = event_name in FIELD_EVENTS

        def sort_key(r, is_field=is_field):
            val = r.get('result2')
            if val is None:
                return float('-inf') if is_field else float('inf')
            return val

        sorted_rows = sorted(rows, key=sort_key, reverse=is_field)
        seen = set()
        unique_rows = []
        for r in sorted_rows:
            key = (r.get('name') or r.get('school'), r.get('school'))
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(r)

        meta = event_meta[event_name]
        events_out.append({
            'event': event_name,
            'event_type': meta.get('event_type'),
            'standard_mark': meta.get('standard_mark'),
            'qualifiers': unique_rows,
        })

    return {
        'context': {'gender': gender, 'year': year},
        'events': events_out,
    }


def main():
    app = create_app()
    with app.app_context():
        for year in YEARS:
            for gender in GENDERS:
                print(f"Computing combined regional rankings for {year} {gender}...")
                # Bypass lru_cache so we always recompute against fresh DB state.
                target = get_regional_qualifiers
                if hasattr(target, 'cache_clear'):
                    target.cache_clear()

                payload = build_combined_payload(gender, year)
                out_path = os.path.join(
                    OUTPUT_DIR,
                    f"combined_rankings_{year}_{gender.lower()}.json",
                )
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                print(f"  Saved: {out_path}  (events={len(payload['events'])})")


if __name__ == '__main__':
    main()
