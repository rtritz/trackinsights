"""Meets

Meet results, team scoring, relays and per-stage rows.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Any,
    Athlete,
    AthleteResult,
    CONST,
    Dict,
    Event,
    List,
    MIN_RECORDS_YEAR,
    Meet,
    Optional,
    Path,
    RelayResult,
    School,
    Tuple,
    _H2H_INDIVIDUAL_POINTS,
    _H2H_RELAY_POINTS,
    _PLACE_POINTS,
    _RELAY_NAME_DELIMITER,
    _STATE_PLACE_POINTS,
    _STAGE_ORDER,
    db,
    func,
    lru_cache,
    re,
)

from .shared import (
    _choose_result_entry,
    _count_result_types,
    _format_place_label,
    _format_result_display,
    _format_sectional_name,
    _is_lower_better,
    _is_valid_postseason_mark,
    _normalize_name_text,
    _normalize_performance_input,
    _ordinal,
    _project_place,
    _safe_int,
    _is_better,
)



@lru_cache(maxsize=1)
def _available_meet_years(limit: int = 30):
    db_path = Path(getattr(CONST, "DB_PATH", "")).expanduser()
    if not db_path.exists():
        return []

    import sqlite3

    query = "SELECT DISTINCT year FROM meet WHERE year IS NOT NULL ORDER BY year DESC LIMIT ?"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [int(row[0]) for row in rows if row and row[0] is not None]

def _compute_stage_badge(stage_name, results, placer_threshold):
    if not results:
        return None

    qualifier_count = 0
    placer_count = 0

    for res, _meet in results:
        qualifier_count += 1
        if res.place is not None and res.place > 0 and res.place <= placer_threshold:
            placer_count += 1

    payload = None
    if placer_count:
        count_prefix = f"{placer_count} x " if placer_count > 1 else ""
        payload = {
            "stage": stage_name,
            "achievement": "Placer",
            "count": placer_count,
            "label": f"{count_prefix}{stage_name} Placer",
        }
    elif qualifier_count:
        count_prefix = f"{qualifier_count} x " if qualifier_count > 1 else ""
        payload = {
            "stage": stage_name,
            "achievement": "Qualifier",
            "count": qualifier_count,
            "label": f"{count_prefix}{stage_name} Qualifier",
        }

    if not payload:
        return None

    payload["qualifier_count"] = qualifier_count
    payload["placer_count"] = placer_count
    payload["entries"] = _serialize_stage_entries(results)
    return payload

def _serialize_stage_entries(results):
    serialized = []
    for res, meet in results:
        place_value = res.place if (res.place is not None and res.place > 0) else None
        serialized.append(
            {
                "event": res.event,
                "result": res.result,
                "place": place_value,
                "place_label": _format_place_label(place_value) if place_value else None,
                "meet_id": getattr(res, "meet_id", None),
                "meet_type": meet.meet_type,
                "year": meet.year,
                "meet_host": meet.host,
                "result_type": getattr(res, "result_type", "Final"),
                "is_relay": isinstance(res, RelayResult),
            }
        )

    serialized.sort(key=lambda entry: (entry["year"] or 0, entry["event"] or ""), reverse=True)
    return serialized

def _serialize_history_stage(stage_entry, meet_type, event_name):
    if not stage_entry:
        return None

    is_relay = stage_entry.get("source") == "RelayResult"
    meet_id = stage_entry.get("meet_id")
    result_type = stage_entry.get("result_type")

    return {
        "text": stage_entry.get("formatted") or "–",
        "result": stage_entry.get("result"),
        "result_value": stage_entry.get("result_value"),
        "place": stage_entry.get("place"),
        "result_type": result_type,
        "meet_id": meet_id,
        "event": event_name,
        "meet_type": meet_type,
        "has_detail": bool(meet_id and result_type),
        "is_relay": is_relay,
    }

def _extract_relay_names(names_blob: str):
    if not names_blob:
        return []

    pieces = _RELAY_NAME_DELIMITER.split(names_blob)
    normalized = []
    for piece in pieces:
        value = _normalize_name_text(piece)
        if value:
            normalized.append(value)
    return normalized

def _format_stage_result(result_value, place):
    if place is None or place <= 0:
        return result_value or "–"

    place_str = _ordinal(place)
    if result_value:
        return f"{result_value} ({place_str})"
    return place_str

def _estimate_relay_rank(
    event_name: str,
    performance_value,
    *,
    gender: str,
    year: int,
    meet_type: str = "Sectional",
    event_type: Optional[str] = None,
):
    event_type_value = event_type
    if not event_type_value:
        event = Event.query.filter_by(event=event_name).one_or_none()
        if not event or not event.event_type:
            return None
        event_type_value = event.event_type

    normalized_value = _normalize_performance_input(performance_value, event_type_value)

    gender_filter = func.lower(Meet.gender) == (gender or "").strip().lower()
    raw_results = (
        db.session.query(
            RelayResult.school_id.label("team_id"),
            RelayResult.meet_id.label("meet_id"),
            RelayResult.result2.label("result_value"),
            RelayResult.result.label("result_text"),
            RelayResult.place.label("place"),
            RelayResult.athlete_names.label("athlete_names"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.event == event_name,
            RelayResult.result2.isnot(None),
            Meet.meet_type == meet_type,
            gender_filter,
            Meet.year == year,
        )
    ).all()

    if not raw_results:
        return None

    lower_is_better = _is_lower_better(event_type_value)
    per_meet = {}
    for row in raw_results:
        meet_entry = per_meet.setdefault(
            row.meet_id,
            {
                "meet_id": row.meet_id,
                "host": row.meet_host,
                "meet_num": row.meet_num,
                "results": {},
            },
        )
        team_bucket = meet_entry["results"]
        candidate = {
            "athlete_id": row.team_id,
            "result_value": row.result_value,
            "result_text": row.result_text,
            "result_type": "Final",
            "place": row.place,
        }
        team_bucket[row.team_id] = _choose_result_entry(
            team_bucket.get(row.team_id), candidate, lower_is_better
        )

    sectional_results = []
    all_result_values = []
    for meet_data in per_meet.values():
        entries = list(meet_data["results"].values())
        if not entries:
            continue
        values = sorted(
            (entry["result_value"] for entry in entries),
            reverse=not lower_is_better,
        )
        all_result_values.extend(values)
        raw_place = _project_place(values, normalized_value, event_type_value, event_name)
        numeric_place = _safe_int(raw_place)
        sectional_results.append(
            {
                "meet_id": meet_data["meet_id"],
                "meet_num": meet_data["meet_num"],
                "sectional_name": _format_sectional_name(meet_data["host"], meet_data["meet_num"]),
                "projected_place": numeric_place,
                "projected_place_label": _format_place_label(raw_place),
                "field_size": len(values),
                "result_type_counts": _count_result_types(entries),
            }
        )

    if not sectional_results:
        return None

    sectional_results.sort(
        key=lambda item: (
            item["meet_num"] if item.get("meet_num") is not None else float("inf"),
            item.get("sectional_name") or "",
        )
    )

    all_values_sorted = sorted(all_result_values, reverse=not lower_is_better)
    raw_overall_place = _project_place(all_values_sorted, normalized_value, event_type_value, event_name)

    return {
        "event": event_name,
        "event_type": event_type_value,
        "gender": gender,
        "year": year,
        "meet_type": meet_type,
        "comparison_count": len(all_values_sorted),
        "projected_place": raw_overall_place,
        "projected_place_label": _format_place_label(raw_overall_place),
        "input_value": normalized_value,
        "sectional_results": sectional_results,
    }

def _compute_school_relay_results(school_id: int):
    """Return school relay performances for dashboard display."""
    rows = (
        db.session.query(
            RelayResult.event,
            RelayResult.result,
            RelayResult.result2,
            RelayResult.place,
            RelayResult.athlete_names,
            Meet.meet_id,
            Meet.host,
            Meet.meet_type,
            Meet.meet_num,
            Meet.gender,
            Meet.year,
            Event.event_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .all()
    )

    statewide_rows = (
        db.session.query(
            RelayResult.event,
            Meet.gender,
            Meet.year,
            Meet.meet_type,
            RelayResult.school_id,
            RelayResult.result2,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.result2.isnot(None),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .all()
    )

    # Dedupe by school within each (event, gender, year, meet_type) bucket:
    # keep each school's best (lowest time) mark at that meet level so
    # ranking reflects teams that competed at that level, not raw
    # performance counts. Each row on the dashboard is ranked against the
    # pool of teams that ran the event at the same meet_type that year.
    best_by_school = {}
    for item in statewide_rows:
        key = (item.event, item.gender, item.year, item.meet_type, item.school_id)
        existing = best_by_school.get(key)
        if existing is None or item.result2 < existing:
            best_by_school[key] = item.result2

    statewide_marks = {}
    for (event, gender, year, meet_type, _sid), mark in best_by_school.items():
        statewide_marks.setdefault((event, gender, year, meet_type), []).append(mark)

    meet_order = {"Sectional": 1, "Regional": 2, "State": 3}
    results = []
    for row in rows:
        event_type = row.event_type or "Relay"
        lineup = _extract_relay_names(row.athlete_names or "")
        marks = statewide_marks.get((row.event, row.gender, row.year, row.meet_type), [])
        total_marks = len(marks)
        better_or_equal = sum(1 for mark in marks if mark <= row.result2) if total_marks else None
        percentile = round((1 - (better_or_equal / total_marks)) * 100, 1) if total_marks else None
        # Cap at 99.9: an athlete is included in their own pool, so they can
        # never beat themselves (true max is (1 - 1/total) * 100 < 100).
        if percentile is not None:
            percentile = min(percentile, 99.9)
        results.append(
            {
                "event": row.event,
                "result": row.result or _format_result_display(row.result2, event_type),
                "result_value": row.result2,
                "place": row.place,
                "athlete_names": row.athlete_names,
                "lineup": lineup,
                "meet_id": row.meet_id,
                "meet_host": row.host,
                "meet_type": row.meet_type,
                "meet_num": row.meet_num,
                "gender": row.gender,
                "year": row.year,
                "event_type": event_type,
                "state_percentile": max(percentile, 0) if percentile is not None else None,
                "rank": better_or_equal,
                "total_marks": total_marks,
                "_meet_order": meet_order.get(row.meet_type, 0),
            }
        )

    results.sort(
        key=lambda item: (
            -(item.get("year") or 0),
            -(item.get("_meet_order") or 0),
            item.get("event") or "",
            item.get("result_value") if item.get("result_value") is not None else float("inf"),
        )
    )

    for item in results:
        item.pop("_meet_order", None)

    return results

def _compute_cumulative_points(school_id: int):
    """
    Compute cumulative points, team rankings, and average places for a school across playoff meets from 2023+.
    Points: 1st=10, 2nd=8, 3rd=6, 4th=5, 5th=4, 6th=3, 7th=2, 8th=1.
    Returns dict keyed by gender, each containing yearly breakdown with points, team rank, and avg places.
    Team rank is relative to schools at the same meet (sectional/regional) or statewide (state).
    """

    # First, get ALL schools' points for ranking purposes
    # Include meet_id and event so ties WITHIN an event can be detected and
    # split fractionally -- two different events both having a "3rd place"
    # at the same meet are not a tie with each other.
    all_individual_rows = (
        db.session.query(
            Athlete.school_id,
            AthleteResult.event,
            Meet.meet_id,
            Meet.year,
            Meet.gender,
            Meet.meet_type,
            AthleteResult.place,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            AthleteResult.result_type == "Final",
            AthleteResult.place.isnot(None),
            AthleteResult.place > 0,
            AthleteResult.place <= 9,
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    all_relay_rows = (
        db.session.query(
            RelayResult.school_id,
            RelayResult.event,
            Meet.meet_id,
            Meet.year,
            Meet.gender,
            Meet.meet_type,
            RelayResult.place,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.place.isnot(None),
            RelayResult.place > 0,
            RelayResult.place <= 9,
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    # Group into {(meet_id, event): [(school_id, place), ...]} for tie
    # detection, and separately track each school's raw per-meet place list
    # (for avg_place/entries display -- unaffected by point tie-splitting).
    event_groups = {}
    meet_metadata = {}
    school_places_by_meet = {}
    for rows in (all_individual_rows, all_relay_rows):
        for sid, event, meet_id, year, gender, meet_type, place in rows:
            meet_metadata.setdefault(meet_id, (year, gender, meet_type))
            event_groups.setdefault((meet_id, event), []).append((sid, place))
            school_places_by_meet.setdefault(meet_id, {}).setdefault(sid, []).append(place)

    # Build {meet_id: {school_id: {"points": float, "places": [int]}}},
    # awarding points per event using each event's actual recorded place
    # (not each row's sequential position), splitting a tie's combined
    # scoring-slot value evenly across the tied schools -- mirrors
    # standalone/scripts/calculate_team_scores.py's get_points().
    meet_school_stats = {}

    def _stats_entry(meet_id, sid):
        return meet_school_stats.setdefault(meet_id, {}).setdefault(sid, {"points": 0, "places": []})

    for (meet_id, event), school_places in event_groups.items():
        _, _, meet_type = meet_metadata[meet_id]
        points_table = _STATE_PLACE_POINTS if meet_type == "State" else _PLACE_POINTS

        by_place = {}
        for sid, place in school_places:
            by_place.setdefault(place, []).append(sid)

        for actual_place, tied_schools in by_place.items():
            tie_size = len(tied_schools)
            scoring_slots = [p for p in range(actual_place, actual_place + tie_size) if p in points_table]
            pts_value = (sum(points_table[p] for p in scoring_slots) / tie_size) if scoring_slots else 0
            for sid in tied_schools:
                _stats_entry(meet_id, sid)["points"] += pts_value

    for meet_id, by_school in school_places_by_meet.items():
        for sid, places in by_school.items():
            _stats_entry(meet_id, sid)["places"] = places

    # Compute rankings for each meet
    # {meet_id: {school_id: {"rank": int, "total_teams": int}}}
    # total_teams = all schools that competed at the meet (not just scorers)
    all_competing_indiv = (
        db.session.query(Athlete.school_id, AthleteResult.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .distinct()
        .all()
    )
    all_competing_relay = (
        db.session.query(RelayResult.school_id, RelayResult.meet_id)
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .distinct()
        .all()
    )
    meet_total_schools = {}
    for sid, mid in all_competing_indiv + all_competing_relay:
        meet_total_schools.setdefault(mid, set()).add(sid)

    # Alphabetical-by-school-name secondary sort for equal-points ties --
    # standardizes on the tiebreak convention already used by the
    # regional/state/projected-team-scores prediction scripts.
    school_names = dict(db.session.query(School.school_id, School.school_name).all())

    meet_rankings = {}
    for meet_id, schools_data in meet_school_stats.items():
        sorted_schools = sorted(
            schools_data.items(),
            key=lambda x: (-x[1]["points"], school_names.get(x[0], "")),
        )
        total = len(meet_total_schools.get(meet_id, set()) | set(schools_data.keys()))
        rankings = {}
        for rank, (sid, _) in enumerate(sorted_schools, start=1):
            rankings[sid] = {"rank": rank, "total_teams": total}
        meet_rankings[meet_id] = rankings

    # Now extract data for the specific school
    # Aggregate by (year, gender, meet_type) for display
    stats_data = {}
    for meet_id, schools_data in meet_school_stats.items():
        if school_id not in schools_data:
            continue
        year, gender, meet_type = meet_metadata[meet_id]
        school_stats = schools_data[school_id]
        ranking_info = meet_rankings[meet_id].get(school_id, {})
        
        gender_data = stats_data.setdefault(gender, {})
        year_data = gender_data.setdefault(year, {})
        # For a given year/gender/meet_type, store the data
        # (a school only competes at one sectional/regional per year/gender)
        year_data[meet_type] = {
            "points": school_stats["points"],
            "places": school_stats["places"],
            "team_rank": ranking_info.get("rank"),
            "total_teams": ranking_info.get("total_teams"),
        }

    result = {}
    for gender, years_dict in stats_data.items():
        yearly = []
        total = 0
        for year in sorted(years_dict.keys(), reverse=True):
            meet_types = years_dict[year]
            year_total = sum(mt.get("points", 0) for mt in meet_types.values())
            total += year_total
            
            year_entry = {"year": year, "total": year_total}
            for mt_name in ("Sectional", "Regional", "State"):
                mt_key = mt_name.lower()
                mt_data = meet_types.get(mt_name, {})
                places = mt_data.get("places", [])
                year_entry[mt_key] = {
                    "points": mt_data.get("points", 0),
                    "avg_place": round(sum(places) / len(places), 1) if places else None,
                    "entries": len(places),
                    "team_rank": mt_data.get("team_rank"),
                    "total_teams": mt_data.get("total_teams"),
                }
            yearly.append(year_entry)
        result[gender] = {"yearly": yearly, "grand_total": total}

    return result

def _format_points_value(points: Optional[float]) -> Optional[str]:
    if points is None:
        return None
    rounded = round(points, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"

# Cached: one cold dashboard calls this eight times over with repeating
# arguments -- once per season for the rank history, again per school for the
# scorecard -- and each call re-runs the join and rebuilds every row as a dict.
# Verified output-identical across 60 dashboard payloads before being added; the
# returned list is treated as read-only by every caller, so they share it.
@lru_cache(maxsize=64)
def _resolve_postseason_relay_rows(
    *,
    gender: Optional[str] = None,
    year: Optional[int] = None,
    school_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query = (
        db.session.query(
            RelayResult.school_id.label("school_id"),
            School.school_name.label("school_name"),
            Meet.gender.label("gender"),
            RelayResult.event.label("event"),
            RelayResult.meet_id.label("meet_id"),
            Meet.meet_type.label("meet_type"),
            Meet.year.label("year"),
            RelayResult.result.label("result"),
            RelayResult.result2.label("result_value"),
            RelayResult.place.label("place"),
            RelayResult.athlete_names.label("athlete_names"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .outerjoin(School, RelayResult.school_id == School.school_id)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
            RelayResult.result2.isnot(None),
        )
    )
    if gender:
        query = query.filter(Meet.gender == gender)
    if year is not None:
        query = query.filter(Meet.year == year)
    if school_id is not None:
        query = query.filter(RelayResult.school_id == school_id)

    return [
        {
            "school_id": row.school_id,
            "school_name": row.school_name,
            "gender": row.gender,
            "event": row.event,
            "meet_id": row.meet_id,
            "meet_type": row.meet_type,
            "year": row.year,
            "event_type": CONST.EVENT_TYPE.RELAY,
            "result": row.result,
            "result_value": row.result_value,
            "place": row.place,
            "athlete_names": row.athlete_names,
            "lineup": _extract_relay_names(row.athlete_names or ""),
        }
        for row in query.all()
    ]

# Scores an entire meet for every school in it, so two schools that ran the same
# sectional were each paying for the identical computation. One core request
# triggers 5-8 of these via stage summary and sectional group points. There are
# 328 meets in the corpus, so maxsize=512 holds all of them.
@lru_cache(maxsize=512)
def _compute_team_scores_for_meet(meet_id: int) -> Dict[int, Dict[str, Any]]:
    meet = db.session.get(Meet, meet_id)
    if not meet:
        return {}

    points_table = _STATE_PLACE_POINTS if meet.meet_type == CONST.MEET_TYPE.STATE else _PLACE_POINTS
    scoring_limit = 9 if meet.meet_type == CONST.MEET_TYPE.STATE else 8

    individual_rows = (
        db.session.query(
            Athlete.school_id,
            AthleteResult.event,
            AthleteResult.place,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            AthleteResult.meet_id == meet_id,
            AthleteResult.result_type == CONST.RESULT_TYPE.FINAL,
            AthleteResult.place.isnot(None),
            AthleteResult.place > 0,
            AthleteResult.place <= scoring_limit,
        )
        .all()
    )
    relay_rows = (
        db.session.query(
            RelayResult.school_id,
            RelayResult.event,
            RelayResult.place,
        )
        .filter(
            RelayResult.meet_id == meet_id,
            RelayResult.place.isnot(None),
            RelayResult.place > 0,
            RelayResult.place <= scoring_limit,
        )
        .all()
    )
    event_groups: Dict[str, List[Tuple[int, int]]] = {}
    for school_id_value, event_name, place in list(individual_rows) + list(relay_rows):
        event_groups.setdefault(event_name, []).append((school_id_value, place))

    points_by_school: Dict[int, float] = {}
    points_by_school_event: Dict[int, Dict[str, float]] = {}
    for event_name, placements in event_groups.items():
        by_place: Dict[int, List[int]] = {}
        for school_id_value, place in placements:
            by_place.setdefault(place, []).append(school_id_value)

        for actual_place, tied_schools in by_place.items():
            scoring_slots = [
                place_number
                for place_number in range(actual_place, actual_place + len(tied_schools))
                if place_number in points_table
            ]
            points_value = (
                sum(points_table[place_number] for place_number in scoring_slots) / len(tied_schools)
                if scoring_slots
                else 0
            )
            for school_id_value in tied_schools:
                points_by_school[school_id_value] = points_by_school.get(school_id_value, 0) + points_value
                per_event = points_by_school_event.setdefault(school_id_value, {})
                per_event[event_name] = per_event.get(event_name, 0.0) + points_value

    participants = {
        row[0]
        for row in db.session.query(Athlete.school_id)
        .join(AthleteResult, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(AthleteResult.meet_id == meet_id)
        .distinct()
        .all()
    }
    participants.update(
        row[0]
        for row in db.session.query(RelayResult.school_id)
        .filter(RelayResult.meet_id == meet_id)
        .distinct()
        .all()
    )

    school_names = dict(
        db.session.query(School.school_id, School.school_name)
        .filter(School.school_id.in_(participants))
        .all()
    ) if participants else {}

    ranked = {}
    ordered = sorted(
        participants,
        key=lambda school_id_value: (
            -points_by_school.get(school_id_value, 0),
            school_names.get(school_id_value, ""),
        ),
    )
    for index, school_id_value in enumerate(ordered, start=1):
        ranked[school_id_value] = {
            "points": round(points_by_school.get(school_id_value, 0), 1),
            "rank": index,
            "total_teams": len(participants),
            "points_by_event": {
                event: round(value, 1)
                for event, value in points_by_school_event.get(school_id_value, {}).items()
            },
        }
    return ranked

def _missing_auto_slots_by_meet(rows, cutoff_place: int = 3):
    """Return placeholder slots needed per meet, handling ties correctly.

    MileSplit place labels can skip a place when there is a tie (for example,
    1st, 2nd, 2nd, no 3rd). In that case, there are already three automatic
    qualifiers represented, so no placeholder should be added.
    """
    meet_data = {}

    for row in rows:
        meet_num_raw = getattr(row, "meet_num", None)
        if meet_num_raw is None:
            continue

        try:
            meet_num = int(meet_num_raw)
        except (TypeError, ValueError):
            continue

        if meet_num not in meet_data:
            meet_data[meet_num] = {
                "top_count": 0,
                "places": set(),
                "host": getattr(row, "host", None),
            }

        place_raw = getattr(row, "place", None)
        try:
            place = int(place_raw)
        except (TypeError, ValueError):
            continue

        if 1 <= place <= cutoff_place:
            meet_data[meet_num]["top_count"] += 1
            meet_data[meet_num]["places"].add(place)

    missing = []
    for meet_num in sorted(meet_data.keys()):
        top_count = meet_data[meet_num]["top_count"]
        missing_slots = max(0, cutoff_place - top_count)
        if missing_slots == 0:
            continue

        missing_places = [
            place for place in range(1, cutoff_place + 1)
            if place not in meet_data[meet_num]["places"]
        ]
        while len(missing_places) < missing_slots:
            missing_places.append(cutoff_place)

        for place in missing_places[:missing_slots]:
            missing.append((meet_num, place, meet_data[meet_num]["host"]))

    return missing

def _score_h2h_meet(current_entries, prior_entries):
    """Score two seasons of the same school against each other as a dual meet.

    5-3-1 for individual events, 5-0 for relays. An event a side did not contest
    simply yields it no points -- the vacancy costs the same in every event,
    which is exactly how it works at a real meet.
    """
    points_current = 0.0
    points_prior = 0.0
    events_won = 0
    events_lost = 0
    uncontested_points = 0.0

    for event_name in sorted(set(current_entries) | set(prior_entries)):
        mine = current_entries.get(event_name, [])
        theirs = prior_entries.get(event_name, [])
        sample = (mine or theirs)[0]
        event_type = sample.get("event_type") or CONST.EVENT_TYPE.TRACK
        lower_is_better = _is_lower_better(event_type)

        field = [(row["result_value"], "current") for row in mine]
        field += [(row["result_value"], "prior") for row in theirs]
        field.sort(key=lambda item: item[0], reverse=not lower_is_better)

        table = _H2H_RELAY_POINTS if event_name in CONST.EVENT.ALL_RELAY else _H2H_INDIVIDUAL_POINTS
        event_current = 0.0
        event_prior = 0.0

        # Equal marks split the combined value of the places they occupy, the same
        # convention as _compute_cumulative_points. Without this, a stable sort hands
        # every tie to whichever season is listed first, which would inflate the
        # current season against every past one -- a season scored against itself
        # would "win" instead of tying.
        index = 0
        while index < len(field):
            value = field[index][0]
            tied = [entry for entry in field[index:] if entry[0] == value]
            slots = [
                table[place] for place in range(index, index + len(tied)) if place < len(table)
            ]
            if slots:
                share = sum(slots) / len(tied)
                for _value, side in tied:
                    if side == "current":
                        event_current += share
                    else:
                        event_prior += share
            index += len(tied)

        # Points scored in events the other season did not contest at all -- worth
        # reporting separately so a win is not misread as "everyone ran faster".
        if mine and not theirs:
            uncontested_points += event_current

        points_current += event_current
        points_prior += event_prior
        if event_current > event_prior:
            events_won += 1
        elif event_prior > event_current:
            events_lost += 1

    return {
        "points_for": round(points_current, 1),
        "points_against": round(points_prior, 1),
        "events_won": events_won,
        "events_lost": events_lost,
        "uncontested_points": round(uncontested_points, 1),
    }

def _stage_index(meet_type):
    try:
        return _STAGE_ORDER.index(meet_type)
    except ValueError:
        return -1

def _stage_cells(rows, lower_is_better, event_type):
    """The one mark to show per stage, plus which stage holds the best of them.

    Every stage runs its own rounds, so a sprinter has a prelim and a final at each
    of them. The final is what the stage is judged on, so it wins; a prelim only
    surfaces when the athlete never reached the final, and is marked as such.
    """
    def _valid(row):
        return _is_valid_postseason_mark(row["result_value"], event_type)

    per_stage: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        stage = row.get("meet_type")
        if _stage_index(stage) < 0:
            continue
        current = per_stage.get(stage)
        if current is None:
            per_stage[stage] = row
            continue
        # A real mark beats a sentinel (NT/DQ), a final beats a prelim, and past
        # that the better mark wins. Sentinel rows are kept rather than dropped:
        # a relay that reached the regional and ran NT still reached the regional,
        # and dropping the row made the season look like it ended a round earlier.
        row_valid, current_valid = _valid(row), _valid(current)
        if row_valid != current_valid:
            if row_valid:
                per_stage[stage] = row
            continue
        is_final = row.get("result_type") == CONST.RESULT_TYPE.FINAL
        was_final = current.get("result_type") == CONST.RESULT_TYPE.FINAL
        if is_final and not was_final:
            per_stage[stage] = row
        elif is_final == was_final and row_valid and _is_better(
            row["result_value"], current["result_value"], lower_is_better
        ):
            per_stage[stage] = row

    cells = {}
    best_stage = None
    best_value = None
    for stage, row in per_stage.items():
        has_mark = _valid(row)
        cells[stage] = {
            # The sentinel token itself (NT, DQ) is the honest display: it says
            # what happened, where a blank cell would say they were never there.
            "mark_display": row.get("result") or (
                _format_result_display(row["result_value"], event_type) if has_mark else None
            ),
            "result_value": row["result_value"] if has_mark else None,
            "has_mark": has_mark,
            "place": row.get("place") if row.get("place") and row["place"] > 0 else None,
            "round": row.get("result_type"),
        }
        if has_mark and (
            best_value is None
            or _is_better(row["result_value"], best_value, lower_is_better)
        ):
            best_value = row["result_value"]
            best_stage = stage
    return cells, best_stage, best_value
