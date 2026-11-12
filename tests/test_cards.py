"""Athlete cards: which results earn one, what it says, and how it is served."""
import os
import re

import pytest

from app.queries.cards import (
    accolade_for,
    card_id,
    card_result,
    cards_status,
    get_card_data,
    list_cards_for_athlete,
)
from app.services.school_colors import normalize_hex


theCardIdPattern = re.compile(r"^TI\d{2}-(SEC|REG|STA)-[0-9A-F]{4}$")


@pytest.mark.parametrize("meet_type,place,advanced,expected", [
    ("Sectional", 1, True, ("Sectional Champion", "Regional Qualifier")),
    ("Sectional", 2, True, ("Sectional Runner-Up", "Regional Qualifier")),
    ("Sectional", 3, True, ("Regional Qualifier", "")),
    ("Sectional", 5, True, ("Regional Qualifier", "")),
    ("Regional", 1, True, ("Regional Champion", "State Qualifier")),
    ("Regional", 2, True, ("Regional Runner-Up", "State Qualifier")),
    ("Regional", 3, True, ("State Qualifier", "")),
    ("State", 1, False, ("State Champion", "")),
    ("State", 2, False, ("State Runner-Up", "")),
    ("State", 3, False, ("State Medalist", "3rd in Indiana")),
    ("State", 6, False, ("State Medalist", "6th in Indiana")),
    ("State", 9, False, ("State Medalist", "9th in Indiana")),
])
def test_every_accolade_case(meet_type, place, advanced, expected):
    assert accolade_for(meet_type, place, advanced) == expected


@pytest.mark.parametrize("meet_type,place,advanced", [
    ("Sectional", 4, False),
    ("Regional", 7, False),
    ("State", 10, False),
    ("State", 0, False),
    ("Sectional", None, True),
])
def test_results_that_earn_no_card(meet_type, place, advanced):
    assert accolade_for(meet_type, place, advanced) is None


def test_card_id_format_and_stability():
    theFirst = card_id(101, 4, "100 Meters", 2024, "Sectional")
    theAgain = card_id(101, 4, "100 Meters", 2024, "Sectional")
    theOtherEvent = card_id(101, 4, "200 Meters", 2024, "Sectional")
    theState = card_id(101, 6, "100 Meters", 2024, "State")
    assert theCardIdPattern.match(theFirst)
    assert theFirst.startswith("TI24-SEC-")
    assert theFirst == theAgain
    assert theFirst != theOtherEvent
    assert theState.startswith("TI24-STA-")


@pytest.mark.parametrize("raw,expected", [
    ("5' 4\"", "5-4"),
    ("17' 3.75\"", "17-3.75"),
    ("34'2\"", "34-2"),
    ("7-2", "7-2"),
    ("4:58.69", "4:58.69"),
    ("44.59", "44.59"),
    (None, ""),
])
def test_card_result_reads_like_a_mark(raw, expected):
    assert card_result(raw) == expected


def test_normalize_hex():
    assert normalize_hex("#0033A0") == "#0033a0"
    assert normalize_hex("fff") == "#ffffff"
    assert normalize_hex("not a color") is None
    assert normalize_hex(None) is None


def test_athlete_cards_follow_the_fixture_results(app):
    with app.app_context():
        theCards = list_cards_for_athlete(101)
        theKeys = [(c["year"], c["meet_type"], c["event"], c["acc1"], c["acc2"], c["kind"]) for c in theCards]
        assert theKeys == [
            (2024, "Regional", "4 x 100 Relay", "Regional Champion", "State Qualifier", "accolade"),
            (2024, "Regional", "100 Meters", "State Qualifier", "", "accolade"),
            (2024, "Sectional", "100 Meters", "Regional Qualifier", "", "accolade"),
            (2023, "Sectional", "100 Meters", "Sectional Finalist", "10th Place", "season"),
        ]
        assert theCards[0]["cardId"].startswith("TI24-REG-")
        assert theCards[2]["school_name"] == "Alpha High"


def test_every_competitor_gets_a_season_card(app):
    with app.app_context():
        theCards = list_cards_for_athlete(105)
        assert len(theCards) == 1
        assert theCards[0]["acc1"] == "Sectional Finalist"
        assert theCards[0]["acc2"] == "10th Place"
        assert theCards[0]["result"] == "10:00.00"
        assert theCards[0]["kind"] == "season"


def test_a_season_with_an_accolade_gets_no_extra_season_card(app):
    with app.app_context():
        theCards = list_cards_for_athlete(111)
        assert len(theCards) >= 2
        assert all(c["year"] == 2024 and c["kind"] == "accolade" for c in theCards)


def test_stored_cards_db_is_read_when_it_matches_the_results(app, tmp_path):
    from app.jobs.precompute_cards import build_cards_db

    with app.app_context():
        thePath = str(tmp_path / "cards.db")
        app.config["CARDS_DB_PATH"] = thePath
        assert cards_status()["built"] is False
        theTotal = build_cards_db(thePath)
        assert theTotal > 0
        theStatus = cards_status()
        assert theStatus["built"] is True
        assert theStatus["stale"] is False
        assert theStatus["count"] == theTotal
        list_cards_for_athlete.cache_clear()
        theStored = list_cards_for_athlete(102)
        assert [c["acc1"] for c in theStored] == ["Regional Champion", "Regional Runner-Up", "Sectional Runner-Up"]
        assert theStored[1]["cardId"] == card_id(102, 5, "100 Meters", 2024, "Regional")


def test_a_fourth_place_who_ran_the_next_round_is_a_qualifier(app):
    with app.app_context():
        theCard = get_card_data(101, 4, "100 Meters")
        assert theCard is not None
        assert theCard["place"] == 4
        assert theCard["acc1"] == "Regional Qualifier"


def test_runner_up_gets_both_lines(app):
    with app.app_context():
        theCard = get_card_data(102, 4, "100 Meters")
        assert theCard["acc1"] == "Sectional Runner-Up"
        assert theCard["acc2"] == "Regional Qualifier"
        theRegional = get_card_data(102, 5, "100 Meters")
        assert theRegional["acc1"] == "Regional Runner-Up"
        assert theRegional["acc2"] == "State Qualifier"


def test_prelims_and_unknown_athletes_earn_nothing(app):
    with app.app_context():
        assert get_card_data(101, 6, "100 Meters") is None
        assert list_cards_for_athlete(999999) == []


def test_card_page_renders_the_approved_markup(client):
    theResponse = client.get("/card/102/4/100 Meters?design=B")
    assert theResponse.status_code == 200
    theHtml = theResponse.get_data(as_text=True)
    assert "Sectional<br>Runner-Up" in theHtml
    assert "Regional Qualifier" in theHtml
    assert "Blake<br>Sprinter" in theHtml
    assert "width:1080px;height:1350px" in theHtml
    assert "window.fitCardText" in theHtml
    assert theHtml.count("data-fit=") >= 6
    assert "/static/fonts/oswald-latin-700-normal.woff2" in theHtml
    theBlackout = client.get("/card/102/4/100 Meters?design=E")
    assert theBlackout.status_code == 200
    theBlackoutHtml = theBlackout.get_data(as_text=True)
    assert "background:#0b0b0f" in theBlackoutHtml
    assert "Sectional<br>Runner-Up" in theBlackoutHtml
    assert "#ff4d6d" not in theBlackoutHtml


@pytest.mark.parametrize("suffix,content_type", [
    ("", "text/html"),
    (".png", "image/png"),
    ("/share", "text/html"),
])
def test_card_routes_accept_event_names_left_encoded_by_the_host(client, suffix, content_type):
    # Some WSGI adapters leave percent escapes in PATH_INFO. The router still
    # matches, but the card lookup must receive the database's decoded event.
    path = "/card/102/4/100%20Meters" + suffix
    response = client.get(path, environ_overrides={"PATH_INFO": path})
    assert response.status_code == 200
    assert response.mimetype == content_type


def test_card_page_rejects_unknown_designs_and_missing_cards(client):
    assert client.get("/card/102/4/100 Meters?design=Z").status_code == 400
    assert client.get("/card/101/6/100 Meters").status_code == 404
    assert client.get("/card/999/4/100 Meters").status_code == 404


def test_cards_api_lists_urls_per_design(client):
    theResponse = client.get("/api/athletes/102/cards")
    assert theResponse.status_code == 200
    theCards = theResponse.get_json()["cards"]
    assert len(theCards) == 3
    theCard = theCards[2]
    assert theCard["meet_type"] == "Sectional"
    assert "?design=B&v=" in theCard["html_url"]["B"]
    assert ".png?design=E&v=" in theCard["png_url"]["E"]
    assert theCard["download_name"]["B"] == "blake-sprinter-2024-sectional-100-meters-b.png"
    assert client.get("/api/athletes/999/cards").status_code == 404


def test_card_png_is_rendered_in_memory_and_served(app, client):
    theResponse = client.get("/card/102/4/100 Meters.png?design=B")
    assert theResponse.status_code == 200
    assert theResponse.content_type == "image/png"
    from io import BytesIO
    from PIL import Image
    theImage = Image.open(BytesIO(theResponse.data))
    assert theImage.size == (1080, 1350)
    assert theResponse.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert "inline" in theResponse.headers["Content-Disposition"]
    theStatic = os.path.join(app.static_folder, "cards")
    assert not os.path.exists(theStatic)
    theAgain = client.get("/card/102/4/100 Meters.png?design=B&download=1")
    assert theAgain.status_code == 200
    assert theAgain.data == theResponse.data
    assert theAgain.headers["Content-Disposition"].startswith("attachment;")


def test_the_painter_has_everything_it_needs(app):
    from app.services.cards import paint_problem, thePaintFontFiles

    assert paint_problem() is None
    assert app.config["CARDS_RENDER_PROBLEM"] is None
    for theKey in thePaintFontFiles:
        assert os.path.isfile(os.path.join(app.static_folder, thePaintFontFiles[theKey])), theKey


def test_every_design_paints_without_a_browser(client):
    for theDesign in ("B", "E", "A"):
        theResponse = client.get("/card/102/4/100 Meters.png?design=" + theDesign)
        assert theResponse.status_code == 200, theDesign
        assert theResponse.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_long_names_split_on_first_and_last_not_the_first_space(app):
    from app.services.card_templates import nameLines, twoLines

    theCard = {"name": "Maria Antonia Vadell Perello", "first": "Maria Antonia", "last": "Vadell Perello"}
    assert nameLines(theCard) == "Maria Antonia<br>Vadell Perello"
    assert nameLines({"name": "Cher", "first": "Cher", "last": ""}) == "Cher"
    assert twoLines("State Runner-Up") == "State<br>Runner-Up"
    assert nameLines({"name": "A <b> B", "first": "A <b>", "last": "B"}) == "A &lt;b&gt;<br>B"


def test_a_final_with_no_time_falls_back_to_the_prelim_mark(app):
    from app import db
    from app.models import AthleteResult

    with app.app_context():
        theFinal = db.session.get(AthleteResult, (103, 4, "200 Meters", "Final"))
        theFinal.result = "NT"
        theFinal.result2 = 9999
        db.session.add(AthleteResult(athlete_id=103, meet_id=4, event="200 Meters", result_type="Prelim",
                                     result="22.31", result2=22.31, place=1, grade="SR"))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCard = get_card_data(103, 4, "200 Meters")
        assert theCard["acc1"] == "Sectional Champion"
        assert theCard["result"] == "22.31"


def test_an_athlete_with_no_school_still_gets_a_card(app, client):
    from app import db
    from app.models import Athlete, AthleteResult

    with app.app_context():
        db.session.add(Athlete(athlete_id=901, first="Solo", last="Runner", school_id=None, gender="Boys", graduation_year=2026))
        db.session.add(AthleteResult(athlete_id=901, meet_id=4, event="400 Meters", result_type="Final",
                                     result="52.10", result2=52.1, place=1, grade="JR"))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCard = get_card_data(901, 4, "400 Meters")
        assert theCard["acc1"] == "Sectional Champion"
        assert theCard["school_id"] is None
        assert theCard["school_name"] == ""
    theResponse = client.get("/card/901/4/400 Meters?design=B")
    assert theResponse.status_code == 200
    theHtml = theResponse.get_data(as_text=True)
    assert "school_logos" not in theHtml
    assert "Solo<br>Runner" in theHtml


def test_a_prelims_only_sprinter_gets_a_competitor_card(app):
    from app import db
    from app.models import Athlete, AthleteResult

    with app.app_context():
        db.session.add(Athlete(athlete_id=902, first="Pre", last="Lim", school_id=2, gender="Boys", graduation_year=2026))
        db.session.add(AthleteResult(athlete_id=902, meet_id=4, event="100 Meters", result_type="Prelim",
                                     result="11.90", result2=11.9, place=14, grade="SO"))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCards = list_cards_for_athlete(902)
        assert len(theCards) == 1
        assert theCards[0]["acc1"] == "Sectional Competitor"
        assert theCards[0]["acc2"] == ""
        assert theCards[0]["result"] == "11.90"
        assert theCards[0]["kind"] == "season"


def test_a_relay_only_athlete_gets_the_relay_card_through_the_link_table(app, client):
    from app import db
    from app.models import Athlete, RelayAthlete

    with app.app_context():
        db.session.add(Athlete(athlete_id=903, first="Relay", last="Only", school_id=1, gender="Boys", graduation_year=2026))
        db.session.add(RelayAthlete(relay_id=2, athlete_id=903))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCards = list_cards_for_athlete(903)
        assert [(c["event"], c["acc1"]) for c in theCards] == [("4 x 100 Relay", "Regional Champion")]
    theResponse = client.get("/api/athletes/903/cards")
    assert theResponse.status_code == 200
    assert len(theResponse.get_json()["cards"]) == 1


def test_an_athlete_with_no_results_or_relays_has_no_cards(app, client):
    from app import db
    from app.models import Athlete

    with app.app_context():
        db.session.add(Athlete(athlete_id=906, first="Never", last="Raced", school_id=1, gender="Boys", graduation_year=2026))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        assert list_cards_for_athlete(906) == []
    assert client.get("/api/athletes/906/cards").get_json() == {"cards": [], "problem": None}


def test_design_parameter_is_case_insensitive(client):
    assert client.get("/card/102/4/100 Meters?design=b").status_code == 200
    assert client.get("/card/102/4/100 Meters?design=e").status_code == 200
    assert client.get("/card/102/4/100 Meters").status_code == 200


def test_cards_come_newest_season_and_latest_round_first(app):
    with app.app_context():
        theCards = list_cards_for_athlete(101)
        theOrder = [(c["year"], c["meet_type"], c["place"]) for c in theCards]
        assert theOrder == [(2024, "Regional", 1), (2024, "Regional", 3), (2024, "Sectional", 4), (2023, "Sectional", 10)]


def test_a_stale_cards_db_is_ignored_in_favour_of_live_results(app, tmp_path):
    from app import db
    from app.jobs.precompute_cards import build_cards_db
    from app.models import AthleteResult

    with app.app_context():
        thePath = str(tmp_path / "cards.db")
        app.config["CARDS_DB_PATH"] = thePath
        build_cards_db(thePath)
        assert cards_status()["stale"] is False
        theResult = db.session.get(AthleteResult, (102, 4, "100 Meters", "Final"))
        theResult.place = 1
        db.session.commit()
        db.engine.dispose()
        list_cards_for_athlete.cache_clear()
        theStatus = cards_status()
        assert theStatus["built"] is True
        assert theStatus["stale"] is True
        theCard = get_card_data(102, 4, "100 Meters")
        assert theCard["acc1"] == "Sectional Champion"


def test_card_ids_carry_the_season_and_round(app):
    with app.app_context():
        theCards = list_cards_for_athlete(101)
        theIds = [c["cardId"][:8] for c in theCards]
        assert theIds == ["TI24-REG", "TI24-REG", "TI24-SEC", "TI23-SEC"]


def test_relay_legs_earn_cards_too(app):
    with app.app_context():
        list_cards_for_athlete.cache_clear()
        theRelayCards = [c for c in list_cards_for_athlete(111) if "Relay" in c["event"]]
        theKeys = [(c["year"], c["meet_type"], c["event"], c["acc1"], c["acc2"]) for c in theRelayCards]
        assert theKeys == [
            (2024, "Sectional", "4 x 400 Relay", "Sectional Champion", "Regional Qualifier"),
        ]
        assert theRelayCards[0]["result"] == "4:05.00"
        assert theRelayCards[0]["cardId"].startswith("TI24-SEC-")
        assert theRelayCards[0]["kind"] == "accolade"


def test_a_relay_only_athlete_gets_a_relay_card(app):
    from app import db
    from app.models import Athlete

    with app.app_context():
        db.session.add(Athlete(athlete_id=904, first="Relay", last="Four", school_id=1, gender="Girls", graduation_year=2026))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCards = list_cards_for_athlete(904)
        assert len(theCards) >= 1
        assert all("Relay" in c["event"] for c in theCards)


def test_a_relay_leg_linked_by_id_counts_even_when_the_roster_misspells_the_name(app):
    from app import db
    from app.models import Athlete, RelayAthlete, RelayResult

    with app.app_context():
        theRelay = db.session.query(RelayResult).filter_by(school_id=1, meet_id=14, event="4 x 400 Relay").one()
        theRowId = db.session.execute(db.text(
            "select rowid from relay_result where school_id=1 and meet_id=14 and event='4 x 400 Relay'")).scalar()
        db.session.add(Athlete(athlete_id=905, first="Misspelt", last="Runner", school_id=1, gender="Girls", graduation_year=2026))
        db.session.add(RelayAthlete(relay_id=theRowId, athlete_id=905))
        db.session.commit()
        list_cards_for_athlete.cache_clear()
        theCards = list_cards_for_athlete(905)
        assert [(c["event"], c["acc1"]) for c in theCards] == [("4 x 400 Relay", "Sectional Champion")]
        assert theCards[0]["result"] == theRelay.result


def test_a_linked_relay_from_the_other_gender_is_ignored(app):
    with app.app_context():
        list_cards_for_athlete.cache_clear()
        theCards = list_cards_for_athlete(112)
        assert all("4 x 100" not in c["event"] for c in theCards)


def test_share_page_carries_the_card_image_and_snapchat_sticker_tags(client):
    theResponse = client.get("/card/102/4/100 Meters/share?design=B")
    assert theResponse.status_code == 200
    theHtml = theResponse.get_data(as_text=True)
    assert 'property="og:image" content="http://localhost/card/102/4/100%20Meters.png?design=B"' in theHtml
    assert 'property="snapchat:sticker" content="http://localhost/card/102/4/100%20Meters/sticker.png?design=B"' in theHtml
    assert "Add to Instagram Story" in theHtml
    assert "Send to Snapchat" in theHtml
    assert "Blake Sprinter" in theHtml
    assert "Sectional Runner-Up" in theHtml
    assert client.get("/card/102/4/100 Meters/share?design=Z").status_code == 400
    assert client.get("/card/101/6/100 Meters/share").status_code == 404


def test_cards_api_includes_a_share_url_per_design(client):
    theCards = client.get("/api/athletes/102/cards").get_json()["cards"]
    assert theCards[0]["share_url"]["B"].endswith("/share?design=B")
    assert theCards[0]["share_url"]["E"].startswith("http://localhost/card/")


def test_sticker_is_a_square_transparent_png(app, client):
    theResponse = client.get("/card/102/4/100 Meters/sticker.png?design=B")
    assert theResponse.status_code == 200
    from io import BytesIO
    from PIL import Image

    theImage = Image.open(BytesIO(theResponse.data))
    assert theImage.size == (400, 400)
    assert theImage.mode == "RGBA"
    assert theImage.getpixel((2, 200))[3] == 0
    assert theImage.getpixel((200, 200))[3] == 255
    assert len(theResponse.data) < 1000000


def test_a_rebuilt_cards_db_is_picked_up_without_a_restart(app, tmp_path):
    import os
    import sqlite3
    from app.jobs.precompute_cards import build_cards_db

    with app.app_context():
        thePath = str(tmp_path / "cards.db")
        app.config["CARDS_DB_PATH"] = thePath
        build_cards_db(thePath)
        list_cards_for_athlete.cache_clear()
        assert list_cards_for_athlete(102)[0]["acc1"] == "Regional Champion"
        theConnection = sqlite3.connect(thePath)
        theConnection.execute("update card set acc1 = 'Rebuilt Label' where athlete_id = 102 and sort_order = 0")
        theConnection.commit()
        theConnection.close()
        theStat = os.stat(thePath)
        os.utime(thePath, ns=(theStat.st_atime_ns, theStat.st_mtime_ns + 1000000))
        assert list_cards_for_athlete(102)[0]["acc1"] == "Rebuilt Label"


def test_centered_design_renders_the_slanted_band(client):
    theResponse = client.get("/card/102/4/100 Meters?design=A")
    assert theResponse.status_code == 200
    theHtml = theResponse.get_data(as_text=True)
    assert "rotate(-2.5deg)" in theHtml
    assert "&#9733;" in theHtml
    assert "Sectional<br>Runner-Up" in theHtml
    assert "Regional Qualifier" in theHtml
    theCards = client.get("/api/athletes/102/cards").get_json()["cards"]
    assert set(theCards[0]["html_url"]) == {"A", "B", "E"}
    assert theCards[0]["download_name"]["A"].endswith("-a.png")
    assert client.get("/card/102/4/100 Meters?design=a").status_code == 200


def test_glow_color_keeps_the_school_hue_on_black():
    from app.services.school_colors import glow_color

    assert glow_color("#1b2a57", "#f0d010") == "#f0d010"
    theRed = glow_color("#9e0e0e", "#ffffff")
    assert theRed != "#ffffff"
    assert int(theRed[1:3], 16) > 150 and int(theRed[3:5], 16) < 60
    assert glow_color("#111111", "#ffffff") == "#ffffff"
    assert glow_color("#1b2a57", "#ffffff") != "#ffffff"


def test_black_schools_get_a_light_school_color_card():
    from app.services.card_templates import designRail, designBlackout

    theCard = {
        "name": "JACOB COLE", "first": "JACOB", "last": "COLE", "gender": "Boys", "event": "100 Meters",
        "result": "11.20", "acc1": "Sectional Champion", "acc2": "Regional Qualifier", "cardId": "TI26-SEC-0000",
        "year": 2026, "school": {"name": "Rossville", "primary": "#111111", "accent": "#9e9e3f", "glow": "#9e9e3f", "logo": None, "logoWhite": None},
    }
    theAssets = {"tiLogo": "ti.png"}
    theRail = designRail(theCard, theAssets)
    theBlackout = designBlackout(theCard, theAssets)
    assert "overflow:hidden;background:#9e9e3f;" in theRail
    assert "overflow:hidden;background:#0b0b0f;" in theBlackout
    assert "color:#111111;text-transform:uppercase" in theRail
    theCard["school"]["accent"] = "#ffffff"
    theCard["school"]["glow"] = "#ffffff"
    assert "overflow:hidden;background:#f2f2f3;" in designRail(theCard, theAssets)


def test_the_cards_api_reports_a_painter_problem(client, app):
    theResponse = client.get("/api/athletes/102/cards")
    assert theResponse.status_code == 200
    assert theResponse.get_json()["problem"] is None
    app.config["CARDS_RENDER_PROBLEM"] = "Pillow and numpy are not installed; run pip install Pillow numpy"
    theAgain = client.get("/api/athletes/102/cards")
    assert theAgain.get_json()["problem"] == "Pillow is not installed on this server; run pip install Pillow numpy and restart"
    app.config["CARDS_RENDER_PROBLEM"] = "card assets could not be loaded (cannot open resource /srv/secret/path.ttf)"
    theThird = client.get("/api/athletes/102/cards").get_json()["problem"]
    assert "/srv" not in theThird and "cannot open" not in theThird
