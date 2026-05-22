# ---------------------------------------------------------------------------
# Athlete interview video configuration
# ---------------------------------------------------------------------------
# To add a new interview, append a dict to INTERVIEW_VIDEOS:
#   youtube_id  – the 11-character YouTube video ID (from the watch?v= URL)
#   title       – display title for the card
#   athlete_name – full name as it should appear on the page
#   athlete_id  – integer DB athlete_id, or None if not linked to a profile
#   school      – school name string
#   event       – primary event (e.g. "1600 Meters")
#   year        – interview year (int)
#   description – 1-2 sentence blurb shown on the card
# ---------------------------------------------------------------------------

INTERVIEW_VIDEOS = [
    { 
        "youtube_id": "e_T8IFLk5OY",
        "title": " Mallory Weller Interview",
        "athlete_name": "Mallory Weller",
        "athlete_id": 291895,
        "school": "Ft. Wayne Concordia Lutheran HS",
        "event": "Distance",
        "year": 2026,
        "description": "Mallory Weller, a standout distance runner from Ft. Wayne Concordia Lutheran HS, shares her running journey with us.",
    },

        { 
        "youtube_id": "Rxy_l8pqRZo ",
        "title": "Noah Bontrager Interview",
        "athlete_name": "Noah Bontrager",
        "athlete_id": 297373,
        "school": "Westview HS",
        "event": "Distance",
        "year": 2026,
        "description": "We sat down with Westview HS distance runner Noah Bontrager to talk all things running — from training to racing to goals!"
    },
]
