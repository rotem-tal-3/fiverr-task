import asyncio
import logging
from decimal import Decimal
from typing import Any, AsyncGenerator
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.db.models import ClickEvent, ShortLink
from app.fraud import FraudDetector
from app.db.session import SessionLocal
from app.schemas import (
    MonthlyBreakdown,
    ShortLinkCreate,
    ShortLinkRead,
    ShortLinkStats,
    StatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_session() -> AsyncGenerator[Any, Any]:
    """Yield an async database session and ensure it is closed after use."""
    async with SessionLocal() as session:
        yield session


def _build_short_url(request: Request, short_code: str) -> str:
    """Construct the full short URL from the current request context.

    Args:
        request: The incoming FastAPI request (used to resolve the base URL).
        short_code: The short code to append.

    Returns:
        The fully-qualified short URL.
    """
    return str(request.base_url) + short_code


async def _handle_fraud_check(short_link_id: int, fraud_detector: FraudDetector) -> None:
    """Run fraud detection in the background and record the click on pass.

    Opens its own database session so it is fully decoupled from the
    request lifecycle. On a legitimate click, both the denormalized
    ``redirect_count`` and a new ``ClickEvent`` row are written in the
    same transaction.

    Args:
        short_link_id: The primary key of the ShortLink to update.
        fraud_detector: The fraud detection strategy to use.
    """
    is_fraudulent = await fraud_detector.detect()

    if is_fraudulent:
        logger.info("Fraud detected for short_link id=%s — skipping count update", short_link_id)
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(ShortLink).where(ShortLink.id == short_link_id)
        )
        link = result.scalar_one_or_none()
        if link is not None:
            link.redirect_count += 1
            session.add(link)
            session.add(ClickEvent(short_link_id=short_link_id))
            await session.commit()
            logger.info("Redirect count updated for short_link id=%s", short_link_id)


@router.post("/links", response_model=ShortLinkRead, status_code=status.HTTP_201_CREATED)
async def create_short_link(
    body: ShortLinkCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a shortened URL for a given target URL.

    If the target URL has already been shortened, the existing short link is
    returned instead of creating a duplicate.

    Args:
        body: Request payload containing the target URL.
        request: The incoming request (used to build the short URL).
        session: Async database session (injected).

    Returns:
        The short link resource including the generated short URL.
    """
    target = str(body.target_url)

    if settings.allowed_domains:
        hostname = urlparse(target).hostname or ""
        if hostname not in settings.allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Domain '{hostname}' is not in the allowed domains list",
            )

    result = await session.execute(
        select(ShortLink).where(ShortLink.target_url == target)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        return {
            **existing.model_dump(),
            "short_url": _build_short_url(request, existing.short_code),
        }

    generator = request.app.state.short_code_generator
    short_code = generator.generate(target)
    link = ShortLink(target_url=target, short_code=short_code)
    session.add(link)
    await session.commit()
    await session.refresh(link)

    return {
        **link.model_dump(),
        "short_url": _build_short_url(request, link.short_code),
    }


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page."),
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    """Return paginated per-link statistics with monthly earnings breakdowns.

    Args:
        page: The page number to retrieve (1-indexed).
        page_size: Number of links per page.
        session: Async database session (injected).

    Returns:
        A StatsResponse containing paginated link stats and monthly reports.
    """
    total_result = await session.execute(select(func.count(ShortLink.id)))
    total_links: int = total_result.scalar_one()

    offset = (page - 1) * page_size
    links_result = await session.execute(
        select(ShortLink)
        .order_by(ShortLink.id)
        .offset(offset)
        .limit(page_size)
    )
    links: list[ShortLink] = list(links_result.scalars().all())

    if not links:
        return StatsResponse(
            page=page,
            page_size=page_size,
            total_links=total_links,
            items=[],
        )

    link_ids = [link.id for link in links]

    monthly_rows = await session.execute(
        select(
            ClickEvent.short_link_id,
            func.extract("year", ClickEvent.clicked_at).label("year"),
            func.extract("month", ClickEvent.clicked_at).label("month"),
            func.count().label("clicks"),
        )
        .where(ClickEvent.short_link_id.in_(link_ids))
        .group_by(
            ClickEvent.short_link_id,
            func.extract("year", ClickEvent.clicked_at),
            func.extract("month", ClickEvent.clicked_at),
        )
        .order_by("year", "month")
    )

    monthly_by_link: dict[int, list[MonthlyBreakdown]] = {lid: [] for lid in link_ids}
    clicks_by_link: dict[int, int] = {lid: 0 for lid in link_ids}
    for row in monthly_rows:
        earnings = float(Decimal(row.clicks) * settings.earning_per_click)
        monthly_by_link[row.short_link_id].append(
            MonthlyBreakdown(
                month=f"{int(row.month)}/{int(row.year)}",
                earnings=earnings,
            )
        )
        clicks_by_link[row.short_link_id] += row.clicks

    items: list[ShortLinkStats] = []
    for link in links:
        breakdowns = monthly_by_link[link.id]
        total_clicks = clicks_by_link[link.id]
        total_earnings = sum(b.earnings for b in breakdowns)
        items.append(
            ShortLinkStats(
                url=link.target_url,
                total_clicks=total_clicks,
                total_earnings=total_earnings,
                monthly_breakdown=breakdowns,
            )
        )

    return StatsResponse(
        page=page,
        page_size=page_size,
        total_links=total_links,
        items=items,
    )


@router.get("/{short_code}")
async def redirect_short_link(
    short_code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Redirect a short code to its original target URL.

    A background fraud-detection task is fired on every redirect. If the
    check passes, the link's redirect_count is incremented asynchronously
    without delaying the response.

    Args:
        short_code: The short code portion of the shortened URL.
        request: The incoming FastAPI request (used to access app state).
        session: Async database session (injected).

    Returns:
        A 307 redirect to the original target URL.

    Raises:
        HTTPException 404: If no short link matches the given code.
    """
    result = await session.execute(
        select(ShortLink).where(ShortLink.short_code == short_code)
    )
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short link not found",
        )

    fraud_detector = request.app.state.fraud_detector
    asyncio.create_task(_handle_fraud_check(link.id, fraud_detector))

    return RedirectResponse(url=link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
