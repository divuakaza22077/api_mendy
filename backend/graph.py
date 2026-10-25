from __future__ import annotations

from collections.abc import Iterable

from backend.models import CallSite, DependencyGraph, GraphEdge, GraphNode


def graph_from_sites(
    owner: str,
    repo: str,
    head_sha: str,
    sites: Iterable[CallSite],
    scanned_files: int,
) -> DependencyGraph:
    site_list = list(sites)
    nodes: dict[str, GraphNode] = {
        f"repo:{owner}/{repo}": GraphNode(
            id=f"repo:{owner}/{repo}",
            type="repo",
            data={"label": f"{owner}/{repo}", "status": "healthy", "headSha": head_sha},
        )
    }
    edges: list[GraphEdge] = []
    file_ids: dict[str, str] = {}
    vendor_ids: dict[str, str] = {}
    for site in site_list:
        file_id = file_ids.setdefault(site.file, f"file:{site.file}")
        nodes.setdefault(
            file_id,
            GraphNode(
                id=file_id,
                type="file",
                data={"label": site.file.rsplit("/", 1)[-1], "path": site.file, "status": "impacted"},
            ),
        )
        edge_file = f"repo-file:{site.file}"
        if not any(edge.id == edge_file for edge in edges):
            edges.append(GraphEdge(id=edge_file, source=f"repo:{owner}/{repo}", target=file_id))

        site_id = f"site:{site.id}"
        nodes[site_id] = GraphNode(
            id=site_id,
            type="callsite",
            data={
                "label": f"{site.callee or site.kind} · L{site.start_line}",
                "status": "impacted",
                "line": site.start_line,
            },
        )
        edges.append(
            GraphEdge(
                id=f"file-site:{site.id}",
                source=file_id,
                target=site_id,
                animated=True,
                data={"impacted": True},
            )
        )

        vendor = site.vendor or "http"
        vendor_id = vendor_ids.setdefault(vendor, f"vendor:{vendor}")
        nodes.setdefault(
            vendor_id,
            GraphNode(
                id=vendor_id,
                type="vendor",
                data={"label": f"{vendor.title()} API", "status": "healthy"},
            ),
        )
        edges.append(GraphEdge(id=f"site-vendor:{site.id}", source=site_id, target=vendor_id))

    return DependencyGraph(
        nodes=list(nodes.values()),
        edges=edges,
        meta={
            "repo": f"{owner}/{repo}",
            "headSha": head_sha,
            "scannedFiles": scanned_files,
            "impactedSites": len(site_list),
        },
    )
