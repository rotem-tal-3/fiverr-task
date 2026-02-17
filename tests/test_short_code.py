import hashlib

import pytest

from app.short_code import Sha256ShortCodeGenerator, ShortCodeGenerator


class TestShortCodeGeneratorABC:
    """Verify that ShortCodeGenerator enforces the abstract contract."""

    def test_cannot_instantiate_abstract_class(self):
        """ShortCodeGenerator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ShortCodeGenerator()

    def test_concrete_subclass_must_implement_generate(self):
        """A subclass that omits `generate` cannot be instantiated."""

        class IncompleteGenerator(ShortCodeGenerator):
            pass

        with pytest.raises(TypeError):
            IncompleteGenerator()

    def test_concrete_subclass_with_generate_succeeds(self):
        """A subclass that implements `generate` can be instantiated."""

        class StubGenerator(ShortCodeGenerator):
            def generate(self, url: str) -> str:
                return "stub"

        generator = StubGenerator()
        assert generator.generate("https://example.com") == "stub"


class TestSha256ShortCodeGeneratorInit:
    """Verify constructor validation and defaults."""

    def test_default_length(self):
        """Default length is 8."""
        generator = Sha256ShortCodeGenerator()
        assert generator.length == 8

    def test_custom_length(self):
        """Custom length is stored correctly."""
        generator = Sha256ShortCodeGenerator(length=16)
        assert generator.length == 16

    @pytest.mark.parametrize("invalid_length", [0, -1, 65, 100])
    def test_invalid_length_raises(self, invalid_length: int):
        """Lengths outside 1–64 raise ValueError."""
        with pytest.raises(ValueError, match="length must be between 1 and 64"):
            Sha256ShortCodeGenerator(length=invalid_length)

    def test_boundary_length_1(self):
        """Minimum valid length (1) is accepted."""
        generator = Sha256ShortCodeGenerator(length=1)
        assert generator.length == 1

    def test_boundary_length_64(self):
        """Maximum valid length (64) is accepted."""
        generator = Sha256ShortCodeGenerator(length=64)
        assert generator.length == 64


class TestSha256ShortCodeGeneratorGenerate:
    """Verify short code generation behavior."""

    def test_output_matches_sha256_prefix(self):
        """Generated code matches the first N chars of the SHA-256 hex digest."""
        url = "https://example.com"
        expected = hashlib.sha256(url.encode()).hexdigest()[:8]
        generator = Sha256ShortCodeGenerator()
        assert generator.generate(url) == expected

    def test_output_length_matches_configured_length(self):
        """Output length equals the configured length."""
        generator = Sha256ShortCodeGenerator(length=12)
        result = generator.generate("https://example.com")
        assert len(result) == 12

    def test_deterministic_output(self):
        """Same URL always produces the same short code."""
        generator = Sha256ShortCodeGenerator()
        url = "https://example.com/page"
        assert generator.generate(url) == generator.generate(url)

    def test_different_urls_produce_different_codes(self):
        """Distinct URLs produce distinct short codes."""
        generator = Sha256ShortCodeGenerator()
        code_a = generator.generate("https://example.com/a")
        code_b = generator.generate("https://example.com/b")
        assert code_a != code_b

    def test_output_is_lowercase_hex(self):
        """Output contains only lowercase hex characters."""
        generator = Sha256ShortCodeGenerator()
        result = generator.generate("https://example.com")
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_string_input(self):
        """Empty string is a valid input and produces a deterministic code."""
        generator = Sha256ShortCodeGenerator()
        expected = hashlib.sha256(b"").hexdigest()[:8]
        assert generator.generate("") == expected

    def test_unicode_url(self):
        """URLs with unicode characters are handled correctly."""
        generator = Sha256ShortCodeGenerator()
        url = "https://example.com/café"
        expected = hashlib.sha256(url.encode()).hexdigest()[:8]
        assert generator.generate(url) == expected

    def test_full_length_64_returns_complete_digest(self):
        """Length 64 returns the full SHA-256 hex digest."""
        generator = Sha256ShortCodeGenerator(length=64)
        url = "https://example.com"
        expected = hashlib.sha256(url.encode()).hexdigest()
        assert generator.generate(url) == expected
