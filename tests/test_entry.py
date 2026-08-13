import sys
from types import ModuleType


def test_worker_entry_imports(monkeypatch):
    workers = ModuleType("workers")
    workers.Response = object
    workers.WorkerEntrypoint = type("WorkerEntrypoint", (), {})
    workers.fetch = object()
    monkeypatch.setitem(sys.modules, "workers", workers)
    sys.modules.pop("src.entry", None)

    from src.entry import Default

    assert Default is not None
    assert hasattr(Default, "scheduled")
    assert "kalshi_rss" not in sys.modules["src.entry"].__dict__
