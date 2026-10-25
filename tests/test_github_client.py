import asyncio

import httpx
import respx

from backend.config import Settings
from backend.github_client import GitHubClient


@respx.mock
def test_scan_repository_fetches_tree_and_blobs_without_clone() -> None:
    base = "https://api.github.com"
    respx.get(f"{base}/repos/acme/shop").mock(return_value=httpx.Response(200, json={"default_branch": "main"}))
    respx.get(f"{base}/repos/acme/shop/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "commit-1"}})
    )
    respx.get(f"{base}/repos/acme/shop/git/commits/commit-1").mock(
        return_value=httpx.Response(200, json={"tree": {"sha": "tree-1"}})
    )
    respx.get(f"{base}/repos/acme/shop/git/trees/tree-1").mock(
        return_value=httpx.Response(
            200,
            json={"truncated": False, "tree": [{"type": "blob", "path": "app.py", "sha": "blob-1", "size": 32}]},
        )
    )
    respx.get(f"{base}/repos/acme/shop/git/blobs/blob-1").mock(
        return_value=httpx.Response(200, json={"content": "aW1wb3J0IHN0cmlwZQpzdHJpcGUuQ2hhcmdlLmNyZWF0ZSgpCg=="})
    )

    async def run() -> dict[str, object]:
        async with GitHubClient(Settings(github_token="test")) as client:
            return await client.scan_repository("acme", "shop")

    result = asyncio.run(run())
    assert result["head_sha"] == "commit-1"
    assert result["scanned_files"] == 1
    assert isinstance(result["files"], dict)
    assert "app.py" in result["files"]


@respx.mock
def test_scan_repository_walks_truncated_recursive_trees() -> None:
    base = "https://api.github.com"
    respx.get(f"{base}/repos/acme/shop").mock(return_value=httpx.Response(200, json={"default_branch": "main"}))
    respx.get(f"{base}/repos/acme/shop/git/ref/heads/main").mock(
        return_value=httpx.Response(200, json={"object": {"sha": "commit-1"}})
    )
    respx.get(f"{base}/repos/acme/shop/git/commits/commit-1").mock(
        return_value=httpx.Response(200, json={"tree": {"sha": "tree-1"}})
    )
    tree_route = respx.get(f"{base}/repos/acme/shop/git/trees/tree-1")
    tree_route.side_effect = [
        httpx.Response(
            200,
            json={"truncated": True, "tree": [{"type": "tree", "path": "src", "sha": "tree-src"}]},
        ),
        httpx.Response(
            200,
            json={"truncated": False, "tree": [{"type": "tree", "path": "src", "sha": "tree-src"}]},
        ),
    ]
    respx.get(f"{base}/repos/acme/shop/git/trees/tree-src").mock(
        return_value=httpx.Response(
            200,
            json={"truncated": False, "tree": [{"type": "blob", "path": "api.py", "sha": "blob-1", "size": 32}]},
        )
    )
    respx.get(f"{base}/repos/acme/shop/git/blobs/blob-1").mock(
        return_value=httpx.Response(200, json={"content": "aW1wb3J0IHN0cmlwZQpzdHJpcGUuQ2hhcmdlLmNyZWF0ZSgpCg=="})
    )

    async def run() -> dict[str, object]:
        async with GitHubClient(Settings(github_token="test")) as client:
            return await client.scan_repository("acme", "shop")

    result = asyncio.run(run())
    assert result["scanned_files"] == 1
    assert isinstance(result["files"], dict)
    assert "src/api.py" in result["files"]
