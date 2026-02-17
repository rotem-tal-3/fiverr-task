from decimal import Decimal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application-wide configuration loaded from environment variables.

    Attributes:
        earning_per_click: Revenue credited for each valid (non-fraudulent) click.
        allowed_domains: Whitelist of permitted target-URL hostnames.
            An empty list disables domain filtering (all domains allowed).
    """

    earning_per_click: Decimal = Decimal("0.05")
    allowed_domains: list[str] = []

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
