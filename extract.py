"""Stream every monthly Hacker News file and keep comments that link a YouTube video (no AI, no key).

Writes data/comments/<YYYY-MM>.parquet: id, by, time, parent, video_id, text (HTML entities decoded).
Re-running skips months already written, so an interrupted run resumes.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import pathlib
import sys
import urllib.request

import duckdb

DATASET = "open-index/hacker-news"
BASE = f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
OUT = pathlib.Path("data/comments")
# watch?v=, youtu.be/, embed/, shorts/, live/ — an 11-character id; the text is HTML with &#x2F; for '/'.
VIDEO_RE = r"(?:youtube\.com/(?:watch\?(?:[^\s\"<]*&(?:amp;)?)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"


def months() -> list[str]:
    with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{DATASET}") as r:
        files = [s["rfilename"] for s in json.load(r)["siblings"]]
    return sorted(f for f in files if f.startswith("data/") and f.endswith(".parquet"))


def one(path: str) -> str:
    month = pathlib.Path(path).stem
    dest = OUT / f"{month}.parquet"
    if dest.exists():
        return f"{month} skipped"
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET threads=2;")
    con.sql(f"""
        COPY (
          WITH c AS (
            SELECT id, "by", "time", parent,
                   replace(replace(replace(replace(text, '&#x2F;', '/'), '&amp;', '&'), '&quot;', '"'), '&#x27;', '''') AS text
            FROM read_parquet('{BASE}{path}')
            WHERE type = 2 AND coalesce(deleted, 0) = 0 AND coalesce(dead, 0) = 0 AND text ILIKE '%youtu%'
          )
          SELECT id, "by", "time", parent, unnest(list_distinct(regexp_extract_all(text, '{VIDEO_RE}', 1))) AS video_id, text
          FROM c
        ) TO '{dest}.tmp' (FORMAT parquet)
    """)
    pathlib.Path(f"{dest}.tmp").rename(dest)
    n = con.sql(f"SELECT count(*) FROM read_parquet('{dest}')").fetchall()[0][0]
    return f"{month} {n}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    todo = months()
    print(f"{len(todo)} monthly files", flush=True)
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        for fut in cf.as_completed([pool.submit(one, p) for p in todo]):
            try:
                print(fut.result(), flush=True)
            except Exception as e:  # one bad month should not stop the rest; a re-run retries it
                print(f"ERROR {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
