import asyncio
import random


async def detect_fraud() -> bool:
    """
    Simulate a fraud detection check.

    Waits 500ms to mimic an external fraud-detection service,
    then returns a random pass/fail verdict with equal probability.

    Returns:
        True if the request is considered fraudulent, False otherwise.
    """
    await asyncio.sleep(0.5)
    return random.random() < 0.5
