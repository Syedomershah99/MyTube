"""Titles and channels for the recommended videos from YouTube's public oEmbed endpoint (no API key).

Reads data/videos.parquet (from build_data.py) and appends one JSON line per video to data/meta.jsonl:
{"video_id", "ok", "title", "author"}. Removed or private videos come back ok=false and are left out of
the site. Re-running skips videos already looked up.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

import duckdb

OUT = pathlib.Path("data/meta.jsonl")


def look_up(video_id: str) -> dict:
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        f"https://www.youtube.com/watch?v={video_id}", safe=""
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.load(r)
            return {"video_id": video_id, "ok": True, "title": d.get("title", ""), "author": d.get("author_name", "")}
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):  # removed, private or not embeddable
                return {"video_id": video_id, "ok": False}
            time.sleep(2**attempt)
        except OSError:
            time.sleep(2**attempt)
    return {"video_id": video_id, "ok": None}  # network trouble: retried on the next run


def main() -> None:
    done = set()
    if OUT.exists():
        done = {json.loads(line)["video_id"] for line in OUT.open() if '"ok": null' not in line}
    ids = [r[0] for r in duckdb.sql("SELECT video_id FROM read_parquet('data/videos.parquet') WHERE people >= 2").fetchall()]
    todo = [v for v in ids if v not in done]
    print(f"{len(todo)} videos to look up", flush=True)
    with OUT.open("a") as fh, cf.ThreadPoolExecutor(max_workers=8) as pool:
        for n, row in enumerate(pool.map(look_up, todo), 1):
            fh.write(json.dumps(row) + "\n")
            if n % 1000 == 0:
                fh.flush()
                print(n, flush=True)


if __name__ == "__main__":
    main()
