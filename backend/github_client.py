from __future__ import annotations

import base64
from typing import Any

import httpx

from backend.config import Settings


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.github_token:
            raise GitHubError("GITHUB_TOKEN is not configured")
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.github_api_base,
            timeout=httpx.Timeout(20.0),
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": settings.github_api_version,
                "User-Agent": "api-mend",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.client.__aexit__(exc_type, exc, traceback)

    async def _json(self, response: httpx.Response) -> Any:
        if response.is_error:
            try:
                detail = response.json().get("message", response.text)
            except ValueError:
                detail = response.text
            raise GitHubError(f"GitHub {response.status_code}: {detail}")
        return response.json()

    async def access(self) -> dict[str, Any]:
        response = await self.client.get("/user")
        user = await self._json(response)
        rate = await self.client.get("/rate_limit")
        rate_data = await self._json(rate)
        return {
            "login": user.get("login"),
            "id": user.get("id"),
            "rate_limit_remaining": rate_data.get("resources", {}).get("core", {}).get("remaining"),
            "api_version": self.settings.github_api_version,
        }

    async def scan_repository(self, owner: str, repo: str, branch: str | None = None) -> dict[str, Any]:
        root = f"/repos/{owner}/{repo}"
        repo_data = await self._json(await self.client.get(root))
        branch_name = branch or repo_data["default_branch"]
        ref = await self._json(await self.client.get(f"{root}/git/ref/heads/{branch_name}"))
        head_sha = ref["object"]["sha"]
        commit = await self._json(await self.client.get(f"{root}/git/commits/{head_sha}"))
        tree_sha = commit["tree"]["sha"]
        tree = await self._json(await self.client.get(f"{root}/git/trees/{tree_sha}", params={"recursive": "1"}))
        if tree.get("truncated"):
            raise GitHubError("Repository tree is truncated; subtree fallback is required before scanning")

        candidates = [
            entry
            for entry in tree.get("tree", [])
            if entry.get("type") == "blob"
            and entry.get("size", 0) <= 300_000
            and entry.get("path", "").lower().endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
            and not any(
                part in entry.get("path", "")
                for part in ("node_modules/", "dist/", "build/", ".venv/", "vendor/")
            )
        ]

        async def fetch(entry: dict[str, Any]) -> tuple[str, str]:
            blob = await self._json(await self.client.get(f"{root}/git/blobs/{entry['sha']}"))
            content = base64.b64decode(blob["content"])
            return entry["path"], content.decode("utf-8", errors="replace")

        files = dict(await _gather_bounded(candidates, fetch, limit=8))
        return {"branch": branch_name, "head_sha": head_sha, "files": files, "scanned_files": len(files)}

    async def create_pr(
        self,
        owner: str,
        repo: str,
        base: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> dict[str, Any]:
        root = f"/repos/{owner}/{repo}"
        ref = await self._json(await self.client.get(f"{root}/git/ref/heads/{base}"))
        base_sha = ref["object"]["sha"]
        commit = await self._json(await self.client.get(f"{root}/git/commits/{base_sha}"))
        tree_items = [
            {"path": path, "mode": "100644", "type": "blob", "content": text}
            for path, text in files.items()
        ]
        tree = await self._json(
            await self.client.post(
                f"{root}/git/trees",
                json={"base_tree": commit["tree"]["sha"], "tree": tree_items},
            )
        )
        new_commit = await self._json(
            await self.client.post(
                f"{root}/git/commits",
                json={"message": title, "tree": tree["sha"], "parents": [base_sha]},
            )
        )
        branch_response = await self.client.post(
            f"{root}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]},
        )
        if branch_response.status_code == 422:
            await self._json(
                await self.client.patch(
                    f"{root}/git/refs/heads/{branch}",
                    json={"sha": new_commit["sha"], "force": False},
                )
            )
        else:
            await self._json(branch_response)
        pr = await self.client.post(
            f"{root}/pulls",
            json={"title": title, "head": branch, "base": base, "body": body},
        )
        if pr.status_code == 422:
            existing = await self._json(
                await self.client.get(
                    f"{root}/pulls",
                    params={"head": f"{owner}:{branch}", "state": "open"},
                )
            )
            if isinstance(existing, list) and existing and isinstance(existing[0], dict):
                first = existing[0]
                return {
                    "number": first["number"],
                    "url": first["html_url"],
                    "commit": new_commit["sha"],
                    "reused": True,
                }
        pr_data = await self._json(pr)
        label = await self.client.post(f"{root}/labels", json={"name": "api-mend-verified", "color": "16a34a"})
        if label.status_code not in (201, 422):
            await self._json(label)
        await self._json(
            await self.client.post(
                f"{root}/issues/{pr_data['number']}/labels",
                json={"labels": ["api-mend-verified"]},
            )
        )
        return {"number": pr_data["number"], "url": pr_data["html_url"], "commit": new_commit["sha"], "reused": False}


async def _gather_bounded(entries: list[dict[str, Any]], fetch: Any, limit: int) -> list[tuple[str, str]]:
    import asyncio

    semaphore = asyncio.Semaphore(limit)

    async def guarded(entry: dict[str, Any]) -> tuple[str, str]:
        async with semaphore:
            return await fetch(entry)

    return list(await asyncio.gather(*(guarded(entry) for entry in entries)))
