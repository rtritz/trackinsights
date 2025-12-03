from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checkers only
    import pandas as pd  # type: ignore[import]
else:  # pragma: no cover - runtime import occurs lazily in get_pandas
    pd = None  # type: ignore[assignment]

def get_pandas():
    global pd  # type: ignore[assignment]
    if pd is None:
        import pandas  # type: ignore[import]

        pd = pandas
    return pd

from backend.util.db_util import Database
from backend.util.conversion_util import Conversion

# function that figures out which place a performance mark would be in a particular meet
def get_place(df, event, result, track_field):
    # marks True if the entered mark is better and False if the mark is worse than each result2... used later in the function
    if track_field == "Track":
        modified = df["result2"] < result
    elif track_field == "Field":
        modified = df["result2"] > result

    # finds the first instance where the mark is worse and returns that index + 1 (place value it would be)
    for i, is_valid in enumerate(modified):
        if not is_valid:
            return str(i + 1)

    # if worse than all finals results, they either DNQ for 1 of the 4 events below or would return the last place value + 1
    if event in ["100 Meters", "200 Meters", "100 Hurdles", "110 Hurdles"]:
        return "DNQ for Finals"
    else:
        return str(len(df) + 1)


db = Database("data/Track.db")
conv = Conversion()

gender = input("Enter gender (e.g. Girls or Boys): ")
year = int(input("Enter year (e.g. 2024): "))

events = ["100 Meters", "200 Meters", "400 Meters", "800 Meters", "1600 Meters", "3200 Meters", "100 Hurdles", "110 Hurdles", "300 Hurdles", "High Jump", "Long Jump", "Shot Put", "Discus", "Pole Vault"]

# printing the options with a number corresponding to each option
for i, option in enumerate(events, 1):
    print(f"{i}. {option}")

# user types in a number that corresponds to their event and program stores the corresponding event as a variable
choice = int(input("Enter the number of your event: "))
selected_event = events[choice - 1]
event_type = db.get_event_type(selected_event) # seeing if a track or field event
performance = 0.0

# user types in their performance mark based on if a track or field event
# input statements should make it fairly straightforward and it also converts to seconds/inches so it matches with result2
if(event_type == "Track"):
    temp = input("\nEnter your time (e.g. 2:05.42 or 27.23): ")
    performance = float(conv.time_to_seconds(temp))
elif(event_type == "Field"):
    print("\nEnter your distance (enter in feet and inches separately as prompted)")
    feet = input("Feet (whole number like 1, 2, etc.): ")
    inches = input("Inches (e.g. 3.5 or 11.75): ")
    temp = f"{feet}' {inches}\""
    performance = float(conv.distance_to_inches(temp))

# pull all athletes from database and filter out according to desired selections and all placed athletes (no dqs, dnfs, etc)
pandas = get_pandas()
athletes = pandas.DataFrame(db.get_all_athlete_results())
athletes = athletes[(athletes["event"] == selected_event) & (athletes["meet_type"] == "Sectional") & (athletes["year"] == year) & (athletes["result_type"] == "Final") & (athletes["gender"] == gender)]
athletes = athletes[athletes['place'].notna()]