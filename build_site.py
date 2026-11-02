"""Write the static site's data: site/videos.json (compact) for the videos recommended by 2+ people.

Record: [video_id, title, channel, topic index, people, first year, last year, quote, quote comment id,
quote author, [other comment ids]]; topics are listed once, most videos first.
"""

from __future__ import annotations

import json
import pathlib

import duckdb

from classify import TOPICS

SITE = pathlib.Path("site")
# The few labels Haiku wrote outside the fixed list, mapped to the nearest listed topic.
NEAREST = {
    "Earth sciences": "Nature", "Game engines": "Games and game design", "Food and cooking": "Cooking and food",
    "Food and drink": "Cooking and food", "Neuroscience": "Biology and medicine", "Robotics": "Engineering",
    "Robotics and AI": "AI and machine learning", "Animals and nature": "Nature", "Animation": "Art and animation",
    "Computer hardware": "Electronics and hardware", "Computer science and distributed systems": "Systems and infrastructure",
    "Conspiracy and UFOs": "Other", "Cryptocurrency": "Economics and finance", "Firearms": "Other",
    "Guns and weapons": "Other", "Game design": "Games and game design", "Health and fitness": "Biology and medicine",
    "Health and medicine": "Biology and medicine", "Health and sleep": "Biology and medicine",
    "Healthcare": "Biology and medicine", "Languages and linguistics": "Language and linguistics",
    "Law": "Politics and society", "Law and courts": "Politics and society", "Television and history": "History",
    "Transport": "Cars and transport", "Urban planning": "Architecture and cities",
}


def main() -> None:
    meta = {}
    for line in open("data/meta.jsonl"):
        r = json.loads(line)
        if r.get("ok"):
            meta[r["video_id"]] = (r["title"], r["author"])
    rows = duckdb.sql(
        "SELECT video_id, topic, people, first_rec, last_rec, quotes FROM read_parquet('data/videos.parquet') "
        "WHERE people >= 2 ORDER BY people DESC, last_rec DESC"
    ).fetchall()
    fixed = set(TOPICS)
    rows = [(r[0], r[1] if r[1] in fixed else NEAREST.get(r[1], "Other"), *r[2:]) for r in rows if r[0] in meta]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r[1]] = counts.get(r[1], 0) + 1
    topics = sorted(counts, key=lambda t: (-counts[t], t))
    index = {t: i for i, t in enumerate(topics)}
    videos = []
    for vid, topic, people, first, last, quotes in rows:
        title, channel = meta[vid]
        q = quotes[0]
        quote = q["quote"] if len(q["quote"]) <= 180 else q["quote"][:177].rstrip() + "..."
        videos.append([vid, title, channel, index[topic], people, int(first[:4]), int(last[:4]), quote,
                       q["id"], q["by"], [x["id"] for x in quotes[1:]]])
    SITE.mkdir(exist_ok=True)
    data = {"topics": topics, "counts": [counts[t] for t in topics], "videos": videos}
    (SITE / "videos.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(videos)} videos, {len(topics)} topics, {(SITE / 'videos.json').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
