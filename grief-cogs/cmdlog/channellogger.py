import asyncio
import datetime
from asyncio import Queue
from typing import NoReturn, Optional

import discord
from cmdlog.objects import Log

from grief.core.bot import Grief
from grief.core.utils.chat_formatting import box, pagify

from .vexutils import get_vex_logger
from .vexutils.loop import VexLoop

log = get_vex_logger(__name__)


class ChannelLogger:
    def __init__(self, bot: Grief, channel: discord.TextChannel) -> None:
        self.bot = bot
        self.channel = channel
        self.task: Optional[asyncio.Task] = None

        self._loop_meta = VexLoop("CmdLog channels", 60.0)

        self.last_send = self._utc_now() - datetime.timedelta(seconds=65)
        # basically make next sendable time now

        self._queue: Queue[Log] = Queue()

    def stop(self) -> None:
        """Stop the channel logger task."""
        if self.task:
            self.task.cancel()

        log.verbose("CmdLog channel logger task stopped.")

    def start(self) -> None:
        """Start the channel logger task."""
        self._queue = Queue()
        self.task = self.bot.loop.create_task(self._cmdlog_channel_task())

        log.verbose("CmdLog channel logger task started.")

    def add_command(self, command: Log):
        log.trace("command added to channel logger queue: %s", command)
        self._queue.put_nowait(command)

    @staticmethod
    def _utc_now() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    async def _cmdlog_channel_task(self) -> NoReturn:
        while True:
            try:
                await self._wait_to_next_safe_send_time()
                to_send = [await self._queue.get()]
                while self._queue.empty() is False:
                    to_send.append(self._queue.get_nowait())

                log.trace("got %s commands to send", len(to_send))

                self.last_send = self._utc_now()

                msg = "\n".join(str(i) for i in to_send)
                for page in pagify(msg, shorten_by=20):
                    await self.channel.send(box(page, "css"))

                log.trace("sent %s commands", len(to_send))

            except Exception as e:
                log.warning(
                    "Something went wrong preparing and sending the messages for the CmdLog "
                    "channel. Some will have been lost, however they will still be available "
                    "under the `[p]cmdlog` command in Discord. Please report this to Vexed.",
                    exc_info=e,
                )

    async def _wait_to_next_safe_send_time(self) -> None:
        now = self._utc_now()
        last_send = (now - self.last_send).total_seconds()

        if last_send < 60:
            to_wait = 60 - last_send
            log.trace(
                f"Waiting {to_wait}s for next safe sendable time, last send was {last_send}s ago."
            )
            await asyncio.sleep(to_wait)
            # else:
            #     log.debug(f"Last send was {last_send}s ago, only waiting 5 seconds.")
            #     await asyncio.sleep(5)
        log.trace("Wait finished")
