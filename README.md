# Medium Publication Article Network Analysis

A Python project that collects public Medium RSS metadata and explores article relationships through shared tags. It builds a weighted similarity network, calculates centrality metrics, and creates two visualizations.

> The course dataset is not included. Collect metadata with the script or provide a CSV that matches the schema below.

## Workflow

1. Collect RSS metadata for the INST414 Data Science & Tech publication.
2. Filter collected records to articles in the target publication.
3. Connect articles that share tags; edge weight is the number of shared tags.
4. Rank articles using PageRank, degree, weighted degree, and betweenness centrality.
5. Export ranking tables, a network diagram, and a tag-frequency chart.

## Files

- analysis.py — builds the similarity network, calculates metrics, and saves charts.
- pachong.py — collects RSS metadata into CSV and JSON files.
- requirements.txt — Python dependencies.

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

Collect metadata (requests are spaced out and retried when rate-limited):

```bash
python pachong.py
```

Analyze the CSV created by the collector:

```bash
python analysis.py
```

The CSV schema is: title, link, pubDate, author, tags, and source. Tags are pipe-separated.

## Outputs

The analysis writes three top-10 ranking tables, network_top35.png, and top_tags.png alongside the input CSV. The collector writes timestamped CSV and JSON files to the project output directory.

## Method and limitations

Each article is a node; an undirected edge joins two articles when their tag lists overlap. Edge weight is the number of shared tags. PageRank and weighted degree use this as connection strength. Betweenness should interpret stronger similarity as a shorter path, so edge distance should be the inverse of the shared-tag count.

This is exploratory analysis of RSS metadata. Shared tags indicate topical overlap, not article quality, influence, or causation. RSS feeds can change over time, so rerunning collection may produce different results. The collector reads feed metadata only and does not download article text. Keep requests moderate and follow Medium's terms and feed behavior.

## Data source

Public feeds from INST414 Data Science & Tech (https://medium.com/feed/inst414-data-science-tech) and related Medium tag feeds. This is a student project and is not affiliated with Medium or the University of Maryland.
