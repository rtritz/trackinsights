"""Percentiles

Percentile tables and the percentile query tools.
"""

import math
from typing import List, Optional

from sqlalchemy import func

from .. import db
from ..models import Athlete, AthleteResult, Event, Meet, RelayResult
from ..analytics.percentile_tables import get_percentiles as _percentile_tables

from common.const import CONST

from .shared import (
    DEFAULT_PERCENTILES,
    GRADE_LEVELS,
    PERCENTILE_CHOICES,
    _coerce_sequence,
    _is_lower_better,
    _tuple_or_none,
    _unique_events,
)
from .formatting import (
    _format_result_display,
)

from .meets import (
    _available_meet_years,
)



def get_percentile_options():
    return {
        "events": _unique_events(),
        "genders": list(getattr(CONST.GENDER, "ALL", [])),
        "meet_types": list(getattr(CONST.MEET_TYPE, "ALL", [])),
        "grade_levels": list(GRADE_LEVELS),
        "default_percentiles": list(DEFAULT_PERCENTILES),
        "percentile_choices": list(PERCENTILE_CHOICES),
        "years": _available_meet_years(),
        "db_path": str(getattr(CONST, "DB_PATH", "")),
    }

def get_percentiles_report(
    *,
    events=None,
    genders=None,
    percentiles=None,
    years=None,
    meet_types=None,
    grade_levels=None,
):
    kwargs = {
        "events": _tuple_or_none(_coerce_sequence(events or [], str)),
        "genders": _tuple_or_none(_coerce_sequence(genders or [], str)),
        "percentiles": _tuple_or_none(
            _coerce_sequence(percentiles or DEFAULT_PERCENTILES, int)
        ),
        "years": _tuple_or_none(_coerce_sequence(years or [], int)),
        "meet_types": _tuple_or_none(_coerce_sequence(meet_types or [], str)),
        "grade_levels": _tuple_or_none(
            _coerce_sequence(grade_levels or [], lambda text: text.upper())
        ),
    }

    # The app's own connection, so the read sits inside the request's
    # transaction rather than opening a second handle to the same file.
    df = _percentile_tables(db.session.connection(), **kwargs)
    if df is None:
        return {"columns": [], "rows": [], "filters": kwargs}

    columns = [str(column) for column in df.columns]
    raw_rows = df.to_dict(orient="records")
    rows = [{str(key): value for key, value in row.items()} for row in raw_rows]

    return {
        "columns": columns,
        "rows": rows,
        "filters": {k: v for k, v in kwargs.items() if v},
        "result_count": len(rows),
    }

def _format_percentile(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"

def _compute_school_percentiles(school_id: int, year: Optional[int] = None):
    """Compute school best/avg marks and percentiles for playoff meets only.

    Rules implemented:
      - Only Sectional/Regional/State results are considered.
      - Individual marks resolve per meet using Final first, then Prelim fallback.
      - Athlete best mark = best resolved playoff mark in the filtered scope.
      - Best Mark percentile compares against individual athlete bests only.
      - Avg Mark percentile compares against qualifying school duo averages only.
      - For running events, lower is better; for field events, higher is better.
    """

    PLAYOFF_MEETS = ("Sectional", "Regional", "State")
    year_filter = (Meet.year == year) if year else Meet.year.isnot(None)

    def _athlete_season_marks(rows):
        """Collapse rows to (event, year, athlete) season best with Final-over-Prelim per meet."""
        per_meet = {}  # (athlete_id, event, meet_id) -> {result_type: (result2, year)}
        event_type_map = {}
        for r in rows:
            key = (r.athlete_id, r.event, r.meet_id)
            per_meet.setdefault(key, {})[r.result_type] = (r.result2, r.year)
            event_type_map[r.event] = r.event_type

        season = {}  # (event, year, athlete_id) -> {mark_raw, event_type}
        for (athlete_id, event, _meet_id), marks in per_meet.items():
            picked = marks.get("Final") or marks.get("Prelim")
            if picked is None:
                picked = next(iter(marks.values()), None)
            if picked is None:
                continue

            mark_val, mark_year = picked
            event_type = event_type_map[event]
            lower = _is_lower_better(event_type)
            season_key = (event, mark_year, athlete_id)
            existing = season.get(season_key)
            if existing is None or (
                (lower and mark_val < existing["mark_raw"])
                or (not lower and mark_val > existing["mark_raw"])
            ):
                season[season_key] = {
                    "mark_raw": mark_val,
                    "event_type": event_type,
                }
        return season

    def _calc_percentile(mark, all_marks, lower_is_better):
        if mark is None or not all_marks:
            return None, None, None
        total = len(all_marks)
        better_or_equal = sum(
            1 for m in all_marks if (m <= mark if lower_is_better else m >= mark)
        )
        percentile = round((1 - (better_or_equal / total)) * 100, 1)
        percentile = min(percentile, 99.9)
        return max(percentile, 0), better_or_equal, total

    # ── School individual rows (playoff meets only) ──
    school_indiv_rows = (
        db.session.query(
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.result_type,
            AthleteResult.result2,
            AthleteResult.athlete_id,
            Athlete.first,
            Athlete.last,
            Athlete.gender,
            Event.event_type,
            Meet.year,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
            Event.event_type != "Relay",
        )
        .all()
    )

    school_athlete_meta = {}
    for r in school_indiv_rows:
        if r.athlete_id not in school_athlete_meta:
            school_athlete_meta[r.athlete_id] = (
                "{} {}".format(r.first, r.last).strip(),
                r.gender,
            )

    school_season = _athlete_season_marks(school_indiv_rows)
    school_event_year_athletes = {}  # (event, gender, year) -> [{athlete...}]
    for (event, season_year, athlete_id), info in school_season.items():
        name, gender = school_athlete_meta[athlete_id]
        school_event_year_athletes.setdefault((event, gender, season_year), []).append(
            {
                "athlete_id": athlete_id,
                "name": name,
                "mark_raw": info["mark_raw"],
                "year": season_year,
                "event_type": info["event_type"],
            }
        )

    indiv_metrics = {}
    event_gender_pairs = {(e, g) for (e, g, _y) in school_event_year_athletes.keys()}
    for (event, gender) in event_gender_pairs:
        year_groups = {
            y: lst
            for (e, g, y), lst in school_event_year_athletes.items()
            if e == event and g == gender
        }
        event_type = next(iter(year_groups.values()))[0]["event_type"]
        lower = _is_lower_better(event_type)

        best_mark = None
        best_athletes = []
        for y, athletes in year_groups.items():
            for a in athletes:
                if best_mark is None or (
                    (lower and a["mark_raw"] < best_mark)
                    or (not lower and a["mark_raw"] > best_mark)
                ):
                    best_mark = a["mark_raw"]
                    best_athletes = [a]
                elif best_mark is not None and math.isclose(a["mark_raw"], best_mark, rel_tol=0.0, abs_tol=1e-9):
                    best_athletes.append(a)

        # Keep tie ordering deterministic.
        best_athletes.sort(key=lambda item: (-(item.get("year") or 0), item.get("name") or ""))

        best_duos = []
        best_duo_avg = None
        for y, athletes in year_groups.items():
            if len(athletes) < 2:
                continue
            sorted_athletes = sorted(athletes, key=lambda a: a["mark_raw"], reverse=not lower)
            duo = sorted_athletes[:2]
            duo_avg = (duo[0]["mark_raw"] + duo[1]["mark_raw"]) / 2.0
            if best_duo_avg is None or (
                (lower and duo_avg < best_duo_avg)
                or (not lower and duo_avg > best_duo_avg)
            ):
                best_duo_avg = duo_avg
                best_duos = [{"year": y, "avg_raw": duo_avg, "athletes": duo}]
            elif best_duo_avg is not None and math.isclose(duo_avg, best_duo_avg, rel_tol=0.0, abs_tol=1e-9):
                best_duos.append({"year": y, "avg_raw": duo_avg, "athletes": duo})

        best_duos.sort(
            key=lambda item: (
                -(item.get("year") or 0),
                " | ".join(a.get("name") or "" for a in item.get("athletes", [])),
            )
        )
        best_duo = best_duos[0]["athletes"] if best_duos else []
        best_duo_year = best_duos[0]["year"] if best_duos else None
        best_year = best_athletes[0]["year"] if best_athletes else None

        indiv_metrics[(event, gender)] = {
            "is_relay": False,
            "event_type": event_type,
            "best_raw": best_mark,
            "best_holder": best_athletes[0]["name"] if best_athletes else None,
            "best_holder_id": best_athletes[0]["athlete_id"] if best_athletes else None,
            "best_holders": best_athletes,
            "best_year": best_year,
            "avg_top2_raw": best_duo_avg,
            "avg_year": best_duo_year,
            "avg_top_athletes": best_duo,
            "avg_top_duos": best_duos,
        }

    # ── School relay bests (playoff meets only) ──
    relay_rows = (
        db.session.query(
            RelayResult.event,
            RelayResult.result2,
            RelayResult.athlete_names,
            Meet.gender,
            Meet.year,
            Event.event_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
        )
        .all()
    )

    relay_metrics = {}
    for row in relay_rows:
        key = (row.event, row.gender)
        lower_is_better = _is_lower_better(row.event_type)
        existing = relay_metrics.get(key)
        entry = {
            "name": row.athlete_names or "Relay Team",
            "athlete_id": None,
            "year": row.year,
            "mark_raw": row.result2,
        }
        if existing is None or (
            (lower_is_better and row.result2 < existing["best_raw"])
            or (not lower_is_better and row.result2 > existing["best_raw"])
        ):
            relay_metrics[key] = {
                "is_relay": True,
                "event_type": row.event_type,
                "best_raw": row.result2,
                "best_holder": entry["name"],
                "best_holder_id": None,
                "best_holders": [entry],
                "best_year": row.year,
                "avg_top2_raw": None,
                "avg_year": None,
                "avg_top_athletes": [],
                "avg_top_duos": [],
            }
        elif math.isclose(row.result2, existing["best_raw"], rel_tol=0.0, abs_tol=1e-9):
            existing["best_holders"].append(entry)

    for item in relay_metrics.values():
        holders = item.get("best_holders", [])
        holders.sort(key=lambda entry: (-(entry.get("year") or 0), entry.get("name") or ""))
        if holders:
            item["best_holder"] = holders[0]["name"]
            item["best_year"] = holders[0]["year"]

    all_metrics = {}
    all_metrics.update(indiv_metrics)
    all_metrics.update(relay_metrics)
    if not all_metrics:
        return []

    # ── Statewide individual rows (playoff meets only) ──
    statewide_indiv_rows = (
        db.session.query(
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.result_type,
            AthleteResult.result2,
            AthleteResult.athlete_id,
            Athlete.school_id,
            Athlete.gender,
            Event.event_type,
            Meet.year,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            AthleteResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
            Event.event_type != "Relay",
        )
        .all()
    )
    sw_season = _athlete_season_marks(statewide_indiv_rows)

    sw_meta = {}
    for r in statewide_indiv_rows:
        if r.athlete_id not in sw_meta:
            sw_meta[r.athlete_id] = {"gender": r.gender, "school_id": r.school_id}

    # Best distribution (individual athlete bests only)
    statewide_indiv_best_dist = {}  # (event, gender) -> [mark]
    sw_athlete_best = {}  # (event, gender, athlete_id) -> best mark
    for (event, _season_year, athlete_id), info in sw_season.items():
        meta = sw_meta.get(athlete_id)
        if not meta:
            continue
        gender = meta["gender"]
        lower = _is_lower_better(info["event_type"])
        key = (event, gender, athlete_id)
        existing = sw_athlete_best.get(key)
        if existing is None or (
            (lower and info["mark_raw"] < existing)
            or (not lower and info["mark_raw"] > existing)
        ):
            sw_athlete_best[key] = info["mark_raw"]

    for (event, gender, _athlete_id), mark in sw_athlete_best.items():
        statewide_indiv_best_dist.setdefault((event, gender), []).append(mark)

    # Avg distribution (qualifying school duos only)
    sw_school_event_year = {}  # (event, gender, year, school_id) -> [{mark_raw, event_type}]
    for (event, season_year, athlete_id), info in sw_season.items():
        meta = sw_meta.get(athlete_id)
        if not meta:
            continue
        key = (event, meta["gender"], season_year, meta["school_id"])
        sw_school_event_year.setdefault(key, []).append(
            {
                "mark_raw": info["mark_raw"],
                "event_type": info["event_type"],
            }
        )

    sw_duo_by_schoolyear = {}  # (event, gender, year, school_id) -> avg_raw
    for (event, gender, season_year, sid), athletes in sw_school_event_year.items():
        if len(athletes) < 2:
            continue
        event_type = athletes[0]["event_type"]
        lower = _is_lower_better(event_type)
        top2 = sorted(athletes, key=lambda a: a["mark_raw"], reverse=not lower)[:2]
        sw_duo_by_schoolyear[(event, gender, season_year, sid)] = (
            (top2[0]["mark_raw"] + top2[1]["mark_raw"]) / 2.0
        )

    # Avg percentile pool:
    # - Year-specific views use qualifying school-year duo values for that season.
    # - All-time views collapse to each school's single best duo average across all years in scope.
    statewide_duo_dist = {}  # (event, gender) -> [avg_raw]
    if year is not None:
        for (event, gender, _season_year, _sid), duo_avg in sw_duo_by_schoolyear.items():
            statewide_duo_dist.setdefault((event, gender), []).append(duo_avg)
    else:
        sw_best_duo_by_school = {}  # (event, gender, school_id) -> avg_raw
        for (event, gender, _season_year, sid), duo_avg in sw_duo_by_schoolyear.items():
            athletes = sw_school_event_year[(event, gender, _season_year, sid)]
            event_type = athletes[0]["event_type"]
            lower = _is_lower_better(event_type)
            key = (event, gender, sid)
            existing = sw_best_duo_by_school.get(key)
            if existing is None or (
                (lower and duo_avg < existing)
                or (not lower and duo_avg > existing)
            ):
                sw_best_duo_by_school[key] = duo_avg

        for (event, gender, _sid), duo_avg in sw_best_duo_by_school.items():
            statewide_duo_dist.setdefault((event, gender), []).append(duo_avg)

    # ── Statewide relay best distributions (school best relay marks) ──
    statewide_relay_dist = {}
    relay_group_rows = (
        db.session.query(
            RelayResult.event,
            Meet.gender,
            RelayResult.school_id,
            Event.event_type,
            func.min(RelayResult.result2).label("best_mark"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
        )
        .group_by(RelayResult.event, Meet.gender, RelayResult.school_id, Event.event_type)
        .all()
    )
    for row in relay_group_rows:
        statewide_relay_dist.setdefault((row.event, row.gender), []).append(row.best_mark)

    results = []
    for (event_name, gender), info in sorted(all_metrics.items()):
        event_type = info["event_type"]
        lower_is_better = _is_lower_better(event_type)

        best_raw = info["best_raw"]
        if info["is_relay"]:
            best_pool = statewide_relay_dist.get((event_name, gender), [])
        else:
            best_pool = statewide_indiv_best_dist.get((event_name, gender), [])
        best_pct, best_rank, best_total = _calc_percentile(best_raw, best_pool, lower_is_better)

        avg_raw = info.get("avg_top2_raw") if not info["is_relay"] else None
        avg_pool = statewide_duo_dist.get((event_name, gender), []) if not info["is_relay"] else []
        avg_pct, avg_rank, avg_total = _calc_percentile(avg_raw, avg_pool, lower_is_better)

        avg_top_athletes = [
            {
                "name": a["name"],
                "athlete_id": a["athlete_id"],
                "mark_raw": a["mark_raw"],
                "mark": _format_result_display(a["mark_raw"], event_type),
                "year": a["year"],
            }
            for a in info.get("avg_top_athletes", [])
        ]

        best_holders = [
            {
                "name": h.get("name"),
                "athlete_id": h.get("athlete_id"),
                "year": h.get("year"),
                "mark_raw": h.get("mark_raw"),
                "mark": _format_result_display(h.get("mark_raw"), event_type)
                if h.get("mark_raw") is not None else None,
            }
            for h in info.get("best_holders", [])
        ]

        top_duos = [
            {
                "year": duo.get("year"),
                "avg_raw": duo.get("avg_raw"),
                "avg_mark": _format_result_display(duo.get("avg_raw"), event_type)
                if duo.get("avg_raw") is not None else None,
                "athletes": [
                    {
                        "name": a.get("name"),
                        "athlete_id": a.get("athlete_id"),
                        "year": a.get("year"),
                        "mark_raw": a.get("mark_raw"),
                        "mark": _format_result_display(a.get("mark_raw"), event_type)
                        if a.get("mark_raw") is not None else None,
                    }
                    for a in duo.get("athletes", [])
                ],
            }
            for duo in info.get("avg_top_duos", [])
        ]

        results.append(
            {
                "event": event_name,
                "gender": gender,
                "event_type": event_type,
                "is_relay": info["is_relay"],
                "school_best": _format_result_display(best_raw, event_type) if best_raw is not None else None,
                "school_best_raw": best_raw,
                "school_avg_top2": _format_result_display(avg_raw, event_type) if avg_raw is not None else None,
                "school_avg_top2_raw": avg_raw,
                "avg_athlete_count": len(avg_top_athletes),
                "top_athletes": avg_top_athletes,
                "top_duos": top_duos,
                "holder": info.get("best_holder"),
                "holder_id": info.get("best_holder_id"),
                "holders": best_holders,
                "year": info.get("best_year"),
                "avg_year": info.get("avg_year"),
                "best_state_percentile": best_pct,
                "best_rank": best_rank,
                "best_total_marks": best_total,
                "avg_state_percentile": avg_pct,
                "avg_rank": avg_rank,
                "avg_total_marks": avg_total,
                # Backward-compatible fields (best metric)
                "state_percentile": best_pct,
                "rank": best_rank,
                "total_marks": best_total,
            }
        )

    return results

def _get_school_percentile_years(school_id: int) -> List[int]:
    """Return sorted list of years (descending) that a school has results (individual or relay)."""
    indiv_years = (
        db.session.query(Meet.year)
        .join(AthleteResult, AthleteResult.meet_id == Meet.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result2.isnot(None),
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            Meet.year.isnot(None),
        )
        .distinct()
        .all()
    )
    relay_years = (
        db.session.query(Meet.year)
        .join(RelayResult, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            Meet.year.isnot(None),
        )
        .distinct()
        .all()
    )
    all_years = set(r.year for r in indiv_years) | set(r.year for r in relay_years)
    return sorted(all_years, reverse=True)
