from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint, fetch

FEED_KV_KEY = "feed.xml"


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        if path == "/feed.xml":
            feed = await self.env.RSS_KV.get(FEED_KV_KEY)
            if feed is None:
                return Response(
                    "Feed not ready yet. Wait for GitHub Actions refresh, "
                    "or upload feed.xml to RSS_KV.",
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
            return Response(
                feed,
                headers={"Content-Type": "application/rss+xml; charset=utf-8"},
            )

        return await self.env.ASSETS.fetch(request)

    async def scheduled(self, controller, env, ctx):
        # Cloudflare Cron is the clock; GitHub Actions still pulls Kalshi
        # (Cloudflare egress hits Kalshi rate limits).
        await self._dispatch_github_refresh(env)

    async def _dispatch_github_refresh(self, env) -> None:
        token = getattr(env, "GITHUB_TOKEN", None)
        if not token:
            print("GITHUB_TOKEN secret is missing; skip workflow dispatch")
            return

        repo = str(getattr(env, "GITHUB_REPO", None) or "motoish/kalshirss").strip()
        workflow = str(
            getattr(env, "GITHUB_WORKFLOW", None) or "refresh-feed.yml"
        ).strip()
        ref = str(getattr(env, "GITHUB_REF", None) or "main").strip()
        url = (
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
        )

        response = await fetch(
            url,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "kalshi-rss-worker",
            },
            body=json.dumps({"ref": ref}),
        )
        if response.status >= 300:
            body = await response.text()
            raise RuntimeError(
                f"GitHub workflow dispatch failed ({response.status}): {body[:300]}"
            )
        print(f"Dispatched {workflow} on {repo}@{ref}")
