import hashlib
from abc import ABC, abstractmethod


class ShortCodeGenerator(ABC):
    """Abstract base class for short code generation strategies.

    Subclasses must implement the `generate` method to produce a short
    code string from a given URL.
    """

    @abstractmethod
    def generate(self, url: str) -> str:
        """Derive a short code from the provided URL.

        Args:
            url: The target URL to generate a short code for.

        Returns:
            A short code string suitable for use in a shortened URL.
        """


class Sha256ShortCodeGenerator(ShortCodeGenerator):
    """Generate short codes using a truncated SHA-256 hex digest.

    Produces deterministic, collision-resistant codes by hashing the
    input URL and taking the first N hex characters.

    Attributes:
        length: Number of hex characters in the generated short code.
    """

    def __init__(self, length: int = 8) -> None:
        """Initialize the SHA-256 short code generator.

        Args:
            length: Number of leading hex characters to use from the
                SHA-256 digest. Must be between 1 and 64 inclusive.

        Raises:
            ValueError: If length is outside the valid range.
        """
        if not 1 <= length <= 64:
            raise ValueError(f"length must be between 1 and 64, got {length}")
        self.length = length

    def generate(self, url: str) -> str:
        """Derive a deterministic short code from a URL using SHA-256.

        Args:
            url: The target URL to hash.

        Returns:
            A lowercase hex string of `self.length` characters.
        """
        return hashlib.sha256(url.encode()).hexdigest()[:self.length]
