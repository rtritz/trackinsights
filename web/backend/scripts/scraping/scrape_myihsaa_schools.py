"""
scrape_myihsaa_schools.py
=========================
Scrape all Indiana high-school names and logos from the myIHSAA
school directory API and store them in a local SQLite database.

The myIHSAA SPA at https://www.myihsaa.net/schools calls a public
JSON API under the hood:

  POST  .../api/school-directory/search   → list of schools
  GET   .../api/school-directory/{id}/logo → school logo image

This script hits that API directly (via httpx), so no browser needed.

Output
------
  web/data/schools.db                             – SQLite database
  web/frontend/static/images/school_logos/*.png    – downloaded logos

Usage
-----
    cd trackinsights
    python web/backend/scripts/scraping/scrape_myihsaa_schools.py
"""

import asyncio
import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone

import httpx

# ── paths & constants ────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
DB_PATH = os.path.join(WEB_DIR, "data", "schools.db")
LOGO_DIR = os.path.join(WEB_DIR, "frontend", "static", "images", "school_logos")

API_BASE = "https://myihsaa-prod-ams.azurewebsites.net/api/school-directory"
SEARCH_URL = f"{API_BASE}/search"
LOGO_URL = lambda school_id: f"{API_BASE}/{school_id}/logo"
PROFILE_URL = lambda school_id: f"https://www.myihsaa.net/schools/{school_id}"

# Request all schools in one page (there are ~412)
SEARCH_BODY = {"limit": -1, "page": 0, "count": 1000, "ihsaaDistrict": None}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://www.myihsaa.net/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ── database ─────────────────────────────────────────────────────────
def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS school_logo (
            school_name  TEXT PRIMARY KEY,
            school_id    TEXT,
            nickname     TEXT,
            city         TEXT,
            logo_url     TEXT,
            logo_path    TEXT,
            profile_url  TEXT,
            has_logo     INTEGER,
            logo_sha256  TEXT,
            scraped_at   TEXT
        )
    """)
    conn.commit()
    return conn


def upsert(conn: sqlite3.Connection, **kw):
    conn.execute(
        """INSERT INTO school_logo(
                school_name, school_id, nickname, city,
                logo_url, logo_path, profile_url,
                has_logo, logo_sha256, scraped_at)
           VALUES(
                :school_name, :school_id, :nickname, :city,
                :logo_url, :logo_path, :profile_url,
                :has_logo, :logo_sha256, :scraped_at)
           ON CONFLICT(school_name) DO UPDATE SET
                school_id   = excluded.school_id,
                nickname    = excluded.nickname,
                city        = excluded.city,
                logo_url    = excluded.logo_url,
                logo_path   = excluded.logo_path,
                profile_url = excluded.profile_url,
                has_logo    = excluded.has_logo,
                logo_sha256 = excluded.logo_sha256,
                scraped_at  = excluded.scraped_at
        """,
        kw,
    )


# ── helpers ──────────────────────────────────────────────────────────
def safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-. ]+", "", name.strip())
    name = re.sub(r"\s+", "_", name)
    return name[:120] or "school"


# ── main logic ───────────────────────────────────────────────────────
async def scrape():
    os.makedirs(LOGO_DIR, exist_ok=True)
    conn = init_db(DB_PATH)

    print(f"Database : {DB_PATH}")
    print(f"Logo dir : {LOGO_DIR}")
    print()

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:

        # ── 1. Fetch school list from API ────────────────────────
        print("Fetching school directory …")
        resp = await client.post(SEARCH_URL, json=SEARCH_BODY)
        resp.raise_for_status()
        data = resp.json()

        schools = data.get("items", [])
        total = data.get("totalItems", len(schools))
        print(f"  API returned {len(schools)} schools (totalItems={total})\n")

        if not schools:
            print("⚠  No schools returned from API. Exiting.")
            conn.close()
            return

        # ── 2. Download logos ────────────────────────────────────
        downloaded = 0
        skipped = 0
        no_logo = 0
        errors = 0
        now = datetime.now(timezone.utc).isoformat()

        for i, school in enumerate(schools, 1):
            name = school["name"]
            sid = school["id"]
            has_logo = school.get("hasLogo", False)
            nickname = school.get("nickname")
            city = school.get("city")

            logo_url = LOGO_URL(sid) if has_logo else None
            profile_url = PROFILE_URL(sid)

            logo_path = None
            logo_sha = None

            if has_logo:
                filename = safe_filename(name) + ".png"
                full_path = os.path.join(LOGO_DIR, filename)
                rel_path = os.path.relpath(full_path, WEB_DIR)

                if os.path.exists(full_path):
                    with open(full_path, "rb") as f:
                        logo_sha = hashlib.sha256(f.read()).hexdigest()
                    logo_path = rel_path
                    skipped += 1
                else:
                    try:
                        logo_resp = await client.get(logo_url)
                        logo_resp.raise_for_status()
                        img_data = logo_resp.content

                        # Detect actual extension from content-type
                        ct = logo_resp.headers.get("content-type", "")
                        ext = ".png"
                        if "jpeg" in ct or "jpg" in ct:
                            ext = ".jpg"
                        elif "gif" in ct:
                            ext = ".gif"
                        elif "svg" in ct:
                            ext = ".svg"
                        elif "webp" in ct:
                            ext = ".webp"
                        filename = safe_filename(name) + ext
                        full_path = os.path.join(LOGO_DIR, filename)
                        rel_path = os.path.relpath(full_path, WEB_DIR)

                        with open(full_path, "wb") as f:
                            f.write(img_data)
                        logo_sha = hashlib.sha256(img_data).hexdigest()
                        logo_path = rel_path
                        downloaded += 1
                        print(f"  [{i:3d}/{len(schools)}] ↓ {filename}")
                    except Exception as exc:
                        print(f"  [{i:3d}/{len(schools)}] ⚠ {name}: {exc}")
                        errors += 1
            else:
                no_logo += 1

            upsert(
                conn,
                school_name=name,
                school_id=sid,
                nickname=nickname,
                city=city,
                logo_url=logo_url,
                logo_path=logo_path,
                profile_url=profile_url,
                has_logo=int(has_logo),
                logo_sha256=logo_sha,
                scraped_at=now,
            )

        conn.commit()
        conn.close()

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Schools in DB   : {len(schools)}")
    print(f"  Logos downloaded : {downloaded}")
    print(f"  Logos skipped    : {skipped} (already on disk)")
    print(f"  Schools w/o logo: {no_logo}")
    print(f"  Errors           : {errors}")
    print(f"  Database         : {DB_PATH}")
    print(f"  Logo directory   : {LOGO_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(scrape())
