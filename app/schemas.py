from datetime import datetime

from pydantic import HttpUrl
from sqlmodel import SQLModel


class ShortLinkCreate(SQLModel):
    """Request body for creating a short link.

    Attributes:
        target_url: The original URL to shorten. Must be a valid HTTP(S) URL.
    """

    target_url: HttpUrl


class ShortLinkRead(SQLModel):
    """Response body for a short link.

    Attributes:
        id: The database identifier.
        target_url: The original URL.
        short_code: The unique short code.
        short_url: The fully-qualified short URL for redirection.
        redirect_count: Number of redirections that passed fraud detection.
        created_at: Timestamp of creation.
    """

    id: int
    target_url: str
    short_code: str
    short_url: str
    redirect_count: int
    created_at: datetime


class MonthlyBreakdown(SQLModel):
    """Earnings breakdown for a single calendar month.

    Attributes:
        month: Formatted month string (e.g. "12/2025").
        earnings: Revenue generated in this month.
    """

    month: str
    earnings: float


class ShortLinkStats(SQLModel):
    """Aggregated statistics for a single short link.

    Attributes:
        url: The original target URL.
        total_clicks: Lifetime valid click count.
        total_earnings: Lifetime earnings across all months.
        monthly_breakdown: Per-month earnings breakdown.
    """

    url: str
    total_clicks: int
    total_earnings: float
    monthly_breakdown: list[MonthlyBreakdown]


class StatsResponse(SQLModel):
    """Paginated response containing stats for multiple short links.

    Attributes:
        page: Current page number (1-indexed).
        page_size: Maximum number of items per page.
        total_links: Total number of short links in the database.
        items: Stats for each short link on this page.
    """

    page: int
    page_size: int
    total_links: int
    items: list[ShortLinkStats]
