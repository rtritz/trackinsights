"""Database queries, grouped by feature.

Split out of a single 6,800-line module so that "where do I change this?" has an
answer. Every name the package defines is re-exported here, so
`from app.queries import X` and `queries.X` work exactly as before -- callers
did not have to change, and new code can import from the specific module instead.

    shared.py            helpers every feature uses
    school_dashboard.py  the dashboards themselves
    rankings.py          statewide program rankings
    scorecard.py         one school's entries, round by round
    outlook.py           returning athletes and head-to-head
    meets.py             meet results, team scoring, relays
    qualifiers.py        regional and state qualifiers, advancement rules
    athletes.py          athlete dashboards, rankings, badges
    percentiles.py       percentile tables and tools
    insights.py          sectional trends, hypothetical rankings
    search.py            site-wide athlete and school search

ADDING A FUNCTION
-----------------
Put it in the feature file it belongs to. If anything outside the package needs
it, add its name to that module's import list below -- otherwise
`from app.queries import your_function` will not find it. New code can also
import straight from the module (`from app.queries.athletes import ...`),
which needs no entry here.
"""

from .shared import (  # noqa: F401
    _active_db_path,
    _build_school_roster,
    _calculate_combined_score,
    _calculate_score,
    _choose_result_entry,
    _clear_query_caches,
    _coerce_sequence,
    _competition_rank_rows,
    _compute_all_event_difficulties,
    _compute_all_event_difficulties_from_data,
    _compute_avg_places,
    _compute_cohort_ranking,
    _compute_rank_for_event,
    _compute_school_records,
    _count_result_types,
    _covered_rank_seasons,
    _db_fingerprint,
    _display_sectional_host,
    _format_gap_display,
    _format_place_label,
    _format_result_display,
    _format_sectional_name,
    _format_sectional_result,
    _get_all_sectional_events_list,
    _get_event_types_map,
    _get_field_size,
    _get_sectional_events,
    _get_sectional_years,
    _ihsaa_sectional_hosts,
    _is_lower_better,
    _is_valid_postseason_mark,
    _normalize_name_text,
    _normalize_performance_input,
    _ordinal,
    _prior_season_status_for_best_mark,
    _project_place,
    _resolve_postseason_individual_rows,
    _resolve_school_enrollment_for_year,
    _safe_int,
    _school_logo_url,
    _schools_with_logos,
    _select_best_result_entry,
    _select_preferred_result,
    _state_target_field_size,
    _summarize_leaderboard,
    _tuple_or_none,
    _unique_events,
    _callback_group,
    _easier,
    _is_better,
    ensure_fresh_queries,
    estimate_event_rank,
    Any,
    Athlete,
    AthleteResult,
    CONST,
    CONVERSION,
    CURRENT_QUALIFIER_YEAR,
    Conversion,
    DEFAULT_PERCENTILES,
    Dict,
    Event,
    GRADE_LEVELS,
    List,
    MIN_RECORDS_YEAR,
    Meet,
    Optional,
    PEER_WINDOW_HALF,
    PERCENTILE_CHOICES,
    Path,
    REGIONAL_SECTIONAL_GROUPS,
    REGIONAL_TARGET_FIELD_SIZE,
    RelayResult,
    Request,
    SPRINT_DNQ_EVENTS,
    STATE_TARGET_FIELD_SIZE_BY_YEAR,
    School,
    SchoolEnrollment,
    Tuple,
    _FALLBACK_EVENTS,
    _FALLBACK_GENDERS,
    _H2H_INDIVIDUAL_POINTS,
    _H2H_RELAY_POINTS,
    _LAST_SEEN_DB,
    _PLACE_POINTS,
    _RELAY_NAME_DELIMITER,
    _SCHOOL_LOGO_DIR,
    _STATE_PLACE_POINTS,
    _AUTO_DEPTH,
    _CALLBACK_SLOTS,
    _EXPECTED_MEETS,
    _SECTIONALS_PER_REGIONAL,
    _STAGE_ORDER,
    _script_get_percentiles,
    and_,
    bisect,
    db,
    formatter,
    func,
    get_configured_regional_hosts,
    get_state_standard_display,
    handler,
    html_lib,
    joinedload,
    json,
    logger,
    logging,
    lru_cache,
    math,
    meets_state_standard,
    or_,
    os,
    re,
    sqlalchemy_text,
    statistics,
    sys,
    urljoin,
    urlopen,
)

from .meets import (  # noqa: F401
    _available_meet_years,
    _compute_cumulative_points,
    _compute_school_relay_results,
    _compute_stage_badge,
    _compute_team_scores_for_meet,
    _estimate_relay_rank,
    _extract_relay_names,
    _format_points_value,
    _format_stage_result,
    _missing_auto_slots_by_meet,
    _resolve_postseason_relay_rows,
    _score_h2h_meet,
    _serialize_history_stage,
    _serialize_stage_entries,
    _stage_cells,
    _stage_index,
)

from .qualifiers import (  # noqa: F401
    _compute_event_qualifiers,
    _extend_to_cutoff_with_ties,
    _format_school_qualifier_row,
    _ihsaa_regional_hosts,
    _qualifier_sort_key,
    _regional_events_for_gender,
    _regional_group_status,
    _regional_hosts_for_year,
    _state_group_status,
    _advancement_from_rows,
    get_regional_qualifiers,
    get_regional_qualifiers_status,
    get_state_qualifiers,
    get_state_qualifiers_status,
)

from .athletes import (  # noqa: F401
    _build_playoff_history,
    _compute_badges,
    _compute_sectional_badge,
    _fetch_relay_rows_for_athlete,
    _get_relay_result_rankings,
    _relay_entry_includes_athlete,
    add_athlete,
    get_athlete_by_id,
    get_athlete_dashboard_data,
    get_athlete_personal_bests,
    get_athlete_result_rankings,
    get_athletes,
    get_hypothetical_result_rankings,
)

from .school_dashboard import (  # noqa: F401
    _build_school_best_history,
    _default_season,
    _get_season_scope,
    _available_years,
    _covered_years,
    _event_groups,
    _events_for_gender,
    get_school_dashboard_data,
    get_school_season_core,
    get_school_qualifiers,
    get_stage_summary,
)

from .rankings import (  # noqa: F401
    _build_statewide_program_rankings,
    _normalize_rank_to_score,
    _group_ranks,
    _group_standings,
    _rank_baselines,
    _slots_filled,
    get_program_rank,
)

from .scorecard import (  # noqa: F401
    _individual_advancement,
    _event_mark_ranks,
    _event_ranked_rows,
    _relay_advancement,
    _relay_mark_ranks,
    _relay_ranked_rows,
    get_athlete_scorecard,
)

from .outlook import (  # noqa: F401
    _grades_for_season,
    _returning_points,
    _season_entries,
    get_returning_athletes,
    get_season_h2h,
)

from .percentiles import (  # noqa: F401
    _compute_school_percentiles,
    _format_percentile,
    _get_school_percentile_years,
    get_percentile_options,
    get_percentiles_report,
)

from .insights import (  # noqa: F401
    get_hypothetical_ranking_options,
    get_sectional_event_trends,
    get_sectional_event_trends_options,
)

from .search import (  # noqa: F401
    search_bar,
)
