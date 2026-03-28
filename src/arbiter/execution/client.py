"""Execution backends for Arbiter.

Supports multiple execution backends:
- Public API (default)
- Local paper trading
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from arbiter.lib.logger import setup_logger

logger = setup_logger("arbiter.execution")


class ExecutionBackend(Enum):
    """Available execution backends."""

    PUBLIC = "public"
    PAPER = "paper"


class ExecutionClient(ABC):
    """Abstract base class for execution clients."""

    @abstractmethod
    def get_account(self):
        pass

    @abstractmethod
    def get_positions(self):
        pass

    @abstractmethod
    def get_position(self, symbol: str):
        pass

    @abstractmethod
    def submit_order(self, symbol: str, qty: float | None, side: str, **kwargs):
        pass

    @abstractmethod
    def get_orders(self, status: str = "open"):
        pass

    @abstractmethod
    def cancel_order(self, order_id: str):
        pass

    @abstractmethod
    def get_price(self, symbol: str):
        pass


def create_execution_client(
    backend: ExecutionBackend = None,
) -> Optional[ExecutionClient]:
    """Create execution client based on configuration.

    Args:
        backend: Specific backend to use, or None for auto-detect

    Returns:
        ExecutionClient instance, or None if no backend configured
    """
    from arbiter.config.settings import EXECUTION_BACKEND

    # Auto-detect backend if not specified
    if backend is None:
        configured_backend = EXECUTION_BACKEND.lower().strip()
        if configured_backend == ExecutionBackend.PUBLIC.value:
            backend = ExecutionBackend.PUBLIC
            logger.info("Using configured Public API backend")
        elif configured_backend == ExecutionBackend.PAPER.value:
            backend = ExecutionBackend.PAPER
            logger.info("Using configured paper backend")
        else:
            import os

            public_token = os.getenv("PUBLIC_API_ACCESS_TOKEN") or os.getenv(
                "PUBLIC_API_KEY"
            )
            public_secret = os.getenv("PUBLIC_API_SECRET_KEY")
            if public_token or public_secret:
                backend = ExecutionBackend.PUBLIC
                logger.info("Auto-detected Public API backend")
            else:
                backend = ExecutionBackend.PAPER
                logger.info("No live broker configured; defaulting to paper backend")

    if backend == ExecutionBackend.PUBLIC:
        import os
        from arbiter.execution.public_client import PublicClient

        access_token = os.getenv("PUBLIC_API_ACCESS_TOKEN") or os.getenv(
            "PUBLIC_API_KEY"
        )
        secret_key = os.getenv("PUBLIC_API_SECRET_KEY")
        if (access_token and access_token != "your_public_access_token_here") or secret_key:
            logger.info("Using Public API backend")
            return PublicClient()
        else:
            logger.warning("Public API backend requested but not configured")
            return None

    if backend == ExecutionBackend.PAPER:
        from arbiter.execution.paper_client import PaperClient

        logger.info("Using local paper backend")
        return PaperClient()

    return None
