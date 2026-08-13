from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from workers import Response, WorkerEntrypoint

from kalshi_rss import FEED_KV_KEY


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        parsed = urlparse(request.url)
        path = parsed.path

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

        if path == "/refresh":
            return await self._handle_refresh(request, parsed.query)

        return await self.env.ASSETS.fetch(request)

    async def scheduled(self, controller, env, ctx):
        # Kalshi public API rate-limits Cloudflare Worker egress IPs.
        # Feed refresh runs in GitHub Actions instead.
        return

    async def _handle_refresh(self, request, query: str):
        expected = getattr(self.env, "REFRESH_TOKEN", None)
        if expected:
            params = parse_qs(query)
            provided = (
                (params.get("token") or [None])[0]
                or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            )
            if provided != expected:
                return Response("Unauthorized", status=HTTPStatus.UNAUTHORIZED)

        return Response(
            "Worker-side Kalshi refresh is disabled (Cloudflare egress hits Kalshi 429). "
            "Use GitHub Actions workflow 'Refresh Feed' or: "
            "python kalshi_rss.py && uv run pywrangler kv key put feed.xml "
            "--path=feed.xml --binding=RSS_KV --remote",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
