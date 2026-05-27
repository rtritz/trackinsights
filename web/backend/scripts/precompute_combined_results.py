"""
Precompute and save the Combined Regional Results as JSON.

Reads ACTUAL Regional meet results (Meet.meet_type='Regional') from the
database, ranks every finisher per event across all 8 regionals, and writes
``combined_results_{year}_{gender}.json`` for the State Qualifiers page.

This is distinct from ``precompute_combined_rankings.py``, which projects
regional fields from Sectional results and writes ``combined_rankings_*``.

Run after Regional meets are scraped.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend import create_app, db  # noqa: E402
from backend.models import Athlete, AthleteResult, Meet, RelayResult, School  # noqa: E402
from backend.queries import (  # noqa: E402
    _get_event_types_map,
    _regional_events_for_gender,
    get_state_standard_display,
    meets_state_standard,
)


OUTPUT_DIR = os.path.join(WEB_DIR, 'frontend', 'static', 'data', 'regional_predictions')
os.makedirs(OUTPUT_DIR, exist_ok=True)

YEARS = [2026]
GENDERS = ["Boys", "Girls"]
FIELD_EVENTS = {"High Jump", "Long Jump", "Triple Jump", "Shot Put", "Discus", "Pole Vault"}


def _fetch_regional_event_rows(event_name: str, gender: str, year: int):
    """Return all Regional-meet finishers for an event across all 8 regionals."""
    if "Relay" in event_name:
        return (
            db.session.query(
                School.school_name.label("school_name"),
                RelayResult.school_id.label("school_id"),
                RelayResult.result.label("result"),
                RelayResult.result2.label("result2"),
                RelayResult.place.label("place"),
                Meet.meet_num.label("regional_num"),
            )
            .join(Meet, RelayResult.meet_id == Meet.meet_id)
            .join(School, RelayResult.school_id == School.school_id)
            .filter(
                Meet.meet_type == "Regional",
                Meet.year == year,
                Meet.gender == gender,
                RelayResult.event == event_name,
                RelayResult.result2.isnot(None),
                RelayResult.place.isnot(None),
            )
            .all()
        )

    return (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            AthleteResult.grade.label("grade"),
            School.school_name.label("school_name"),
            Athlete.school_id.label("school_id"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result2"),
            AthleteResult.place.label("place"),
            Meet.meet_num.label("regional_num"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(School, Athlete.school_id == School.school_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type == "Regional",
            Meet.year == year,
            Meet.gender == gender,
            AthleteResult.event == event_name,
            AthleteResult.result_type == "Final",
            AthleteResult.result2.isnot(None),
            AthleteResult.place.isnot(None),
        )
        .all()
    )


def build_payload(gender: str, year: int) -> dict:
    event_types = _get_event_types_map()
    events = _regional_events_for_gender(gender)

    events_out = []
    for event_name in events:
        event_type = event_types.get(event_name, "Track")
        is_field = event_name in FIELD_EVENTS
        is_relay = "Relay" in event_name

        rows = _fetch_regional_event_rows(event_name, gender, year)
        formatted = []
        for row in rows:
            met_standard = meets_state_standard(row.result2, gender, event_name, event_type, year=year)
            if is_relay:
                formatted.append({
                    "event": event_name,
                    "event_type": event_type,
                    "name": None,
                    "athlete_id": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "regional_num": row.regional_num,
                    "met_standard": met_standard,
                })
            else:
                name = f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", ")
                formatted.append({
                    "event": event_name,
                    "event_type": event_type,
                    "name": name,
                    "athlete_id": row.athlete_id,
                    "grade": row.grade,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "regional_num": row.regional_num,
                    "met_standard": met_standard,
                })

        def sort_key(r, is_field=is_field):
            val = r.get("result2")
            if val is None:
                return float('-inf') if is_field else float('inf')
            return val

        formatted.sort(key=sort_key, reverse=is_field)

        events_out.append({
            "event": event_name,
            "event_type": event_type,
            "standard_mark": get_state_standard_display(gender, event_name, year),
            "qualifiers": formatted,
        })

    return {
        "context": {"gender": gender, "year": year},
        "events": events_out,
    }


def main():
    app = create_app()
    with app.app_context():
        for year in YEARS:
            for gender in GENDERS:
                print(f"Computing combined regional results for {year} {gender}...")
                payload = build_payload(gender, year)
                out_path = os.path.join(
                    OUTPUT_DIR,
                    f"combined_results_{year}_{gender.lower()}.json",
                )
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                total = sum(len(e['qualifiers']) for e in payload['events'])
                print(f"  Saved: {out_path}  (events={len(payload['events'])}, rows={total})")


if __name__ == '__main__':
    main()
