import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heist.framework import heist

logger = logging.getLogger("heist/backend")

class Backend:
    """Backend cluster management class."""
    
    def __init__(self, bot: "heist", port: int):
        self.bot = bot
        self.port = port
        self._task = None
        
    def start_task(self):
        """Start the backend task."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info(f"Backend task started on port {self.port}")
    
    async def stop(self):
        """Stop the backend task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Backend task stopped")
    
    async def _run(self):
        """Main backend loop."""
        try:
            while True:
                await asyncio.sleep(60)  # asyncio barebones heartbeat system to keep the cluster alive lol....
        except asyncio.CancelledError:
            logger.info("Backend task cancelled")
            raise

__all__ = ["Backend"]