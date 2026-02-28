import os
import csv
import math
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import networkx as nx
import matplotlib.pyplot as plt


INPUT_CSV = r"C:\Users\hl667\Desktop\代码作业\414\A2\medium_inst414-data-science-tech_inst414featured_20260227_234914.csv"

OUT_DIR = os.path.dirname(INPUT_CSV)

PUB_SLUG = "inst414-data-science-tech"


def read_posts(csv_path: str):
    """
    CSV columns expected:
    title, link, pubDate, author, tags (pipe-separated), source
    """
    posts = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or "").strip()
            link = (row.get("link") or "").strip()
            tags = [t.strip() for t in (row.get("tags") or "").split("|") if t.strip()]
            posts.append(
                {
                    "title": title,
                    "link": link,
                    "pubDate": (row.get("pubDate") or "").strip(),
                    "author": (row.get("author") or "").strip(),
                    "tags": tags,
                    "source": (row.get("source") or "").strip(),
                }
            )
    return posts


def is_in_publication(link: str) -> bool:
    """
    Keep only:
      domain endswith medium.com
      path begins with /inst414-data-science-tech/
    """
    if not link:
        return False
    parts = urlsplit(link)
    host_ok = parts.netloc.endswith("medium.com")
    path_ok = parts.path.startswith(f"/{PUB_SLUG}/")
    return host_ok and path_ok


def build_article_similarity_graph(posts, min_shared_tags: int = 1):
    """
    Node: article (link)
    Edge: undirected, if share >= min_shared_tags tags
    Weight: number of shared tags
    """
    posts_pub = [p for p in posts if is_in_publication(p["link"])]

    node_data = {p["link"]: p for p in posts_pub if p["link"]}

    tag_to_links = defaultdict(list)
    for p in posts_pub:
        for t in p["tags"]:
            tag_to_links[t].append(p["link"])

    pair_shared = Counter()
    for tag, links in tag_to_links.items():
        links = list(dict.fromkeys(links))
        for i in range(len(links)):
            for j in range(i + 1, len(links)):
                a, b = links[i], links[j]
                if a != b:
                    pair_shared[(a, b)] += 1

    G = nx.Graph()

    for link, p in node_data.items():
        G.add_node(
            link,
            title=p["title"],
            pubDate=p["pubDate"],
            author=p["author"],
            tags=p["tags"],
            source=p["source"],
        )

    for (a, b), w in pair_shared.items():
        if w >= min_shared_tags and a in G and b in G:
            G.add_edge(a, b, weight=w)

    return G, posts_pub


def compute_metrics(G: nx.Graph):
    degree = dict(G.degree())
    weighted_degree = dict(G.degree(weight="weight"))
    pagerank = nx.pagerank(G, weight="weight") if G.number_of_edges() > 0 else {n: 0.0 for n in G.nodes()}
    betweenness = nx.betweenness_centrality(G, weight="weight", normalized=True) if G.number_of_edges() > 0 else {n: 0.0 for n in G.nodes()}
    return degree, weighted_degree, pagerank, betweenness


def write_top_table(G, metric_dict, out_csv, top_n=10, metric_name="metric"):
    ranked = sorted(metric_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", metric_name, "score", "weighted_degree", "degree", "title", "link", "tags"])
        wd_all = dict(G.degree(weight="weight"))
        d_all = dict(G.degree())
        for idx, (node, score) in enumerate(ranked, start=1):
            title = G.nodes[node].get("title", "")
            tags = ", ".join(G.nodes[node].get("tags", [])[:8])
            w.writerow([idx, metric_name, f"{score:.8f}", f"{wd_all.get(node,0):.2f}", d_all.get(node,0), title, node, tags])


def plot_network(G: nx.Graph, out_png: str, max_nodes: int = 35):
    if G.number_of_nodes() == 0:
        print("Graph has 0 nodes (after filtering). Nothing to plot.")
        return

    if G.number_of_edges() == 0:
        H = G
        pr = {n: 0.0 for n in H.nodes()}
    else:
        pr_full = nx.pagerank(G, weight="weight")
        top_nodes = [n for n, _ in sorted(pr_full.items(), key=lambda x: x[1], reverse=True)[:max_nodes]]
        H = G.subgraph(top_nodes).copy()
        pr = nx.pagerank(H, weight="weight") if H.number_of_edges() > 0 else {n: 0.0 for n in H.nodes()}

    pos = nx.spring_layout(H, seed=42, weight="weight")

    wd = dict(H.degree(weight="weight"))
    sizes = [200 + 80 * math.sqrt(max(wd.get(n, 0), 0)) for n in H.nodes()]

    widths = []
    for u, v, data in H.edges(data=True):
        w = data.get("weight", 1)
        widths.append(0.6 + 0.4 * w)

    plt.figure(figsize=(12, 9))
    nx.draw_networkx_edges(H, pos, width=widths, alpha=0.6)
    nx.draw_networkx_nodes(H, pos, node_size=sizes, alpha=0.85)

    top10 = set([n for n, _ in sorted(pr.items(), key=lambda x: x[1], reverse=True)[:10]])
    labels = {}
    for n in top10:
        t = H.nodes[n].get("title", "")
        labels[n] = (t[:26] + "…") if len(t) > 26 else t
    nx.draw_networkx_labels(H, pos, labels=labels, font_size=8)

    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def plot_top_tags(posts_pub, out_png: str, top_k: int = 15):
    tag_counts = Counter()
    for p in posts_pub:
        tag_counts.update(p["tags"])

    top = tag_counts.most_common(top_k)
    if not top:
        print("No tags to plot.")
        return

    labels = [t for t, _ in top]
    values = [c for _, c in top]

    plt.figure(figsize=(12, 6))
    plt.bar(labels, values)
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("Count")
    plt.title("Top Tags in INST414 Publication (RSS metadata)")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def main():
    posts = read_posts(INPUT_CSV)
    print(f"Loaded rows from CSV: {len(posts)}")

    G, posts_pub = build_article_similarity_graph(posts, min_shared_tags=1)
    print(f"After publication filter: {len(posts_pub)} posts")
    print(f"Graph nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}")

    degree, weighted_degree, pagerank, betweenness = compute_metrics(G)

    out_pr = os.path.join(OUT_DIR, "top10_pagerank.csv")
    out_wd = os.path.join(OUT_DIR, "top10_weighted_degree.csv")
    out_bw = os.path.join(OUT_DIR, "top10_betweenness.csv")

    write_top_table(G, pagerank, out_pr, top_n=10, metric_name="pagerank")
    write_top_table(G, weighted_degree, out_wd, top_n=10, metric_name="weighted_degree")
    write_top_table(G, betweenness, out_bw, top_n=10, metric_name="betweenness")

    print(f"Saved tables:\n- {out_pr}\n- {out_wd}\n- {out_bw}")

    out_net = os.path.join(OUT_DIR, "network_top35.png")
    out_tags = os.path.join(OUT_DIR, "top_tags.png")
    plot_network(G, out_net, max_nodes=35)
    plot_top_tags(posts_pub, out_tags, top_k=15)

    print(f"Saved figures:\n- {out_net}\n- {out_tags}")


    top3 = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:3]
    print("\nTop 3 by PageRank (copy these into your post):")
    for i, (node, score) in enumerate(top3, start=1):
        print(f"{i}. {G.nodes[node].get('title','')} | pagerank={score:.8f} | {node}")


if __name__ == "__main__":
    main()