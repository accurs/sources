#!/usr/bin/env python3
"""
Heist Bot Launcher
Provides easy startup options for the heist Discord bot with proper sharding configuration.
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("heist-launcher")

def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent

def run_bot(shard_start=0, shard_end=0, shard_count=1, port=8080, cluster_id=0, protocol="http", host="0.0.0.0"):
    """Run the heist bot with specified parameters."""
    project_root = get_project_root()
    main_module = project_root / "heist" / "__main__.py"
    
    if not main_module.exists():
        logger.error(f"Main module not found at {main_module}")
        sys.exit(1)
    
    cmd = [
        sys.executable, "-m", "heist",
        "--shard-start", str(shard_start),
        "--shard-end", str(shard_end), 
        "--shard-count", str(shard_count),
        "--port", str(port),
        "--cluster-id", str(cluster_id),
        "--protocol", protocol,
        "--host", host
    ]
    
    logger.info(f"Starting heist bot with command: {' '.join(cmd)}")
    
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    try:
        subprocess.run(cmd, cwd=project_root, env=env, check=True)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except subprocess.CalledProcessError as e:
        logger.error(f"Bot exited with error code {e.returncode}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(
        description="Heist Bot Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run single shard on port 8080
  %(prog)s --dev                    # Run in development mode
  %(prog)s --shards 4               # Run with 4 shards (cluster 0)
  %(prog)s --cluster 1 --shards 4   # Run cluster 1 with 4 total shards
  %(prog)s --port 9000              # Run on custom port
        """
    )
    
    parser.add_argument(
        "--dev", 
        action="store_true",
        help="Development mode (single shard, port 8080)"
    )
    
    parser.add_argument(
        "--shard-start",
        type=int,
        help="Starting shard ID for this cluster"
    )
    parser.add_argument(
        "--shard-end", 
        type=int,
        help="Ending shard ID for this cluster"
    )
    parser.add_argument(
        "--shards",
        type=int,
        default=1,
        help="Total number of shards (default: 1)"
    )
    parser.add_argument(
        "--cluster",
        type=int,
        default=0,
        help="Cluster ID (default: 0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to run on (default: 8080)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--protocol",
        default="http",
        choices=["http", "https"],
        help="Protocol to use (default: http)"
    )
    
    args = parser.parse_args()
    
    if args.dev:
        logger.info("Running in development mode")
        run_bot(
            shard_start=0,
            shard_end=0, 
            shard_count=1,
            port=8080,
            cluster_id=0,
            protocol=args.protocol,
            host=args.host
        )
        return
    
    if args.shard_start is None or args.shard_end is None:
        shards_per_cluster = args.shards
        shard_start = args.cluster * shards_per_cluster
        shard_end = shard_start + shards_per_cluster - 1
    else:
        shard_start = args.shard_start
        shard_end = args.shard_end
    
    if shard_start > shard_end:
        logger.error("shard-start cannot be greater than shard-end")
        sys.exit(1)
    
    if shard_end >= args.shards:
        logger.error("shard-end cannot be greater than or equal to total shard count")
        sys.exit(1)
    
    logger.info(f"Cluster {args.cluster}: Managing shards {shard_start}-{shard_end} of {args.shards} total")
    
    run_bot(
        shard_start=shard_start,
        shard_end=shard_end,
        shard_count=args.shards,
        port=args.port,
        cluster_id=args.cluster,
        protocol=args.protocol,
        host=args.host
    )

if __name__ == "__main__":
    main()