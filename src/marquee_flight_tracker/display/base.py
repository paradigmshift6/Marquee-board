from abc import ABC, abstractmethod
from typing import List


class DisplayBackend(ABC):
    @abstractmethod
    def start(self) -> None:
        """Initialize the display."""

    @abstractmethod
    def update(self, messages: List[str]) -> None:
        """Update the display with new messages to cycle through."""

    @abstractmethod
    def stop(self) -> None:
        """Clean up resources."""
