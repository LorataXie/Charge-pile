from abc import ABC, abstractmethod
from typing import Any


class DispatchStrategy(ABC):
    @abstractmethod
    async def dispatch(self, candidates: list[Any], piles: list[Any], context: dict) -> dict:
        """Returns mapping of candidate -> pile_id."""
        pass
