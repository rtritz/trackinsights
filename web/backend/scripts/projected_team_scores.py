from datetime import datetime
import pandas as pd

from util.db_util import Database
from util.const_util import CONST


NOT_READY_MESSAGE = "Projected scores for the selected filters is not ready yet. Please check back later."

REGIONAL_POINTS = {
    1: 10,
    2: 8,
    3: 6,
    4: 5,
    5: 4,
    6: 3,
    7: 2,
    8: 1,
}

STATE_POINTS = {
    1: 10,
    2: 8,
    3: 7,
    4: 6,
    5: 5,
    6: 4,
    7: 3,
    8: 2,
    9: 1,
}


def get_available_projected_score_seasons(start_year=2023):
    current_year = datetime.now().year
    return list(range(start_year, current_year + 1))


def _not_ready_df():
    return pd.DataFrame({"Message": [NOT_READY_MESSAGE]})


def _get_feeder_meets_for_projection(meet_type, meet_num):
    if meet_type == CONST.MEET_TYPE.REGIONAL:
        if meet_num is None or meet_num < 1 or meet_num > 8:
            return None
        start_sectional = ((meet_num - 1) * 4) + 1
        return CONST.MEET_TYPE.SECTIONAL, list(range(start_sectional, start_sectional + 4))

    if meet_type == CONST.MEET_TYPE.STATE:
        return CONST.MEET_TYPE.REGIONAL, list(range(1, 9))

    return None


def _is_track_like_event(event_name):
    return event_name[0].isdigit()


def _average_points_for_tie(start_place, tie_count, points_by_place):
    total_points = 0
    for offset in range(tie_count):
        total_points += points_by_place.get(start_place + offset, 0)
    return total_points / tie_count


def _score_event(event_df, points_by_place, ascending):
    scores = {}

    sorted_event_df = event_df.sort_values(by="result2", ascending=ascending).copy()
    sorted_event_df["place"] = sorted_event_df["result2"].rank(method="min", ascending=ascending).astype(int)
    place_counts = sorted_event_df["place"].value_counts()

    for _, row in sorted_event_df.iterrows():
        school_id = int(row["school_id"])
        place = int(row["place"])
        tie_count = int(place_counts[place])
        points = _average_points_for_tie(place, tie_count, points_by_place)
        scores[school_id] = scores.get(school_id, 0) + points

    return scores


def _merge_scores(total_scores, partial_scores):
    for school_id, score in partial_scores.items():
        total_scores[school_id] = total_scores.get(school_id, 0) + score


def _build_scores_dataframe(scores, db):
    if not scores:
        return _not_ready_df()

    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    df = pd.DataFrame(sorted_scores, columns=["school_id", "Score"])
    df = df[df["Score"] > 0].copy()
    if df.empty:
        return _not_ready_df()
    df["Place"] = df["Score"].rank(method="min", ascending=False).astype(int)
    df["Team"] = df["school_id"].apply(db.get_school_name)
    df["Score"] = df["Score"].round(2)

    result = df[["Place", "Team", "Score"]].sort_values(by=["Place", "Team"]).reset_index(drop=True)
    return result


def get_projected_team_scores(meet_type, year, gender, meet_num=None):
    """
    Calculate projected team scores by recomputing meet scoring from sectional performances.

    Parameters:
        meet_type (str): "Regional" or "State".
        year (int): Season year. Supported filter years are 2023 through current year.
        gender (str): "Boys" or "Girls".
        meet_num (int or None): Regional number (1-8) when meet_type is "Regional".

    Returns:
        pd.DataFrame: DataFrame with columns [Place, Team, Score] when available,
                      otherwise a DataFrame with one "Message" row indicating data is not ready.
    """
    if meet_type not in (CONST.MEET_TYPE.REGIONAL, CONST.MEET_TYPE.STATE):
        return _not_ready_df()

    if gender not in CONST.GENDER.ALL:
        return _not_ready_df()

    if year not in get_available_projected_score_seasons():
        return _not_ready_df()

    feeder_config = _get_feeder_meets_for_projection(meet_type, meet_num)
    if feeder_config is None:
        return _not_ready_df()
    feeder_meet_type, feeder_meet_nums = feeder_config

    points_by_place = REGIONAL_POINTS if meet_type == CONST.MEET_TYPE.REGIONAL else STATE_POINTS

    db = Database(CONST.DB_PATH)
    individual_results = db.get_all_athlete_results()
    relay_results = db.get_all_relay_results()

    individual_filtered = individual_results[
        (individual_results["meet_type"] == feeder_meet_type) &
        (individual_results["meet_num"].isin(feeder_meet_nums)) &
        (individual_results["year"] == year) &
        (individual_results["gender"] == gender) &
        (individual_results["result_type"] == CONST.RESULT_TYPE.FINAL) &
        (individual_results["result2"] != 0) &
        (individual_results["result2"] != 9999)
    ]

    relay_filtered = relay_results[
        (relay_results["meet_type"] == feeder_meet_type) &
        (relay_results["meet_num"].isin(feeder_meet_nums)) &
        (relay_results["year"] == year) &
        (relay_results["gender"] == gender) &
        (relay_results["result2"] != 0) &
        (relay_results["result2"] != 9999)
    ]

    if individual_filtered.empty and relay_filtered.empty:
        return _not_ready_df()

    scores = {}

    for event in individual_filtered["event"].dropna().unique():
        event_df = individual_filtered[individual_filtered["event"] == event][["school_id", "result2"]]
        if event_df.empty:
            continue
        partial_scores = _score_event(
            event_df,
            points_by_place=points_by_place,
            ascending=_is_track_like_event(event),
        )
        _merge_scores(scores, partial_scores)

    for event in relay_filtered["event"].dropna().unique():
        event_df = relay_filtered[relay_filtered["event"] == event][["school_id", "result2"]]
        if event_df.empty:
            continue
        partial_scores = _score_event(
            event_df,
            points_by_place=points_by_place,
            ascending=_is_track_like_event(event),
        )
        _merge_scores(scores, partial_scores)

    return _build_scores_dataframe(scores, db)
