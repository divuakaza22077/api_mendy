from __future__ import annotations

import base64
from collections import deque
from typing import Any
from urllib.parse import quote

import httpx

from backend.config import Settings


class GitHubError(RuntimeError):
    pass


class GitHubConflictError(GitHubError):
    pass


def create_github_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.github_api_base,
        timeout=httpx.Timeout(20.0),
        headers={
            "Authorization": f"Bearer {settings.github_token or ''}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": settings.github_api_version,
            "User-Agent": "api-mend",
        },
    )


class GitHubClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.github_token:
            raise GitHubError("GITHUB_TOKEN is not configured")
        self.settings = settings
        self.client = client or create_github_http_client(settings)
        self._owns_client = client is None

    async def __aenter__(self) -> GitHubClient:
        if self._owns_client:
            await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._owns_client:
            await self.client.__aexit__(exc_type, exc, traceback)

    async def _json(self, response: httpx.Response) -> Any:
        if response.is_error:
            if response.status_code == 429 or (
                response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
            ):
                raise GitHubError("GitHub rate limit exhausted")
            try:
                payload = response.json()
                detail = payload.get("message", response.text) if isinstance(payload, dict) else response.text
            except ValueError:
                detail = response.text
            safe_detail = str(detail).replace(self.settings.github_token or "", "[redacted]")
            raise GitHubError(f"GitHub {response.status_code}: {safe_detail[:300]}")
        return response.json()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GitHubError("GitHub request timed out") from exc
        except httpx.RequestError as exc:
            raise GitHubError("GitHub request failed") from exc

    async def access(self) -> dict[str, Any]:
        response = await self._send("GET", "/user")
        user = await self._json(response)
        rate = await self._send("GET", "/rate_limit")
        rate_data = await self._json(rate)
        return {
            "login": user.get("login"),
            "id": user.get("id"),
            "rate_limit_remaining": rate_data.get("resources", {}).get("core", {}).get("remaining"),
            "api_version": self.settings.github_api_version,
        }

    async def scan_repository(self, owner: str, repo: str, branch: str | None = None) -> dict[str, Any]:
        root = _repo_root(owner, repo)
        repo_data = await self._json(await self._send("GET", root))
        branch_name = _validate_ref(branch or repo_data["default_branch"])
        ref = await self._json(await self._send("GET", f"{root}/git/ref/heads/{_quote_ref(branch_name)}"))
        head_sha = ref["object"]["sha"]
        commit = await self._json(await self._send("GET", f"{root}/git/commits/{quote(str(head_sha), safe='')}"))
        tree_sha = commit["tree"]["sha"]
        tree = await self._json(
            await self._send("GET", f"{root}/git/trees/{quote(str(tree_sha), safe='')}", params={"recursive": "1"})
        )
        entries = tree.get("tree", [])
        if tree.get("truncated"):
            entries = await self._walk_tree(root, tree_sha)

        candidates = [
            entry
            for entry in entries
            if entry.get("type") == "blob"
            and entry.get("size", 0) <= 300_000
            and entry.get("path", "").lower().endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))
            and not any(
                part in entry.get("path", "")
                for part in ("node_modules/", "dist/", "build/", ".venv/", "vendor/")
            )
        ]
        if len(candidates) > self.settings.max_scan_files:
            raise GitHubError("Repository exceeds the bounded scan file limit")
        if sum(int(entry.get("size", 0) or 0) for entry in candidates) > self.settings.max_scan_bytes:
            raise GitHubError("Repository exceeds the bounded scan byte limit")

        async def fetch(entry: dict[str, Any]) -> tuple[str, str]:
            blob = await self._json(
                await self._send("GET", f"{root}/git/blobs/{quote(str(entry['sha']), safe='')}")
            )
            content = base64.b64decode(blob["content"])
            return entry["path"], content.decode("utf-8", errors="replace")

        files = dict(await _gather_bounded(candidates, fetch, limit=8))
        return {"branch": branch_name, "head_sha": head_sha, "files": files, "scanned_files": len(files)}

    async def _walk_tree(self, root: str, tree_sha: str) -> list[dict[str, Any]]:
        queue: deque[tuple[str, str]] = deque([(tree_sha, "")])
        entries: list[dict[str, Any]] = []
        while queue:
            current_sha, prefix = queue.popleft()
            tree = await self._json(
                await self._send("GET", f"{root}/git/trees/{quote(str(current_sha), safe='')}")
            )
            if tree.get("truncated"):
                raise GitHubError("A repository subtree is still truncated; scan limits were exceeded")
            for entry in tree.get("tree", []):
                path = entry.get("path", "")
                full_path = f"{prefix}/{path}".lstrip("/")
                if entry.get("type") == "tree":
                    if not _skip_directory(full_path):
                        queue.append((entry["sha"], full_path))
                elif entry.get("type") == "blob":
                    entries.append({**entry, "path": full_path})
                    if len(entries) > 10_000:
                        raise GitHubError("Repository exceeds the bounded scan file limit")
        return entries

    async def create_pr(
        self,
        owner: str,
        repo: str,
        base: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
        expected_head_sha: str | None = None,
    ) -> dict[str, Any]:
        root = _repo_root(owner, repo)
        base = _validate_ref(base)
        branch = _validate_ref(branch)
        ref = await self._json(await self._send("GET", f"{root}/git/ref/heads/{_quote_ref(base)}"))
        base_sha = ref["object"]["sha"]
        if expected_head_sha and base_sha != expected_head_sha:
            raise GitHubConflictError("Base branch changed after the scan; run a fresh scan before shipping")
        commit = await self._json(
            await self._send("GET", f"{root}/git/commits/{quote(str(base_sha), safe='')}")
        )
        tree_items = [
            {"path": path, "mode": "100644", "type": "blob", "content": text}
            for path, text in files.items()
        ]
        tree = await self._json(
            await self._send(
                "POST",
                f"{root}/git/trees",
                json={"base_tree": commit["tree"]["sha"], "tree": tree_items},
            )
        )
        new_commit = await self._json(
            await self._send(
                "POST",
                f"{root}/git/commits",
                json={"message": title, "tree": tree["sha"], "parents": [base_sha]},
            )
        )
        branch_response = await self._send(
            "POST",
            f"{root}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]},
        )
        if branch_response.status_code in (409, 422):
            try:
                branch_error = branch_response.json()
            except ValueError:
                branch_error = {}
            branch_exists = isinstance(branch_error, dict) and "Reference already exists" in str(
                branch_error.get("message", "")
            )
            if not branch_exists:
                await self._json(branch_response)
            await self._json(
                await self._send(
                    "PATCH",
                    f"{root}/git/refs/heads/{_quote_ref(branch)}",
                    json={"sha": new_commit["sha"], "force": False},
                )
            )
        else:
            await self._json(branch_response)
        pr = await self._send(
            "POST",
            f"{root}/pulls",
            json={"title": title, "head": branch, "base": base, "body": body},
        )
        if pr.status_code == 422:
            existing = await self._json(
                await self._send(
                    "GET",
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
        label = await self._send("POST", f"{root}/labels", json={"name": "api-mend-verified", "color": "16a34a"})
        if label.status_code in (201, 422):
            label_application = await self._send(
                "POST",
                f"{root}/issues/{pr_data['number']}/labels",
                json={"labels": ["api-mend-verified"]},
            )
            # Labels are best-effort metadata after the PR has been created.
            if not label_application.is_error:
                await self._json(label_application)
        return {"number": pr_data["number"], "url": pr_data["html_url"], "commit": new_commit["sha"], "reused": False}


async def _gather_bounded(entries: list[dict[str, Any]], fetch: Any, limit: int) -> list[tuple[str, str]]:
    import asyncio

    semaphore = asyncio.Semaphore(limit)

    async def guarded(entry: dict[str, Any]) -> tuple[str, str]:
        async with semaphore:
            return await fetch(entry)

    return list(await asyncio.gather(*(guarded(entry) for entry in entries)))


def _skip_directory(path: str) -> bool:
    return any(
        part in path.split("/")
        for part in ("node_modules", "dist", "build", ".venv", "venv", "__pycache__", "vendor")
    )


def _repo_root(owner: str, repo: str) -> str:
    return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"


def _quote_ref(value: str) -> str:
    return quote(value, safe="/")


def _validate_ref(value: str) -> str:
    if (
        not value
        or len(value) > 255
        or any(char.isspace() or ord(char) < 32 for char in value)
        or any(token in value for token in ("..", "//", "@{", "?", "#", "\\"))
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise GitHubError("Invalid Git ref")
    return value
