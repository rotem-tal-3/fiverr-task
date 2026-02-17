from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlmodel import SQLModel, Field


class ShortLink(SQLModel, table=True):
    """Represents a shortened URL mapping.

    Attributes:
        id: Auto-incrementing primary key.
        target_url: The original URL to redirect to.
        short_code: The unique short code used in the shortened URL.
        redirect_count: Number of redirections that passed fraud detection.
        created_at: Timezone-aware UTC timestamp of when the short link was created.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    target_url: str = Field(index=True, unique=True)
    short_code: str = Field(index=True, unique=True)
    redirect_count: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=sa.TIMESTAMP(timezone=True),
    )


class ClickEvent(SQLModel, table=True):
    """Records a single valid (non-fraudulent) click on a short link.

    Attributes:
        id: Auto-incrementing primary key.
        short_link_id: Foreign key referencing the clicked ShortLink.
        clicked_at: Timezone-aware UTC timestamp of when the click occurred.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    short_link_id: int = Field(foreign_key="shortlink.id", index=True)
    clicked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=sa.TIMESTAMP(timezone=True),
        sa_column_kwargs={"index": True},
    )
