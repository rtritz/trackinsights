"""Qualifiers

Who advanced and who did not: regional and state qualifier
lists and the advancement rules behind them.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Any,
    Athlete,
    AthleteResult,
    CONST,
    CURRENT_QUALIFIER_YEAR,
    Dict,
    List,
    Meet,
    Optional,
    REGIONAL_SECTIONAL_GROUPS,
    REGIONAL_TARGET_FIELD_SIZE,
    RelayResult,
    Request,
    School,
    Tuple,
    _AUTO_DEPTH,
    _CALLBACK_SLOTS,
    _STAGE_ORDER,
    db,
    func,
    get_configured_regional_hosts,
    get_state_standard_display,
    html_lib,
    logger,
    lru_cache,
    math,
    meets_state_standard,
    re,
    sys,
    urlopen,
)

from .shared import (
    _display_sectional_host,
    _format_gap_display,
    _format_result_display,
    _get_event_types_map,
    _is_valid_postseason_mark,
    _state_target_field_size,
    _callback_group,
    _easier,
    _is_better,
)

from .meets import (
    _missing_auto_slots_by_meet,
    _stage_index,
)



def _format_school_qualifier_row(row: Dict[str, Any], stage_name: str, event_name: Optional[str] = None):
    source_label = row.get("sectional_host")
    if row.get("sectional_num") is not None and not source_label:
        source_label = f"{stage_name} feed {row.get('sectional_num')}"
    return {
        "event": row.get("event") or event_name,
        "mark": row.get("result") or "—",
        "place": row.get("place"),
        "qualifier_type": row.get("qualifier_type"),
        "source_label": source_label,
        "school_id": row.get("school_id"),
        "school_name": row.get("school"),
        "athlete_id": row.get("athlete_id"),
        "name": row.get("name") or row.get("school"),
        "lineup": [],
    }

def _regional_events_for_gender(gender: str):
    events = [
        "100 Meters",
        "200 Meters",
        "400 Meters",
        "800 Meters",
        "1600 Meters",
        "3200 Meters",
        "300 Hurdles",
        "High Jump",
        "Long Jump",
        "Shot Put",
        "Discus",
        "Pole Vault",
        "4 x 100 Relay",
        "4 x 400 Relay",
        "4 x 800 Relay",
    ]
    events.insert(6, "110 Hurdles" if gender == "Boys" else "100 Hurdles")
    return events

@lru_cache(maxsize=32)
def _ihsaa_regional_hosts(year: int, gender: str):
    gender_slug = "boys" if str(gender).strip().lower() == "boys" else "girls"
    parsed_year = int(year)
    season_slug = f"{parsed_year - 1}-{parsed_year % 100:02d}"
    url = f"https://www.ihsaa.org/sports/{gender_slug}/track-field/{season_slug}-tournament?round=regionals"

    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    hosts = {}

    # The tournament page includes sectional and regional rows together.
    # Regional rows include "Sectional Host:" in their text.
    paragraphs = re.findall(r"<p[^>]*>.*?</p>", html, flags=re.IGNORECASE | re.DOTALL)
    for block in paragraphs:
        lower_block = block.lower()
        if "in.milesplit.com" not in lower_block or "/results" not in lower_block:
            continue
        if "sectional host:" not in lower_block:
            continue

        text = re.sub(r"<[^>]+>", " ", block)
        text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()

        before_tickets = text.split("Tickets", 1)[0].strip()
        match = re.match(r"^(\d{1,2})\.\s*(.+)$", before_tickets)
        if not match:
            continue

        regional_num = int(match.group(1))
        host = re.sub(
            r"\s+\d{1,2}(?::\d{2})?\s*[ap]m(?:\s*[A-Z]{2})?$",
            "",
            match.group(2).strip(),
            flags=re.IGNORECASE,
        ).strip(" -")
        host = re.sub(r"\s*\(\d+\)\s*$", "", host).strip()
        if host and regional_num not in hosts:
            hosts[regional_num] = host

    return hosts

def _regional_hosts_for_year(year: int, gender: str):
    regional_hosts = get_configured_regional_hosts(year, gender)

    regional_host_rows = (
        db.session.query(Meet.meet_num, Meet.host)
        .filter(
            Meet.meet_type == "Regional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .all()
    )

    for meet_num, host in regional_host_rows:
        if meet_num is None:
            continue
        if host:
            regional_hosts.setdefault(meet_num, host)

    # Fill any remaining gaps from IHSAA tournament hosts.
    for meet_num, host in _ihsaa_regional_hosts(year, gender).items():
        regional_hosts.setdefault(meet_num, host)

    return regional_hosts

def _regional_group_status(year: int, gender: str):
    meet_nums = (
        db.session.query(Meet.meet_num)
        .filter(
            Meet.meet_type == "Sectional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .distinct()
        .all()
    )
    loaded = {row[0] for row in meet_nums if row[0] is not None}

    regional_hosts = _regional_hosts_for_year(year, gender)

    regionals = []
    import sys
    logger.info(f"Loaded sectionals for {year} {gender}: {sorted(list(loaded))}")

    for regional_num, feeders in REGIONAL_SECTIONAL_GROUPS.items():
        feeder_set = set(feeders)
        completed = sorted(feeder_set.intersection(loaded))
        missing = sorted(feeder_set.difference(loaded))
        logger.info(f"Regional {regional_num}: completed={completed}, missing={missing}")
        if len(completed) == len(feeders):
            status = "ready"
        elif completed:
            status = "not_ready"
        else:
            status = "not_ready"

        regionals.append(
            {
                "regional_num": regional_num,
                "status": status,
                "completed_sectionals": len(completed),
                "total_sectionals": len(feeders),
                "missing_sectionals": missing,
                "loaded_sectionals": completed,
                "regional_host": regional_hosts.get(regional_num),
            }
        )

    total_completed = sum(item["completed_sectionals"] for item in regionals)
    ready_count = sum(1 for item in regionals if item["status"] == "ready")

    return {
        "year": year,
        "gender": gender,
        "ready_regionals": ready_count,
        "total_regionals": len(REGIONAL_SECTIONAL_GROUPS),
        "completed_sectionals": total_completed,
        "total_sectionals": 32,
        "generated_at": func.now(),
        "regionals": regionals,
    }

def get_regional_qualifiers_status(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    payload = _regional_group_status(year, clean_gender)
    payload["generated_at"] = str(db.session.query(func.datetime("now")).scalar())
    payload["disclaimer"] = "Unofficial until IHSAA confirmation."
    return payload

def _state_group_status(year: int, gender: str):
    meet_nums = (
        db.session.query(Meet.meet_num)
        .filter(
            Meet.meet_type == "Regional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .distinct()
        .all()
    )
    loaded = {row[0] for row in meet_nums if row[0] is not None}

    regional_hosts = _regional_hosts_for_year(year, gender)

    state_host_row = (
        db.session.query(Meet.host)
        .filter(
            Meet.meet_type == "State",
            Meet.year == year,
            Meet.gender == gender,
            Meet.host.isnot(None),
        )
        .first()
    )
    state_host = state_host_row[0] if state_host_row else ""

    all_regionals = sorted(REGIONAL_SECTIONAL_GROUPS.keys())
    loaded_regionals = [regional_num for regional_num in all_regionals if regional_num in loaded]
    missing_regionals = [regional_num for regional_num in all_regionals if regional_num not in loaded]
    ready = len(loaded_regionals) == len(all_regionals)

    return {
        "year": year,
        "gender": gender,
        "status": "ready" if ready else "pending",
        "ready_regionals": len(loaded_regionals),
        "total_regionals": len(all_regionals),
        "completed_regionals": len(loaded_regionals),
        "missing_regionals": missing_regionals,
        "loaded_regionals": loaded_regionals,
        "regional_hosts": regional_hosts,
        "state_host": state_host,
        "generated_at": func.now(),
    }

def get_state_qualifiers_status(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    payload = _state_group_status(year, clean_gender)
    payload["generated_at"] = str(db.session.query(func.datetime("now")).scalar())
    payload["disclaimer"] = "Unofficial until IHSAA confirmation."
    return payload

def _extend_to_cutoff_with_ties(rows, target_count):
    def _result_value(item):
        if isinstance(item, dict):
            return item.get("result2")
        return getattr(item, "result2", None)

    if target_count <= 0:
        return []
    if len(rows) <= target_count:
        return rows[:target_count]

    selected = list(rows[:target_count])
    last_value = _result_value(selected[-1])
    idx = target_count
    while idx < len(rows) and _result_value(rows[idx]) == last_value:
        selected.append(rows[idx])
        idx += 1
    return selected

def _qualifier_sort_key(row, lower_is_better: bool):
    value = row.get("result2")
    if value is None:
        return float("inf") if lower_is_better else float("-inf")
    return value

def _compute_event_qualifiers(
    event_name: str,
    gender: str,
    year: int,
    feeder_meet_nums: tuple,
    source_meet_type: str = "Sectional",
    target_field_size: int = REGIONAL_TARGET_FIELD_SIZE,
):
    event_type = _get_event_types_map().get(event_name, "Track")
    lower_is_better = event_type != "Field"

    if "Relay" in event_name:
        rows = (
            db.session.query(
                RelayResult.school_id.label("school_id"),
                School.school_name.label("school_name"),
                RelayResult.event.label("event"),
                RelayResult.result.label("result"),
                RelayResult.result2.label("result2"),
                RelayResult.place.label("place"),
                Meet.host.label("host"),
                Meet.meet_num.label("meet_num"),
            )
            .join(Meet, RelayResult.meet_id == Meet.meet_id)
            .join(School, RelayResult.school_id == School.school_id)
            .filter(
                Meet.meet_type == source_meet_type,
                Meet.year == year,
                Meet.gender == gender,
                Meet.meet_num.in_(feeder_meet_nums),
                RelayResult.event == event_name,
                RelayResult.result2.isnot(None),
                RelayResult.place.isnot(None),
            )
            .all()
        )

        # Detect which sectionals are missing the event entirely
        present_meet_nums = {row.meet_num for row in rows}
        missing_event_meet_nums = set(feeder_meet_nums) - present_meet_nums
        # Get host info for missing sectionals
        host_map = {row.meet_num: row.host for row in rows}
        for meet_num in missing_event_meet_nums:
            host_map.setdefault(meet_num, None)

        top3 = [row for row in rows if row.place is not None and row.place <= 3]
        missing_top3 = _missing_auto_slots_by_meet(rows)
        others = [row for row in rows if row.place is not None and row.place > 3]
        others_sorted = sorted(others, key=lambda row: row.result2, reverse=not lower_is_better)

        standard_qualifiers = [
            row for row in others_sorted
            if meets_state_standard(row.result2, gender, event_name, event_type, year=year)
        ]
        selected_school_ids = {row.school_id for row in top3}
        selected_school_ids.update(row.school_id for row in standard_qualifiers)

        remaining = [row for row in others_sorted if row.school_id not in selected_school_ids]
        auto_slots = len(top3) + len(missing_top3) + 3 * len(missing_event_meet_nums)
        needed_for_field_size = max(0, target_field_size - (auto_slots + len(standard_qualifiers)))
        fill_qualifiers = _extend_to_cutoff_with_ties(remaining, needed_for_field_size)

        formatted = []
        for row in top3:
            met_standard = meets_state_standard(row.result2, gender, event_name, event_type, year=year)
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": met_standard,
                    "qualifier_type": "auto",
                    "is_callback": False,
                }
            )

        for meet_num, place, host in missing_top3:
            formatted.append(
                {
                    "event": event_name,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": "-",
                    "result": "-",
                    "result2": None,
                    "place": place,
                    "sectional_host": _display_sectional_host(host, meet_num, year, gender),
                    "sectional_num": meet_num,
                    "met_standard": False,
                    "qualifier_type": "auto-missing",
                    "is_callback": False,
                    "is_placeholder": True,
                }
            )

        # Add placeholders for sectionals missing the event entirely
        for meet_num in missing_event_meet_nums:
            for place in (1, 2, 3):
                formatted.append(
                    {
                        "event": event_name,
                        "event_type": event_type,
                        "name": None,
                        "grade": None,
                        "school": "-",
                        "result": "-",
                        "result2": None,
                        "place": place,
                        "sectional_host": _display_sectional_host(host_map.get(meet_num), meet_num, year, gender),
                        "sectional_num": meet_num,
                        "met_standard": False,
                        "qualifier_type": "auto-missing",
                        "is_callback": False,
                        "is_placeholder": True,
                    }
                )

        for row in standard_qualifiers:
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": True,
                    "qualifier_type": "standard",
                    "is_callback": False,
                }
            )

        for row in fill_qualifiers:
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": False,
                    "qualifier_type": "fill",
                    "is_callback": True,
                }
            )

        return sorted(formatted, key=lambda row: _qualifier_sort_key(row, lower_is_better), reverse=not lower_is_better)

    rows = (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            Athlete.school_id.label("school_id"),
            AthleteResult.grade.label("grade"),
            School.school_name.label("school_name"),
            AthleteResult.event.label("event"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result2"),
            AthleteResult.place.label("place"),
            Meet.host.label("host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(School, Athlete.school_id == School.school_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type == source_meet_type,
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.in_(feeder_meet_nums),
            AthleteResult.event == event_name,
            AthleteResult.result_type == "Final",
            AthleteResult.result2.isnot(None),
            AthleteResult.place.isnot(None),
        )
        .all()
    )

    # Detect which sectionals are missing the event entirely (individual events)
    present_meet_nums = {row.meet_num for row in rows}
    missing_event_meet_nums = set(feeder_meet_nums) - present_meet_nums
    # Get host info for missing sectionals
    host_map = {row.meet_num: row.host for row in rows}
    for meet_num in missing_event_meet_nums:
        host_map.setdefault(meet_num, None)

    top3 = [row for row in rows if row.place is not None and row.place <= 3]
    missing_top3 = _missing_auto_slots_by_meet(rows)
    others = [row for row in rows if row.place is not None and row.place > 3]
    others_sorted = sorted(others, key=lambda row: row.result2, reverse=not lower_is_better)

    standard_qualifiers = [
        row for row in others_sorted
        if meets_state_standard(row.result2, gender, event_name, event_type, year=year)
    ]
    selected_athlete_ids = {row.athlete_id for row in top3}
    selected_athlete_ids.update(row.athlete_id for row in standard_qualifiers)

    remaining = [row for row in others_sorted if row.athlete_id not in selected_athlete_ids]
    # Count placeholders as auto-qualifiers for callback math
    num_missing_event_placeholders = 3 * len(missing_event_meet_nums)
    auto_slots = len(top3) + len(missing_top3) + num_missing_event_placeholders
    needed_for_field_size = max(0, target_field_size - (auto_slots + len(standard_qualifiers)))
    fill_qualifiers = _extend_to_cutoff_with_ties(remaining, needed_for_field_size)

    formatted = []
    for row in top3:
        met_standard = meets_state_standard(row.result2, gender, event_name, event_type, year=year)
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": met_standard,
                "qualifier_type": "auto",
                "is_callback": False,
            }
        )

    for meet_num, place, host in missing_top3:
        formatted.append(
            {
                "event": event_name,
                "event_type": event_type,
                "name": "Missing on MileSplit",
                "grade": "-",
                "school": "-",
                "result": "-",
                "result2": None,
                "place": place,
                "sectional_host": _display_sectional_host(host, meet_num, year, gender),
                "sectional_num": meet_num,
                "met_standard": False,
                "qualifier_type": "auto-missing",
                "is_callback": False,
                "is_placeholder": True,
            }
        )

    # Add placeholders for sectionals missing the event entirely (individual events)
    for meet_num in missing_event_meet_nums:
        for place in (1, 2, 3):
            formatted.append(
                {
                    "event": event_name,
                    "event_type": event_type,
                    "name": "Missing on MileSplit",
                    "grade": "-",
                    "school": "-",
                    "result": "-",
                    "result2": None,
                    "place": place,
                    "sectional_host": _display_sectional_host(host_map.get(meet_num), meet_num, year, gender),
                    "sectional_num": meet_num,
                    "met_standard": False,
                    "qualifier_type": "auto-missing",
                    "is_callback": False,
                    "is_placeholder": True,
                }
            )

    for row in standard_qualifiers:
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": True,
                "qualifier_type": "standard",
                "is_callback": False,
            }
        )

    for row in fill_qualifiers:
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": False,
                "qualifier_type": "fill",
                "is_callback": True,
            }
        )

    return sorted(formatted, key=lambda row: _qualifier_sort_key(row, lower_is_better), reverse=not lower_is_better)

@lru_cache(maxsize=128)
def get_regional_qualifiers(gender: str, regional_num: int, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    if regional_num not in REGIONAL_SECTIONAL_GROUPS:
        raise ValueError("regional_num must be an integer between 1 and 8")

    status_payload = _regional_group_status(year, clean_gender)
    status_map = {row["regional_num"]: row for row in status_payload["regionals"]}
    regional_status = status_map[regional_num]

    response = {
        "context": {
            "year": year,
            "gender": clean_gender,
            "regional_num": regional_num,
            "status": regional_status["status"],
            "completed_sectionals": regional_status["completed_sectionals"],
            "total_sectionals": regional_status["total_sectionals"],
            "missing_sectionals": regional_status["missing_sectionals"],
            "generated_at": str(db.session.query(func.datetime("now")).scalar()),
            "disclaimer": "Unofficial until IHSAA confirmation.",
        },
        "events": [],
    }


    # Allow predictions for regionals with all feeders present, mark others as pending
    if regional_status["status"] != "ready":
        response["context"]["note"] = "Pending: Not all feeder sectionals are loaded. Predictions below are only shown for completed sectionals."
        # Only show predictions for completed feeders
        feeder_meet_nums = REGIONAL_SECTIONAL_GROUPS[regional_num]
        events = _regional_events_for_gender(clean_gender)
        for event_name in events:
            # Only include results for sectionals that are loaded
            loaded_feeders = tuple(set(feeder_meet_nums).intersection(set(regional_status["loaded_sectionals"])))
            if not loaded_feeders:
                continue
            qualifiers = _compute_event_qualifiers(event_name, clean_gender, year, loaded_feeders)
            response["events"].append(
                {
                    "event": event_name,
                    "event_type": _get_event_types_map().get(event_name, "Track"),
                    "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                    "qualifiers": qualifiers,
                }
            )
        return response

    feeder_meet_nums = REGIONAL_SECTIONAL_GROUPS[regional_num]
    events = _regional_events_for_gender(clean_gender)
    for event_name in events:
        qualifiers = _compute_event_qualifiers(event_name, clean_gender, year, feeder_meet_nums)
        response["events"].append(
            {
                "event": event_name,
                "event_type": _get_event_types_map().get(event_name, "Track"),
                "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                "qualifiers": qualifiers,
            }
        )

    return response

def get_state_qualifiers(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    status_payload = _state_group_status(year, clean_gender)

    response = {
        "context": {
            "year": year,
            "gender": clean_gender,
            "status": status_payload["status"],
            "completed_regionals": status_payload["completed_regionals"],
            "total_regionals": status_payload["total_regionals"],
            "missing_regionals": status_payload["missing_regionals"],
            "generated_at": str(db.session.query(func.datetime("now")).scalar()),
            "disclaimer": "Unofficial until IHSAA confirmation.",
        },
        "events": [],
    }

    if status_payload["status"] != "ready":
        return response

    feeder_meet_nums = tuple(sorted(REGIONAL_SECTIONAL_GROUPS.keys()))
    events = _regional_events_for_gender(clean_gender)
    target_field_size = _state_target_field_size(year)
    for event_name in events:
        qualifiers = _compute_event_qualifiers(
            event_name,
            clean_gender,
            year,
            feeder_meet_nums,
            source_meet_type="Regional",
            target_field_size=target_field_size,
        )
        response["events"].append(
            {
                "event": event_name,
                "event_type": _get_event_types_map().get(event_name, "Track"),
                "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                "qualifiers": qualifiers,
            }
        )

    return response

def _advancement_from_rows(rows, next_stage_pairs, pair_of, lower_is_better_of):
    """Where each entry's season ended, and the mark it needed to go further.

    The bar is the easier of two real, observed marks:

    * the **auto** path -- the third-place mark at their own meet, since beating it
      would have earned an automatic spot; and
    * the **callback** path -- the last mark to take a callback slot in their pool.

    The callback line is counted from the top (the Nth best non-auto mark), not up
    from the poorest athlete who turned up. Selection happens on marks before anyone
    withdraws, so counting from the bottom lets a withdrawal soften the bar: in the
    2026 Boys regional-2 3200, two auto qualifiers from one sectional did not run
    and their sectional's 4th and 5th places replaced them at 10:37 and 10:41, while
    the mark that actually took the last callback slot was 9:58.75. Counting from
    the top is immune to that.

    An entry that met its bar but never appeared at the next stage qualified and did
    not compete -- roughly one callback in eight -- so it is reported that way rather
    than being given a gap it never had.
    """
    by_stage: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if _stage_index(row["meet_type"]) < 0:
            continue
        by_stage.setdefault(row["meet_type"], []).append(row)

    # ---- the two lines, per stage that has a next stage ---------------------
    auto_lines: Dict[Tuple[int, str], float] = {}
    callback_lines: Dict[Tuple[str, Tuple[Any, str]], float] = {}

    for stage, stage_rows in by_stage.items():
        stage_index = _stage_index(stage)
        if stage_index >= len(_STAGE_ORDER) - 1:
            continue

        finals = [
            row for row in stage_rows
            if row["result_type"] == CONST.RESULT_TYPE.FINAL
            and row.get("place")
            and row["place"] > 0
            and _is_valid_postseason_mark(row["result_value"], row["event_type"])
        ]

        # Auto line: the mark of the last automatic qualifying place at that meet.
        for row in finals:
            if row["place"] > _AUTO_DEPTH:
                continue
            key = (row["meet_id"], row["event"])
            current = auto_lines.get(key)
            lower_is_better = lower_is_better_of(row)
            # The poorest of the automatic places is the bar to reach them.
            if current is None or _is_better(current, row["result_value"], lower_is_better):
                auto_lines[key] = row["result_value"]

        # Callback line: the Nth best mark among those outside the automatic places.
        slots = _CALLBACK_SLOTS.get(stage)
        pools: Dict[Tuple[Any, str], List[Dict[str, Any]]] = {}
        for row in finals:
            if row["place"] <= _AUTO_DEPTH:
                continue
            group = _callback_group(stage, row.get("meet_num"), row["event"])
            pools.setdefault(group, []).append(row)
        for group, pool in pools.items():
            lower_is_better = lower_is_better_of(pool[0])
            pool.sort(key=lambda item: item["result_value"], reverse=not lower_is_better)
            if not slots:
                continue
            # Fewer contenders than slots means everyone outside the automatic
            # places got in, so the poorest of them is the line.
            index = min(slots, len(pool)) - 1
            callback_lines[(stage, group)] = pool[index]["result_value"]

    # ---- furthest stage reached per entry -----------------------------------
    furthest: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        stage_index = _stage_index(row["meet_type"])
        if stage_index < 0:
            continue
        pair = pair_of(row)
        current = furthest.get(pair)
        if current is None:
            furthest[pair] = row
            continue
        current_index = _stage_index(current["meet_type"])
        if stage_index > current_index:
            furthest[pair] = row
        elif stage_index == current_index:
            # The final decides advancement, so it wins over a prelim.
            if (row["result_type"] == CONST.RESULT_TYPE.FINAL
                    and current["result_type"] != CONST.RESULT_TYPE.FINAL):
                furthest[pair] = row

    result: Dict[Any, Dict[str, Any]] = {}
    for pair, row in furthest.items():
        stage = row["meet_type"]
        stage_index = _stage_index(stage)
        is_final = row["result_type"] == CONST.RESULT_TYPE.FINAL
        place = row.get("place")
        entry = {
            "final_stage": stage,
            "final_place": place if place and place > 0 else None,
            "final_round": CONST.RESULT_TYPE.FINAL if is_final else CONST.RESULT_TYPE.PRELIM,
            "final_mark_display": row.get("result"),
            "cutoff_display": None,
            "cutoff_path": None,
            "gap_display": None,
            # The raw numbers behind the two displays above. "0.29" in the 100 and
            # "10 inches" in the long jump cannot be ranked against each other,
            # but gap / cutoff can, and that ratio is what lets the dashboard say
            # which entries came closest across unlike events. Parsing it back out
            # of the formatted strings would mean re-reading feet and inches.
            "cutoff_value": None,
            "gap_value": None,
            "qualified_did_not_compete": False,
            "tied_cutoff": False,
        }

        can_advance = stage_index < len(_STAGE_ORDER) - 1
        valid = _is_valid_postseason_mark(row["result_value"], row["event_type"])
        if can_advance and is_final and valid:
            lower_is_better = lower_is_better_of(row)
            auto = auto_lines.get((row["meet_id"], row["event"]))
            group = _callback_group(stage, row.get("meet_num"), row["event"])
            callback = callback_lines.get((stage, group))
            bar = _easier(auto, callback, lower_is_better)

            if bar is not None:
                entry["cutoff_display"] = _format_result_display(bar, row["event_type"])
                entry["cutoff_value"] = bar
                if auto is not None and bar == auto and (
                    callback is None or auto != callback
                ):
                    entry["cutoff_path"] = "auto"
                elif callback is not None and bar == callback:
                    entry["cutoff_path"] = "callback"

                # Strictly better than the bar yet absent from the next stage: they
                # had the mark and did not run it.
                #
                # Equalling the bar is deliberately not treated as qualifying. The
                # vertical jumps move in two-inch steps, so ties on the bar mark are
                # routine -- one 2026 sectional had four boys at 5-8 for places 5,
                # 5, 7 and 8 -- and which of them advanced was settled by misses,
                # which the results do not record. Those rows get the bar with no
                # gap and no claim either way.
                if _is_better(row["result_value"], bar, lower_is_better):
                    entry["qualified_did_not_compete"] = True
                elif row["result_value"] == bar:
                    entry["tied_cutoff"] = True
                else:
                    gap = (
                        row["result_value"] - bar if lower_is_better
                        else bar - row["result_value"]
                    )
                    if gap > 0:
                        entry["gap_display"] = _format_gap_display(gap, row["event_type"])
                        entry["gap_value"] = gap

        result[pair] = entry

    return result
