"""Add the comments posted after the dataset's last month, from the free HN Algolia search API.

Writes data/comments/recent.parquet in the same shape as extract.py's files (id, by, time, parent,
video_id, text), covering everything after the newest comment already extracted. Re-running rebuilds it.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

import duckdb

API = "https://hn.algolia.com/api/v1/search_by_date"
VIDEO = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^\s\"<]*&(?:amp;)?)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def newest_extracted() -> int:
    t = duckdb.sql(
        "SELECT epoch(max(\"time\"))::BIGINT FROM read_parquet('data/comments/2*.parquet')"
    ).fetchall()[0][0]
    return int(t)


def fetch(after: int) -> list[dict]:
    hits, before = [], int(time.time()) + 60
    while True:
        q = urllib.parse.urlencode({
            "query": "youtu", "tags": "comment", "hitsPerPage": 1000,
            "numericFilters": f"created_at_i>{after},created_at_i<{before}",
        })
        with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
            page = json.load(r)["hits"]
        hits += page
        if len(page) < 1000:
            return hits
        before = min(h["created_at_i"] for h in page)  # walk back in time past the 1,000-hit cap


def main() -> None:
    after = newest_extracted()
    hits = fetch(after)
    rows, seen = [], set()
    for h in hits:
        text = html.unescape(h.get("comment_text") or "")
        cid = int(h["objectID"])
        for vid in dict.fromkeys(VIDEO.findall(text)):
            if (cid, vid) in seen:
                continue
            seen.add((cid, vid))
            rows.append((cid, h.get("author"), dt.datetime.fromtimestamp(h["created_at_i"], dt.timezone.utc),
                         h.get("parent_id"), vid, text))
    con = duckdb.connect()
    con.execute("CREATE TABLE r(id UINTEGER, \"by\" VARCHAR, \"time\" TIMESTAMPTZ, parent UINTEGER, video_id VARCHAR, text VARCHAR)")
    con.executemany("INSERT INTO r VALUES (?, ?, ?, ?, ?, ?)", rows)
    con.sql("COPY r TO 'data/comments/recent.parquet' (FORMAT parquet)")
    since = dt.datetime.fromtimestamp(after, dt.timezone.utc).date()
    print(f"{len(hits)} comments since {since}, {len(rows)} YouTube links, {len({r[0] for r in rows})} comments with a link")


if __name__ == "__main__":
    main()
