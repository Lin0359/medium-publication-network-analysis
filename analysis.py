"""Analyze Medium article tags as a weighted similarity network."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

import matplotlib.pyplot as plt
import networkx as nx

PUBLICATION_SLUG = "inst414-data-science-tech"
REQUIRED_COLUMNS = {"title", "link", "pubDate", "author", "tags", "source"}


def read_posts(csv_path: Path) -> list[dict]:
    """Read RSS metadata and validate the collector's CSV schema."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        return [{
            "title": (row.get("title") or "").strip(),
            "link": (row.get("link") or "").strip(),
            "pubDate": (row.get("pubDate") or "").strip(),
            "author": (row.get("author") or "").strip(),
            "tags": [tag.strip() for tag in (row.get("tags") or "").split("|") if tag.strip()],
            "source": (row.get("source") or "").strip(),
        } for row in reader]


def is_in_publication(link: str) -> bool:
    """Check the URL host and path against the target Medium publication."""
    parts = urlsplit(link)
    host = (parts.hostname or "").lower()
    return (host == "medium.com" or host.endswith(".medium.com")) and parts.path.startswith(f"/{PUBLICATION_SLUG}/")


def build_graph(posts: list[dict]) -> tuple[nx.Graph, list[dict]]:
    """Create one node per article; edge weight is the number of shared tags."""
    selected = {post["link"]: post for post in posts if post["link"] and is_in_publication(post["link"])}
    tag_links: dict[str, set[str]] = defaultdict(set)
    for link, post in selected.items():
        for tag in post["tags"]:
            tag_links[tag].add(link)

    shared = Counter()
    for links in tag_links.values():
        ordered = sorted(links)
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                shared[(first, second)] += 1

    graph = nx.Graph()
    for link, post in selected.items():
        graph.add_node(link, **{key: post[key] for key in ("title", "pubDate", "author", "tags", "source")})
    for (first, second), weight in shared.items():
        graph.add_edge(first, second, weight=weight, distance=1 / weight)
    return graph, list(selected.values())


def calculate_metrics(graph: nx.Graph) -> dict[str, dict[str, float]]:
    """Calculate centralities; betweenness uses inverse similarity as distance."""
    if graph.number_of_edges():
        pagerank = nx.pagerank(graph, weight="weight")
        betweenness = nx.betweenness_centrality(graph, weight="distance", normalized=True)
    else:
        pagerank = {node: 0.0 for node in graph}
        betweenness = {node: 0.0 for node in graph}
    return {
        "pagerank": pagerank,
        "degree": dict(graph.degree()),
        "weighted_degree": dict(graph.degree(weight="weight")),
        "betweenness": betweenness,
    }


def write_rankings(graph: nx.Graph, metrics: dict[str, dict[str, float]], output_dir: Path, top_n: int = 10) -> None:
    for metric_name, scores in metrics.items():
        path = output_dir / f"top_{top_n}_{metric_name}.csv"
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["rank", "score", "degree", "weighted_degree", "title", "link", "tags"])
            for rank, (link, score) in enumerate(ranked, start=1):
                node = graph.nodes[link]
                writer.writerow([rank, f"{score:.8f}", metrics["degree"][link], metrics["weighted_degree"][link], node["title"], link, ", ".join(node["tags"])])


def plot_network(graph: nx.Graph, output_path: Path, max_nodes: int = 35) -> None:
    if not graph.number_of_nodes():
        return
    scores = calculate_metrics(graph)["pagerank"]
    selected = sorted(scores, key=scores.get, reverse=True)[:max_nodes]
    view = graph.subgraph(selected).copy()
    positions = nx.spring_layout(view, seed=42, weight="weight")
    weighted_degree = dict(view.degree(weight="weight"))
    sizes = [240 + 90 * math.sqrt(weighted_degree[node]) for node in view]
    widths = [0.7 + 0.5 * data["weight"] for _, _, data in view.edges(data=True)]
    fig, axis = plt.subplots(figsize=(13, 9))
    nx.draw_networkx_edges(view, positions, width=widths, alpha=0.3, edge_color="#64748b", ax=axis)
    nx.draw_networkx_nodes(view, positions, node_size=sizes, node_color="#2563eb", alpha=0.85, ax=axis)
    labels = {node: (view.nodes[node]["title"][:34] + "…") for node in selected[:10]}
    nx.draw_networkx_labels(view, positions, labels=labels, font_size=7, ax=axis)
    axis.set_title(f"Article similarity network — top {len(view)} articles")
    axis.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_top_tags(posts: list[dict], output_path: Path, top_k: int = 15) -> None:
    counts = Counter(tag for post in posts for tag in post["tags"])
    top = counts.most_common(top_k)
    if not top:
        return
    labels, values = zip(*top)
    fig, axis = plt.subplots(figsize=(10, max(5, len(top) * 0.34)))
    axis.barh(list(reversed(labels)), list(reversed(values)), color="#0f766e")
    axis.set_xlabel("Articles")
    axis.set_title("Most frequent publication tags")
    axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to the collector CSV.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Folder for tables, charts, and summary.")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    posts = read_posts(args.input)
    graph, publication_posts = build_graph(posts)
    metrics = calculate_metrics(graph)
    write_rankings(graph, metrics, args.output_dir)
    plot_network(graph, args.output_dir / "article_similarity_network.png")
    plot_top_tags(publication_posts, args.output_dir / "top_tags.png")
    summary = {
        "input_rows": len(posts),
        "publication_articles": len(publication_posts),
        "network_nodes": graph.number_of_nodes(),
        "network_edges": graph.number_of_edges(),
        "unique_tags": len({tag for post in publication_posts for tag in post["tags"]}),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Results saved to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
