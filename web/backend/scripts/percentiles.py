import pandas as pd
from util.db_util import Database
from util.const_util import CONST


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
    # Initialize database connection and load data
    db = Database(CONST.DB_PATH)
    df = db.get_all_athlete_results()
    df_relay = db.get_all_relay_results()
    
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
            if current_event[0].isdigit():
                event_type = CONST.EVENT_TYPE.TRACK
                track_percentiles = [1 - x for x in percentile_decimals]
                df3 = df2['result2'].quantile(track_percentiles)
            else:
                event_type = CONST.EVENT_TYPE.FIELD
                df3 = df2['result2'].quantile(list(reversed(percentile_decimals)))
            percentile_values = [convert_back(event_type, df3.iloc[i]) for i in range(len(percentiles))]
            # Add a row for each event/gender
            all_rows.append([event_gender, display_event] + percentile_values)
    # Build final DataFrame
    columns = ['Gender', 'Event'] + list(percentiles)
    final_df = pd.DataFrame(all_rows, columns=columns)
    # Sort: Boys first, then Girls, then by event name
    final_df['Gender_sort'] = final_df['Gender'].apply(lambda g: 0 if g == CONST.GENDER.BOYS else 1)
    final_df = final_df.sort_values(['Gender_sort', 'Event']).drop(columns=['Gender_sort']).reset_index(drop=True)
    return final_df




