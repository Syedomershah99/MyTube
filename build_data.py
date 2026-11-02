"""Join Haiku's labels with the comments and roll them up per video: data/videos.parquet.

Per video: how many different people recommended it, the most common topic among the recommending
comments, first and last recommendation, and up to three short quotes with links to their HN comments.
Also prints how the labels came out, so the inclusion threshold can be chosen from the numbers.
"""

from __future__ import annotations

import html
import json
import pathlib
import re

import duckdb

STATE = pathlib.Path("data/classify")
TAG = re.compile(r"<[^>]+>")
URL = re.compile(r"https?://\S+|www\.\S+")


def labels() -> list[tuple[int, bool, str]]:
    rows, bad = [], 0
    for f in sorted(STATE.glob("results-*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            text = r.get("text", "")
            try:
                items = json.loads(text[text.index("[") : text.rindex("]") + 1])
            except ValueError:
                bad += 1
                continue
            for it in items:
                if isinstance(it, dict) and "id" in it:
                    rows.append((int(it["id"]), bool(it.get("rec")), str(it.get("topic") or "Other")))
    print(f"{len(rows)} labels, {bad} unparseable replies")
    return rows


def quote(text: str) -> str:
    plain = " ".join(URL.sub(" ", html.unescape(TAG.sub(" ", text))).split())
    return plain if len(plain) <= 240 else plain[:237].rstrip() + "..."


def main() -> None:
    con = duckdb.connect()
    con.execute("CREATE TABLE labels(id UINTEGER, rec BOOLEAN, topic VARCHAR)")
    con.executemany("INSERT INTO labels VALUES (?, ?, ?)", labels())
    con.create_function("quote", quote, ["VARCHAR"], "VARCHAR")
    con.sql("""
        CREATE TABLE recs AS
        SELECT c.video_id, c.id, c."by", c."time", l.topic, quote(c.text) AS quote,
               count(*) OVER (PARTITION BY c.id) AS links_in_comment
        FROM read_parquet('data/comments/*.parquet') c JOIN labels l USING (id)
        WHERE l.rec AND c."by" IS NOT NULL
    """)
    print(con.sql("SELECT count(*) AS rec_comments, count(DISTINCT video_id) AS videos FROM recs").fetchall())
    print(con.sql("""
        SELECT n, count(*) FROM (SELECT video_id, count(DISTINCT "by") AS n FROM recs GROUP BY 1)
        GROUP BY 1 ORDER BY 1 LIMIT 6
    """).fetchall())
    con.sql("""
        COPY (
          SELECT video_id,
                 count(DISTINCT "by") AS people,
                 mode(topic) AS topic,
                 min("time")::VARCHAR AS first_rec,
                 max("time")::VARCHAR AS last_rec,
                 list({'id': id, 'by': "by", 'quote': quote}
                      ORDER BY links_in_comment, length(quote) < 40, abs(length(quote) - 150))[1:3] AS quotes
          FROM recs GROUP BY video_id
        ) TO 'data/videos.parquet' (FORMAT parquet)
    """)


if __name__ == "__main__":
    main()
