# HN Video Picks

11,044 YouTube videos that at least two different Hacker News commenters recommended, 2007 to 2026, sorted into 43 topics. A static site: search, topic filters, "for you" ordering and watched marks, all kept in your browser.

Inspired by Andrej Karpathy's [HackerTube](https://karpathy.bearblog.dev/hacker-tube/); built independently from public data.

## How it was made

1. **Extract** (`extract.py`, free): stream the monthly files of the [open-index/hacker-news](https://huggingface.co/datasets/open-index/hacker-news) dataset with DuckDB and keep comments that link a YouTube video: 256,991 comments, 185,888 videos.
2. **Classify** (`classify.py`, about $4.40 of API calls): Claude Haiku 5.5 labels each comment as a recommendation or not and assigns one of 43 topics. It reads 25 comments per request, through the Message Batches API (half price), with the instructions prompt-cached. Result: 117,485 recommending comments covering 79,346 videos.
3. **Roll up** (`build_data.py`): per video, the number of different people who recommended it, its most common topic, and short quotes that link back to the HN comments. Quotes come preferably from comments that link only that video.
4. **Titles** (`fetch_meta.py`, free): YouTube's public oEmbed endpoint, no API key. Of the 11,817 videos recommended by two or more people, 773 are now private or deleted and are left out.
5. **Site** (`build_site.py`, `docs/index.html`, served by GitHub Pages from `docs/`): one HTML file plus `videos.json` (3.1 MB), no framework and no server.

Rebuild: `uv run --with duckdb --with numpy --with anthropic python <step>.py` for each step in order. `classify.py` reads an Anthropic API key from `~/.config/anthropic/key`.

## Credits and licences

- Comments: Hacker News via the open-index/hacker-news dataset, licensed ODC-BY. Each video links back to its HN comments.
- Video titles and thumbnails: YouTube. Videos are linked, not hosted.
- Code: MIT. Not affiliated with Y Combinator, Hacker News or YouTube.
