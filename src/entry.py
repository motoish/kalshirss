from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

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
