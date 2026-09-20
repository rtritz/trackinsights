"""Percentile tables, computed from every result in the database.

Named percentile_tables rather than percentiles so it is distinct from
``app.queries.percentiles``, which is the feature layer above it -- that one
answers the percentile pages, this one does the arithmetic.

Takes the database connection as an argument rather than importing the Flask
app's ``db`` to fetch one. This package is the bottom of the stack -- queries and
routes call into it, it calls into nothing above it -- and an import back up to
``app.db`` made that a cycle, which is why it had to be written inside the
function to work at all. Handing the connection in keeps the direction of
dependency one-way, and lets this run against any connection: the app's, a
notebook's, or a test's.
"""
import pandas as pd

from common.const import CONST
from common.db import ALL_ATHLETE_RESULTS_SQL, ALL_RELAY_RESULTS_SQL


def convert_back(event_type, event_result):
    if event_type == CONST.EVENT_TYPE.FIELD:
        feet = int(event_result // 12)
        inches = event_result - (feet * 12)
        return str(feet) + "'" + " " + '{:g}'.format(inches) + "\""
    else:
        minutes = int(event_result // 60)
        seconds = event_result - (minutes * 60)

        if minutes == 0:
            return "{:.2f}".format(seconds)
        else:
            if seconds < 10:
                return str(minutes) + ":0" + "{:.2f}".format(seconds)
            else:
                return str(minutes) + ":" + "{:.2f}".format(seconds)


def get_percentiles(
    connection,                 # DBAPI/SQLAlchemy connection to read the results through.
    events=None,                # tuple of events to include in results. None means all events.
    genders=None,               # tuple of genders to include in results. None means both Boys and Girls.
    percentiles=(25, 50, 75),   # tuple of percentiles to include in results.
    years=None,                 # tuple of years to include in calculation, or None
    meet_types=None,            # tuple of meet types to include in calculation, or None
    grade_levels=None           # tuple of grade levels to include in calculation, or None
):
    """
    Returns percentile data for track & field events.

    Parameters:
         connection: An open database connection to read through. The web app
             passes its own (``db.session.connection()``) so the read is inside
             the request's transaction and the freshness check can account for
             it; a notebook or script can pass ``common.db.Database``'s.
         events (tuple[str] or None): Events to include in results. None means all events.
         genders (tuple[str] or None): Genders to include in results. None means both Boys and Girls.
         percentiles (tuple[int]): Percentiles to include in results.
         years (tuple[int] or None): Years of data used in percentile calculations. None means all years.
         meet_types (tuple[str] or None): Meet types used in percentile calculations. None means all meet types.
         grade_levels (tuple[str] or None): Grade levels (only applied to individual events) used in percentile calculations. None means all grade levels.

    Notes:
        - `events`, `genders`, and `percentiles` indicate what to include in results.
        - `years`, `meet_types`, and `grade_levels` indicate what to include in percentile calculation. Percentiles are aggregated across all selected years, meet types, and grade levels, not split by them.

    Returns:
        DataFrame or tuple[DataFrame, DataFrame]: Single DataFrame if one gender specified, otherwise tuple of (Girls DataFrame, Boys DataFrame).
    """
    df = pd.read_sql_query(ALL_ATHLETE_RESULTS_SQL, connection)
    df_relay = pd.read_sql_query(ALL_RELAY_RESULTS_SQL, connection)

    # Default values
    if genders is None:
        gender_list = [CONST.GENDER.GIRLS, CONST.GENDER.BOYS]
    else:
        gender_list = list(genders)

    if events is None:
        event_list = [
            CONST.EVENT.E100, CONST.EVENT.E200, CONST.EVENT.E400, CONST.EVENT.E800, CONST.EVENT.E1600, CONST.EVENT.E3200,
            CONST.EVENT.E110H, CONST.EVENT.E300H,
            CONST.EVENT.E400R, CONST.EVENT.E1600R, CONST.EVENT.E3200R,
            CONST.EVENT.EHJ, CONST.EVENT.ELJ, CONST.EVENT.EDT, CONST.EVENT.ESP, CONST.EVENT.EPV
        ]
    else:
        event_list = list(events)

    # Convert percentiles to decimal format
    percentile_decimals = [p / 100.0 for p in percentiles]

    all_rows = []
    sample_counts = {}  # Track sample sizes per gender/event
    for event_gender in gender_list:
        for event_name in event_list:
            # Girls 110 Hurdles is actually 100 Hurdles
            current_event = event_name
            display_event = event_name
            if event_gender == CONST.GENDER.GIRLS and event_name == CONST.EVENT.E110H:
                current_event = CONST.EVENT.E100H
                display_event = CONST.EVENT.E100H
            # Select appropriate dataframe (relay vs individual)
            if CONST.EVENT_TYPE.RELAY in current_event:
                df_source = df_relay
            else:
                df_source = df
            # Build filter conditions
            conditions = (
                (df_source.event == current_event) &
                (df_source.gender == event_gender) &
                (df_source.result2 != 0) &
                (df_source.result2 != 9999)
            )
            if meet_types is not None:
                conditions &= df_source.meet_type.isin(meet_types)
            if years is not None:
                conditions &= df_source.year.isin(years)
            if grade_levels is not None and CONST.EVENT_TYPE.RELAY not in current_event:
                conditions &= df_source.grade.isin(grade_levels)
            df2 = df_source[conditions]
            if df2.empty:
                continue

            # Determine if this is a track event (lower is better) or field event (higher is better)
            if current_event[0].isdigit():
                event_type = CONST.EVENT_TYPE.TRACK
                # For track events, get the minimum (best) time per athlete
                if CONST.EVENT_TYPE.RELAY in current_event:
                    # For relays, group by school_id instead of athlete_id
                    best_per_athlete = df2.groupby('school_id')['result2'].min()
                else:
                    best_per_athlete = df2.groupby('athlete_id')['result2'].min()
                track_percentiles = [1 - x for x in percentile_decimals]
                df3 = best_per_athlete.quantile(track_percentiles)
            else:
                event_type = CONST.EVENT_TYPE.FIELD
                # For field events, get the maximum (best) distance/height per athlete
                best_per_athlete = df2.groupby('athlete_id')['result2'].max()
                df3 = best_per_athlete.quantile(percentile_decimals)

            # Store sample count (unique athletes/teams, not total records)
            sample_counts[(event_gender, display_event)] = len(best_per_athlete)

            percentile_values = [convert_back(event_type, df3.iloc[i]) for i in range(len(percentiles))]
            # Add a row for each event/gender
            all_rows.append([event_gender, display_event] + percentile_values)
    # Build final DataFrame
    columns = ['Gender', 'Event'] + list(percentiles)
    final_df = pd.DataFrame(all_rows, columns=columns)
    # Sort: Boys first, then Girls, then by event name
    final_df['Gender_sort'] = final_df['Gender'].apply(lambda g: 0 if g == CONST.GENDER.BOYS else 1)
    final_df = final_df.sort_values(['Gender_sort', 'Event']).drop(columns=['Gender_sort']).reset_index(drop=True)
    # Add sample_count column to the dataframe
    final_df['sample_count'] = final_df.apply(
        lambda row: sample_counts.get((row['Gender'], row['Event']), 0), axis=1
    )
    return final_df
