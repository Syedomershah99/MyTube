"""Keep only comments that recommend the video they link, and give each a topic, with Claude Haiku.

Comments go 25 to a request; requests go through the Message Batches API (half price) with the shared
instructions cached (1-hour TTL, as batches can wait between requests). State lives in data/classify/,
so the script can be stopped and re-run: `submit` sends what has not been sent, `collect` downloads
finished batches, `pilot` makes two direct calls to check the reply format and cost first.

Key: read from ~/.config/anthropic/key (never printed).
"""

from __future__ import annotations

import json
import pathlib
import sys

import anthropic
import duckdb

MODEL = "claude-haiku-5-5"
PER_REQUEST = 25
PER_BATCH = 4000  # requests per batch, well under the API's size limits
STATE = pathlib.Path("data/classify")
TOPICS = [
    "Programming", "Software engineering", "Systems and infrastructure", "Databases", "Security",
    "AI and machine learning", "Mathematics", "Physics", "Space and astronomy", "Biology and medicine",
    "Chemistry", "Engineering", "Electronics and hardware", "Retro computing", "Computer history",
    "Startups and business", "Economics and finance", "Product and design", "Science communication",
    "Education and lectures", "Conference talks", "Interviews and conversations", "History",
    "Politics and society", "Philosophy", "Psychology", "Language and linguistics", "Music",
    "Film and television", "Documentaries", "Comedy", "Art and animation", "Games and game design",
    "Chess and puzzles", "Sports", "Aviation", "Cars and transport", "Energy and climate", "Nature",
    "Cooking and food", "Making and DIY", "Architecture and cities", "Other",
]
SYSTEM = f"""You sort Hacker News comments that contain a YouTube link, for a site that lists the videos
Hacker News commenters recommend.

For each comment decide:
- "rec": true if the commenter is pointing other readers to the video as worth watching (a talk, lecture,
  documentary, song, demo, explanation, interview or other video they suggest, mention favourably or offer
  as a good source). false if the link is incidental: a citation of something bad, a joke reply with no
  recommendation, spam, self-promotion with no context, a link the commenter dislikes or criticises, or a
  link that is clearly not about watching (for example a mirror of an article).
- "topic": the single best topic for the video from this fixed list, copied exactly:
  {", ".join(TOPICS)}.
  Judge the topic from what the comment says about the video and from its title if the comment gives one.

Answer with only a JSON array, one object per comment, in the order given:
[{{"id": <comment id>, "rec": true|false, "topic": "<topic>"}}, ...]
No other text. Every comment gets exactly one object, even when it is unclear: then choose rec false and
topic "Other".

Examples of rec true: "This talk by X on Y is the best intro I know: <link>", "Relevant: <link> (great
lecture)", "If you liked that, watch <link>". Examples of rec false: "Here's the clip of him saying the
wrong thing: <link>" when used to criticise, "lol <link>" with no recommendation, "My channel: <link>"."""


def client() -> anthropic.Anthropic:
    key = (pathlib.Path.home() / ".config/anthropic/key").read_text().strip()
    return anthropic.Anthropic(api_key=key)


def comments() -> list[dict]:
    rows = duckdb.sql(
        "SELECT id, any_value(text) AS text FROM read_parquet('data/comments/*.parquet') GROUP BY id ORDER BY id"
    ).fetchall()
    return [{"id": i, "text": t[:900]} for i, t in rows]


def params(chunk: list[dict]) -> dict:
    body = "\n\n".join(f"<comment id={c['id']}>\n{c['text']}\n</comment>" for c in chunk)
    return {
        "model": MODEL,
        "max_tokens": 40 * len(chunk) + 64,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "thinking": {"type": "disabled"},  # a label per comment needs no reasoning; thinking ate the reply budget
        "messages": [{"role": "user", "content": body}],
    }


def chunks() -> list[tuple[str, list[dict]]]:
    cs = comments()
    return [(f"c{n:06d}", cs[i : i + PER_REQUEST]) for n, i in enumerate(range(0, len(cs), PER_REQUEST))]


def pilot() -> None:
    cl = client()
    for cid, chunk in chunks()[:2]:
        r = cl.messages.create(**params(chunk))
        print(cid, r.usage)
        print("".join(b.text for b in r.content if b.type == "text")[:600])


def submit() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    sent = {line for f in STATE.glob("batch-*.ids") for line in f.read_text().split()}
    todo = [(cid, ch) for cid, ch in chunks() if cid not in sent]
    print(f"{len(todo)} requests to send", flush=True)
    cl = client()
    for b in range(0, len(todo), PER_BATCH):
        part = todo[b : b + PER_BATCH]
        batch = cl.messages.batches.create(requests=[{"custom_id": cid, "params": params(ch)} for cid, ch in part])
        (STATE / f"batch-{batch.id}.ids").write_text("\n".join(cid for cid, _ in part))
        print(batch.id, len(part), flush=True)


def collect() -> None:
    cl = client()
    pending = 0
    for f in sorted(STATE.glob("batch-*.ids")):
        bid = f.stem.removeprefix("batch-")
        out = STATE / f"results-{bid}.jsonl"
        if out.exists():
            continue
        b = cl.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            pending += 1
            continue
        with out.open("w") as fh:
            for r in cl.messages.batches.results(bid):
                row = {"custom_id": r.custom_id, "type": r.result.type}
                if r.result.type == "succeeded":
                    m = r.result.message
                    row["text"] = "".join(b.text for b in m.content if b.type == "text")
                    row["usage"] = m.usage.model_dump()
                fh.write(json.dumps(row) + "\n")
        print(f"collected {bid}: {b.request_counts}", flush=True)
    print(f"{pending} batches still running", flush=True)


if __name__ == "__main__":
    {"pilot": pilot, "submit": submit, "collect": collect}[sys.argv[1]]()
