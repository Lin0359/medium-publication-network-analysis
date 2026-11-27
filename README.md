# Medium Publication Article Network Analysis

A reproducible Python workflow for collecting public Medium RSS metadata and analyzing how articles in the **INST414 Data Science & Tech** publication relate through shared tags. The project builds a weighted article network, compares four centrality measures, and exports publication ready charts and ranking tables.

> The source dataset is not committed. Run the collector to create your own dated metadata snapshot; analysis results depend on the snapshot and collection date.

## What it does

- Collects article metadata from the publication RSS feed, with a polite delay and retry handling for rate limits and temporary server errors.
- Filters records to the target publication and represents each article as a network node.
- Connects two articles when they share at least one tag. Edge weight is the number of shared tags.
- Ranks articles by PageRank, degree, weighted degree, and betweenness centrality. Betweenness treats stronger similarity as a shorter distance by using the inverse edge weight.
- Produces a network diagram, a tag frequency chart, CSV ranking tables, and a JSON summary.

## Project files

| File | Purpose |
| --- | --- |
| `pachong.py` | Collects RSS metadata and writes timestamped CSV and JSON snapshots. |
| `analysis.py` | Validates the CSV schema, builds the weighted graph, calculates metrics, and exports charts and results. |
| `requirements.txt` | Lists the Python dependencies. |
| `.gitignore` | Excludes local data, generated outputs, and virtual environments. |

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run the workflow

Collect up to 100 unique articles into the local `data/` directory:

```bash
python pachong.py --target 100 --output-dir data
```

The collector prints the timestamped CSV path. Pass that file to the analysis script:

```bash
python analysis.py --input data/medium_articles_YYYYMMDDTHHMMSSZ.csv --output-dir outputs
```

Replace the example timestamp with the CSV filename printed by the collector. You can also analyze an existing CSV if it has these columns: `title`, `link`, `pubDate`, `author`, `tags`, and `source`. The `tags` column uses a vertical bar (`|`) between tags.

Useful collector options:

- `--target`: maximum number of unique article records (default: 100).
- `--delay`: seconds between feed requests (default: 1).
- `--retries`: retries for HTTP 429 and temporary server errors (default: 4).
- `--output-dir`: local folder for the dated CSV and JSON files (default: `data`).

## Generated outputs

The analysis writes these files to the selected output directory:

- `top_10_pagerank.csv`
- `top_10_degree.csv`
- `top_10_weighted_degree.csv`
- `top_10_betweenness.csv`
- `article_similarity_network.png`
- `top_tags.png`
- `summary.json`

The collector writes a matching `medium_articles_<timestamp>.csv` and `.json` snapshot. Local data and generated outputs are excluded from version control.

## Method and scope

This project analyzes RSS metadata and tags; it does not download or analyze the full text of articles. Shared tags are a simple proxy for topical similarity, so centrality scores describe relationships in this tag based graph rather than article quality or influence. RSS availability and the metadata returned by Medium can change over time.

The weighted graph supports PageRank and weighted degree as similarity strength. Betweenness uses `distance = 1 / shared_tag_count`, since shortest path algorithms interpret smaller distances as closer relationships. The network visualization uses a fixed layout seed for repeatable placement and labels only a subset of nodes to keep the chart readable.
