from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import ClickEvent, ShortLink
from app.routes import _handle_fraud_check
from app.short_code import Sha256ShortCodeGenerator
from tests.conftest import AlwaysFraudDetector, AlwaysLegitFraudDetector

pytestmark = pytest.mark.asyncio


class TestCreateShortLink:
    """Tests for POST /links."""

    async def test_create_returns_201(self, client: AsyncClient):
        """Creating a new short link returns 201 with correct fields."""
        response = await client.post("/links", json={"target_url": "https://example.com"})
        assert response.status_code == 201
        data = response.json()
        assert data["target_url"] == "https://example.com/"
        assert data["short_code"]
        assert data["short_url"].endswith(data["short_code"])
        assert data["redirect_count"] == 0
        assert "id" in data
        assert "created_at" in data

    async def test_create_duplicate_returns_existing(self, client: AsyncClient):
        """Posting the same URL twice returns the original record."""
        url = "https://example.com/dup"
        first = await client.post("/links", json={"target_url": url})
        second = await client.post("/links", json={"target_url": url})
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["short_code"] == second.json()["short_code"]

    async def test_create_different_urls_get_different_codes(self, client: AsyncClient):
        """Distinct target URLs produce distinct short codes."""
        r1 = await client.post("/links", json={"target_url": "https://a.com"})
        r2 = await client.post("/links", json={"target_url": "https://b.com"})
        assert r1.json()["short_code"] != r2.json()["short_code"]

    async def test_create_uses_injected_generator(self, client: AsyncClient):
        """The short code matches the Sha256ShortCodeGenerator output."""
        target = "https://example.com/gen-test"
        response = await client.post("/links", json={"target_url": target})
        data = response.json()
        generator = Sha256ShortCodeGenerator()
        expected_code = generator.generate(str(data["target_url"]))
        assert data["short_code"] == expected_code

    async def test_create_invalid_url_returns_422(self, client: AsyncClient):
        """An invalid URL in the payload returns 422."""
        response = await client.post("/links", json={"target_url": "not-a-url"})
        assert response.status_code == 422

    async def test_create_missing_body_returns_422(self, client: AsyncClient):
        """A request with no body returns 422."""
        response = await client.post("/links", json={})
        assert response.status_code == 422

    async def test_short_url_contains_base_url(self, client: AsyncClient):
        """The returned short_url starts with the server base URL."""
        response = await client.post("/links", json={"target_url": "https://example.com/base"})
        data = response.json()
        assert data["short_url"].startswith("http://testserver/")


class TestDomainAllowlist:
    """Tests for allowed_domains filtering on POST /links."""

    async def test_allowed_domain_succeeds(self, client: AsyncClient):
        """A URL whose domain is in the allowlist returns 201."""
        with patch("app.routes.settings") as mock_settings:
            mock_settings.allowed_domains = ["example.com"]
            mock_settings.earning_per_click = settings.earning_per_click
            response = await client.post(
                "/links", json={"target_url": "https://example.com/page"}
            )
        assert response.status_code == 201

    async def test_disallowed_domain_returns_403(self, client: AsyncClient):
        """A URL whose domain is not in the allowlist returns 403."""
        with patch("app.routes.settings") as mock_settings:
            mock_settings.allowed_domains = ["example.com"]
            mock_settings.earning_per_click = settings.earning_per_click
            response = await client.post(
                "/links", json={"target_url": "https://evil.com/phish"}
            )
        assert response.status_code == 403
        assert "evil.com" in response.json()["detail"]

    async def test_empty_allowlist_permits_all(self, client: AsyncClient):
        """An empty allowlist disables filtering — any domain is accepted."""
        response = await client.post(
            "/links", json={"target_url": "https://anything.org/path"}
        )
        assert response.status_code == 201

    async def test_subdomain_not_implicitly_allowed(self, client: AsyncClient):
        """A subdomain is not allowed unless explicitly listed."""
        with patch("app.routes.settings") as mock_settings:
            mock_settings.allowed_domains = ["example.com"]
            mock_settings.earning_per_click = settings.earning_per_click
            response = await client.post(
                "/links", json={"target_url": "https://sub.example.com/page"}
            )
        assert response.status_code == 403


class TestRedirectShortLink:
    """Tests for GET /{short_code}."""

    async def test_redirect_returns_307(self, client: AsyncClient):
        """A valid short code returns a 307 redirect to the target URL."""
        create = await client.post("/links", json={"target_url": "https://example.com/redir"})
        short_code = create.json()["short_code"]
        response = await client.get(f"/{short_code}", follow_redirects=False)
        assert response.status_code == 307
        assert "example.com/redir" in response.headers["location"]

    async def test_redirect_unknown_code_returns_404(self, client: AsyncClient):
        """An unknown short code returns 404."""
        response = await client.get("/nonexistent", follow_redirects=False)
        assert response.status_code == 404
        assert response.json()["detail"] == "Short link not found"

    async def test_redirect_fires_background_fraud_check(self, client: AsyncClient):
        """Redirect creates a background task for fraud checking."""
        create = await client.post("/links", json={"target_url": "https://example.com/bg"})
        short_code = create.json()["short_code"]
        with patch("app.routes.asyncio.create_task") as mock_task:
            await client.get(f"/{short_code}", follow_redirects=False)
            mock_task.assert_called_once()


class TestHandleFraudCheck:
    """Tests for _handle_fraud_check background logic."""

    async def test_legit_click_increments_count(
        self, db_session: AsyncSession, db_session_factory: async_sessionmaker
    ):
        """A legitimate click increments redirect_count and creates a ClickEvent."""
        link = ShortLink(target_url="https://example.com/legit", short_code="legit001")
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        detector = AlwaysLegitFraudDetector()
        with patch("app.routes.SessionLocal", db_session_factory):
            await _handle_fraud_check(link.id, detector)

        await db_session.refresh(link)
        assert link.redirect_count == 1

    async def test_fraud_click_does_not_increment(
        self, db_session: AsyncSession, db_session_factory: async_sessionmaker
    ):
        """A fraudulent click leaves redirect_count at zero."""
        link = ShortLink(target_url="https://example.com/fraud", short_code="fraud001")
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        detector = AlwaysFraudDetector()
        with patch("app.routes.SessionLocal", db_session_factory):
            await _handle_fraud_check(link.id, detector)

        await db_session.refresh(link)
        assert link.redirect_count == 0

    async def test_legit_click_creates_click_event(
        self, db_session: AsyncSession, db_session_factory: async_sessionmaker
    ):
        """A legitimate click creates a ClickEvent record."""
        link = ShortLink(target_url="https://example.com/event", short_code="event001")
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        detector = AlwaysLegitFraudDetector()
        with patch("app.routes.SessionLocal", db_session_factory):
            await _handle_fraud_check(link.id, detector)

        from sqlmodel import select
        result = await db_session.execute(
            select(ClickEvent).where(ClickEvent.short_link_id == link.id)
        )
        events = result.scalars().all()
        assert len(events) == 1

    async def test_fraud_click_creates_no_click_event(
        self, db_session: AsyncSession, db_session_factory: async_sessionmaker
    ):
        """A fraudulent click creates no ClickEvent."""
        link = ShortLink(target_url="https://example.com/noevent", short_code="noevt001")
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        detector = AlwaysFraudDetector()
        with patch("app.routes.SessionLocal", db_session_factory):
            await _handle_fraud_check(link.id, detector)

        from sqlmodel import select
        result = await db_session.execute(
            select(ClickEvent).where(ClickEvent.short_link_id == link.id)
        )
        events = result.scalars().all()
        assert len(events) == 0

    async def test_nonexistent_link_is_noop(
        self, db_session: AsyncSession, db_session_factory: async_sessionmaker
    ):
        """Fraud check for a missing link ID does not raise."""
        detector = AlwaysLegitFraudDetector()
        with patch("app.routes.SessionLocal", db_session_factory):
            await _handle_fraud_check(999999, detector)


class TestGetStats:
    """Tests for GET /stats."""

    async def test_empty_stats(self, client: AsyncClient):
        """Stats with no links returns empty items list."""
        response = await client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_links"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    async def test_stats_after_creating_link(self, client: AsyncClient):
        """Stats reflect a newly created link with zero clicks."""
        await client.post("/links", json={"target_url": "https://example.com/stats1"})
        response = await client.get("/stats")
        data = response.json()
        assert data["total_links"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["url"] == "https://example.com/stats1"
        assert item["total_clicks"] == 0
        assert item["total_earnings"] == 0.0
        assert item["monthly_breakdown"] == []

    async def test_stats_pagination_defaults(self, client: AsyncClient):
        """Default pagination returns page=1, page_size=10."""
        response = await client.get("/stats")
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    async def test_stats_custom_pagination(self, client: AsyncClient):
        """Custom page and page_size are respected."""
        for i in range(3):
            await client.post("/links", json={"target_url": f"https://example.com/p{i}"})
        response = await client.get("/stats", params={"page": 1, "page_size": 2})
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["total_links"] == 3

    async def test_stats_page_beyond_total(self, client: AsyncClient):
        """Requesting a page beyond available data returns empty items."""
        await client.post("/links", json={"target_url": "https://example.com/beyond"})
        response = await client.get("/stats", params={"page": 100})
        data = response.json()
        assert data["items"] == []
        assert data["total_links"] == 1

    async def test_stats_invalid_page_returns_422(self, client: AsyncClient):
        """page=0 is invalid and returns 422."""
        response = await client.get("/stats", params={"page": 0})
        assert response.status_code == 422

    async def test_stats_invalid_page_size_returns_422(self, client: AsyncClient):
        """page_size=0 is invalid and returns 422."""
        response = await client.get("/stats", params={"page_size": 0})
        assert response.status_code == 422

    async def test_stats_page_size_over_max_returns_422(self, client: AsyncClient):
        """page_size=101 exceeds the maximum and returns 422."""
        response = await client.get("/stats", params={"page_size": 101})
        assert response.status_code == 422
