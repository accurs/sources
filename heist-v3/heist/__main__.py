import logging
import argparse
import asyncio
import os
import psutil

from cashews import cache
from os import getenv, environ
from contextlib import suppress

from heist.framework.discord import interactions
from heist.framework import heist
from heist.shared.config import Configuration
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from dotenv import load_dotenv
load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("heist.log"),
    ],
)

logger = logging.getLogger("heist")

process = psutil.Process(os.getpid())
logger.info(
    f"Starting heist process with PID: {os.getpid()} [Parent: {process.ppid()}]"
)

redis_url = getenv("REDIS_URL", "redis://localhost:6379")
logger.info(f"Setting up cashews cache with Redis URL: {redis_url}")
try:
    cache.setup(redis_url, 
                client_side={"socket_timeout": 30.0},
                client_name="heist-cashews")
    logger.info("Successfully initialized cashews cache with Redis")

except Exception as e:
    logger.error(f"Failed to setup cashews cache: {e}")
    logger.warning("Falling back to memory cache")
    cache.setup("mem://")

# cache.setup("mem://")

environ["JISHAKU_NO_UNDERSCORE"] = "True"
environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
environ["JISHAKU_HIDE"] = "True"
environ["JISHAKU_FORCE_PAGINATOR"] = "True"
environ["JISHAKU_RETAIN"] = "True"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shard-start", type=int, required=True
    )
    parser.add_argument(
        "--shard-end", type=int, required=True
    )
    parser.add_argument(
        "--shard-count", type=int, required=True
    )
    parser.add_argument(
        "--protocol", type=str, default="http"
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0"
    )
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--cluster-id", type=int, required=True
    )
    args = parser.parse_args()

    logger.info(f"Starting bot with cluster_id={args.cluster_id}, port={args.port}")
    
    bot = heist(
        Configuration(),
        port=args.port,
        cluster_id=args.cluster_id,
        shard_ids=list(
            range(args.shard_start, args.shard_end + 1)
        ),
        shard_count=args.shard_count,
    )

    from heist.framework.script.github import GitHubWebhook
    github = GitHubWebhook(bot)

    async with bot:
        await github.initialize()
        logger.info("GitHub webhook server initialized")

        try:
            await bot.start()
        finally:
            await github.close()
            logger.info("GitHub webhook server closed")

if __name__ == "__main__":
    with (
        suppress(
            RuntimeError,
            KeyboardInterrupt,
            ProcessLookupError,
        ),
    ):
        asyncio.run(main())
