"""
Precompute the Unofficial Regional Qualifiers into dashboard_cache.db.

For the current season and each gender, this stores the page's status (which
sectionals are in, per regional) and all 8 regionals' qualifier lists as one
artifact, ``regional_qualifiers_{year}_{gender}``. The API serves from it, so
opening a regional is a lookup instead of 5-7 seconds of queries on the server.

build_all runs this. On its own, from web/:

    python -m app.jobs.precompute_regional_qualifiers
"""
from app import create_app  # noqa: E402
from app.queries import (  # noqa: E402
    current_season,
    get_regional_qualifiers,
    get_regional_qualifiers_status,
)
from app.queries.shared import REGIONAL_SECTIONAL_GROUPS  # noqa: E402
from app.jobs.artifacts import write_artifact  # noqa: E402

GENDERS = ["Boys", "Girls"]


def artifact_name(year, gender):
    return f"regional_qualifiers_{year}_{gender.lower()}"


def build_payload(gender, year):
    """{'status': <status payload>, 'regionals': {'1': <regional payload>, ...}}"""
    return {
        'status': get_regional_qualifiers_status(gender=gender, year=year),
        'regionals': {str(num): get_regional_qualifiers(gender=gender, regional_num=num, year=year)
                      for num in sorted(REGIONAL_SECTIONAL_GROUPS)},
    }


def main(years=None):
    app = create_app()
    with app.app_context():
        for year in years or [current_season()]:
            if year is None:
                print('No results in Track.db; nothing to build.')
                return
            for gender in GENDERS:
                print(f"Computing unofficial regional qualifiers for {year} {gender}...")
                payload = build_payload(gender, year)
                name = artifact_name(year, gender)
                write_artifact(name, payload, year=year, gender=gender)
                ready = payload['status'].get('ready_regionals', 0)
                print(f"  Stored: {name}  ({ready} of {len(payload['regionals'])} regionals complete)")


if __name__ == '__main__':
    main()
