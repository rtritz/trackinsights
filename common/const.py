import os


class CONST:
    """A class to store application constants with IntelliSense support."""

    class GENDER:
        BOYS = "Boys"
        GIRLS = "Girls"
        ALL = [BOYS, GIRLS]

    class MEET_TYPE:
        SECTIONAL = "Sectional"
        REGIONAL = "Regional"
        STATE = "State"
        ALL = [SECTIONAL, REGIONAL, STATE]

    class RESULT_TYPE:
        PRELIM = "Prelim"
        FINAL = "Final"
        ALL = [PRELIM, FINAL]

    class EVENT_TYPE:
        PRELIM = "Prelim"
        HURDLE = "Hurdle"
        RELAY = "Relay"
        FIELD = "Field"
        TRACK = "Track"

    class EVENT:
        # Track
        E100 = "100 Meters"
        E200 = "200 Meters"
        E400 = "400 Meters"
        E800 = "800 Meters"
        E1600 = "1600 Meters"
        E3200 = "3200 Meters"
        ALL_TRACK = [E100, E200, E400, E800, E1600, E3200]

        # Hurdles
        E100H = "100 Hurdles"
        E110H = "110 Hurdles"
        E300H = "300 Hurdles"
        ALL_GIRLS_HURDLES = [E100H, E300H]
        ALL_BOYS_HURDLES = [E110H, E300H]

        # Field
        EHJ = "High Jump"
        ELJ = "Long Jump"
        ESP = "Shot Put"
        EDT = "Discus"
        EPV = "Pole Vault"
        ALL_FIELD = [EHJ, ELJ, ESP, EDT, EPV]

        # Relay
        E400R = "4 x 100 Relay"
        E1600R = "4 x 400 Relay"
        E3200R = "4 x 800 Relay"
        ALL_RELAY = [E400R, E1600R, E3200R]

        ALL_GIRLS_PRELIM = [E100, E200, E100H]
        ALL_BOYS_PRELIM = [E100, E200, E110H]
        ALL_GIRLS_EVENTS = [ALL_TRACK, ALL_FIELD, ALL_RELAY, ALL_GIRLS_HURDLES]
        ALL_BOYS_EVENTS = [ALL_TRACK, ALL_FIELD, ALL_RELAY, ALL_BOYS_HURDLES]

    # File paths — cwd-independent: resolved from this file's own location
    # (common/const.py -> common/ -> repo root -> web/data/Track.db), so it
    # works the same whether invoked from the Flask app, a notebook, or a
    # standalone script run from any directory.
    _COMMON_DIR = os.path.dirname(os.path.abspath(__file__))
    _REPO_ROOT = os.path.dirname(_COMMON_DIR)
    # Two layouts have to work. In the repo, common/ sits beside web/. A
    # deployment that copies web/. into the app root and common/ next to it
    # leaves backend/ and frontend/ directly beside common/, with no web/ at
    # all -- so "<root>/web" is the right answer only when it actually exists.
    # Getting this wrong is quiet rather than loud: Flask reads its database URI
    # from config.py, so the app serves pages normally while every CONST-derived
    # path points into a directory that is not there.
    _WEB_DIR_CANDIDATE = os.path.join(_REPO_ROOT, "web")
    WEB_DIR = (_WEB_DIR_CANDIDATE if os.path.isdir(_WEB_DIR_CANDIDATE)
               else _REPO_ROOT)
    DB_PATH = os.path.join(WEB_DIR, "data", "Track.db")
    OUTPUT_PATH = os.path.join(_REPO_ROOT, "output")

    # School logos live at web/frontend/static/<SCHOOL_LOGO_STATIC_SUBDIR>/<school_id>.<SCHOOL_LOGO_EXT>
    # -- every logo is converted to this single format/size (see common/logo.py),
    # so a school's logo file existing at that exact path IS the "has a logo"
    # signal; there is no DB column for it. This is the single place the
    # subdirectory/extension/size are spelled out, shared by the web app
    # (building the served URL) and standalone/notebooks/Load Schools in
    # DB.ipynb (building the on-disk path when scraping/converting logos).
    SCHOOL_LOGO_STATIC_SUBDIR = "images/school_logos"
    SCHOOL_LOGO_EXT = "webp"
    SCHOOL_LOGO_MAX_DIMENSION = 300  # px, longest side; smaller logos are never upscaled
    SCHOOL_LOGO_WEBP_QUALITY = 82  # visually near-lossless at logo display sizes; ~1/10th a PNG
    # WEB_DIR is defined above, alongside DB_PATH, so both agree on the layout.
