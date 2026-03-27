import zstandard as zstd
import asyncio

_zstd_compressor = zstd.ZstdCompressor(
    level=3,
    threads=2,
    write_checksum=False,
    write_content_size=False
)
_zstd_decompressor = zstd.ZstdDecompressor()

async def compress(content: str) -> bytes:
    if not content or not isinstance(content, str):
        return b''
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _zstd_compressor.compress(content.encode("utf-8"))
    )

async def decompress(compressed: bytes) -> str:
    if not compressed:
        return ""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _zstd_decompressor.decompress(compressed).decode("utf-8")
        )
    except:
        return ""