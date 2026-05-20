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
    # { 
    #     "youtube_id": "QQk0jn3UQcE",
    #     "title": "Interview with Jane Smith",
    #     "athlete_name": "Jane Smith",
    #     "athlete_id": 302793,
    #     "school": "Indianapolis Cathedral",
    #     "event": "1600 Meters",
    #     "year": 2026,
    #     "description": "We sat down with Jane to talk about her record-breaking season and goals for state.",
    # },
]
