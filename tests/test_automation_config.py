from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_github_actions_schedules_feed_refresh_twice_per_hour():
    workflow = (ROOT / ".github/workflows/refresh-feed.yml").read_text(
        encoding="utf-8"
    )

    assert "schedule:" in workflow
    assert '- cron: "7,37 * * * *"' in workflow
    assert "workflow_dispatch:" in workflow


def test_cloudflare_worker_has_no_github_dispatch_responsibility():
    entrypoint = (ROOT / "src/entry.py").read_text(encoding="utf-8")
    wrangler = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")

    assert "async def scheduled" not in entrypoint
    assert "_dispatch_github_refresh" not in entrypoint
    assert "GITHUB_TOKEN" not in wrangler
    assert "GITHUB_REPO" not in wrangler
    assert '"triggers"' in wrangler
    assert '"crons": []' in wrangler
