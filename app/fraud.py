import asyncio
import random
from abc import ABC, abstractmethod


class FraudDetector(ABC):
    """Abstract base class for fraud detection strategies.

    Subclasses must implement the `detect` method to determine
    whether a given interaction is fraudulent.
    """

    @abstractmethod
    async def detect(self) -> bool:
        """Run a fraud detection check.

        Returns:
            True if the interaction is considered fraudulent, False otherwise.
        """


class RandomFraudDetector(FraudDetector):
    """Simulated fraud detector that returns a random verdict.

    Introduces an artificial delay to mimic latency from an external
    fraud-detection service, then flips a coin with configurable probability.

    Attributes:
        delay: Seconds to wait before returning a result.
        threshold: Probability of flagging as fraudulent (0.0–1.0).
    """

    def __init__(self, delay: float = 0.5, threshold: float = 0.5) -> None:
        """Initialize the random fraud detector.

        Args:
            delay: Simulated service latency in seconds.
            threshold: Probability that a check is flagged as fraud.
        """
        self.delay = delay
        self.threshold = threshold

    async def detect(self) -> bool:
        """Simulate a fraud detection check.

        Returns:
            True if the interaction is considered fraudulent, False otherwise.
        """
        await asyncio.sleep(self.delay)
        return random.random() < self.threshold
