from importlib.util import find_spec

import pytest

from app.carehomes.store import MemoryCareHomeStore, sample_snapshot

# The browser tests import Playwright, which only the `e2e` dependency group installs.
if find_spec("playwright") is None:
    collect_ignore = ["e2e"]


class FakeStore(MemoryCareHomeStore):
    """The in-memory care home store, plus a switch to make Neo4j look unreachable."""

    healthy = True

    async def ping(self) -> bool:
        return self.healthy


@pytest.fixture
async def fake_store() -> FakeStore:
    """The made-up sample homes, as the API serves them before any CQC data is loaded."""
    store = FakeStore()
    await store.replace(sample_snapshot())
    return store


@pytest.fixture
def mock_sign_on(monkeypatch):
    """Turn mock sign-on on for one test, whatever brand.toml says."""
    from app.api.auth import demo_members
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_mode", "mock")
    demo_members.cache_clear()
    yield
    demo_members.cache_clear()
