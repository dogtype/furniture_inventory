# app/linkcheck.py
#
# Checks every 12 hours whether the product links of the items still work.
# Only clear signals mark a link as broken (404, 410, redirect to the start page, repeated
# network errors). Bot protection, rate limits and server errors say nothing about the link,
# so they leave the last known state unchanged.

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from app.db import get_connection
from app.scraper import BLOCK_MARKERS, HEADERS

log = logging.getLogger("linkcheck")

TICK_SECONDS = 12 * 60 * 60  # how often the scheduler runs
# A link is due when its last check is older than this. Slightly less than the tick, otherwise a link
# checked at the end of a run would just miss the next one and wait for a whole extra tick.
CHECK_EVERY = timedelta(hours=11)
PAUSE_SECONDS = 1.5          # pause between two requests
NETWORK_FAILS_FOR_BROKEN = 2  # consecutive network errors before a link counts as broken

# "/", "/de/", "/de/de/", "/de-de/": the start page of a shop
HOME_PATH = re.compile(r"^/?([a-z]{2}([-_][a-z]{2})?)?(/[a-z]{2})?/?$", re.IGNORECASE)


def to_url(location: str | None) -> str | None:
    """Returns a checkable URL for the location text, or None if it is not a link (e.g. "Wohnzimmer links")."""
    loc = (location or "").strip()
    if not loc or " " in loc:
        return None
    url = loc if re.match(r"^https?://", loc, re.IGNORECASE) else f"https://{loc}"
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        return None
    return url


def _is_home_redirect(original: str, final: str) -> bool:
    orig_path = urlparse(original).path.strip("/")
    final_path = urlparse(final).path
    return bool(orig_path) and bool(HOME_PATH.match(final_path)) and not HOME_PATH.match("/" + orig_path)


async def check_url(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Returns (verdict, text). Verdict is "ok", "broken", "unknown" or "neterror"."""
    try:
        async with client.stream("GET", url) as response:
            status = response.status_code
            final = str(response.url)
            head = b""
            async for chunk in response.aiter_bytes():
                head += chunk
                if len(head) >= 8000:
                    break
    except httpx.TooManyRedirects:
        return "unknown", "zu viele Weiterleitungen"
    except httpx.HTTPError as e:
        return "neterror", type(e).__name__

    if status in (404, 410):
        return "broken", f"HTTP {status}"
    if status == 202 or status >= 300:
        # 202 is what some bot protections answer with, other codes (403, 429, 5xx) are inconclusive
        return "unknown", f"HTTP {status}"
    text = head.decode("utf-8", errors="ignore").lower()
    if any(m in text for m in BLOCK_MARKERS) and "application/ld+json" not in text:
        return "unknown", "Bot-Schutz"
    if _is_home_redirect(url, final):
        return "broken", "Weiterleitung auf die Startseite"
    return "ok", f"HTTP {status}"


def _save(item_id: int, verdict: str, text: str):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link_ok, link_fails FROM furniture WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return
    link_ok, fails = row["link_ok"], row["link_fails"] or 0
    if verdict == "ok":
        link_ok, fails = 1, 0
    elif verdict == "broken":
        link_ok, fails = 0, 0
    elif verdict == "neterror":
        fails += 1
        if fails >= NETWORK_FAILS_FOR_BROKEN:
            link_ok = 0
    else:
        fails = 0
    cursor.execute(
        "UPDATE furniture SET link_ok = ?, link_fails = ?, link_status = ?, link_checked_at = ? WHERE id = ?",
        (link_ok, fails, text, now, item_id),
    )
    conn.commit()
    conn.close()


async def run_checks(force: bool = False) -> int:
    """Checks all items whose last check is due (or all of them with force). Returns the count."""
    cutoff = (datetime.now(timezone.utc) - CHECK_EVERY).isoformat(timespec="seconds")
    conn = get_connection()
    cursor = conn.cursor()
    if force:
        cursor.execute("SELECT id, location FROM furniture")
    else:
        cursor.execute(
            "SELECT id, location FROM furniture WHERE link_checked_at IS NULL OR link_checked_at < ?", (cutoff,)
        )
    rows = cursor.fetchall()
    conn.close()

    checked = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=HEADERS) as client:
        for row in rows:
            url = to_url(row["location"])
            if url is None:
                _save(row["id"], "unknown", "kein Link")
                continue
            verdict, text = await check_url(client, url)
            _save(row["id"], verdict, text)
            checked += 1
            log.info("Link %s: %s (%s)", url, verdict, text)
            await asyncio.sleep(PAUSE_SECONDS)
    return checked


async def scheduler():
    await asyncio.sleep(30)  # let the server finish starting first
    while True:
        try:
            await run_checks()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Link check failed")
        await asyncio.sleep(TICK_SECONDS)
