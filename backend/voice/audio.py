"""
Audio conversion and manipulation utilities for voice telephony streaming.
Handles 16-bit Linear PCM audio validation, sample rate conversion, and framing.
"""

from typing import List, Tuple, Optional
import audioop
import logging

logger = logging.getLogger(__name__)


def validate_pcm16_chunk(chunk: bytes, max_bytes: int = 102400) -> Tuple[bool, Optional[str]]:
    """
    Validate 16-bit Linear PCM mono audio chunk.
    Ensures byte length is an even number (2 bytes per sample) and within size bounds.
    """
    if not chunk:
        return False, "Audio chunk is empty"
    if len(chunk) % 2 != 0:
        return False, f"PCM 16-bit chunk has odd byte length ({len(chunk)} bytes)"
    if len(chunk) > max_bytes:
        return False, f"PCM chunk exceeds maximum size ({len(chunk)} > {max_bytes} bytes)"
    return True, None


def resample_pcm16(audio_bytes: bytes, in_rate: int, out_rate: int) -> bytes:
    """
    Resample 16-bit Linear PCM mono audio from in_rate to out_rate.
    Returns unmodified bytes if sample rates match or input is empty.
    Preserves 16-bit sample alignment.
    """
    if not audio_bytes or in_rate == out_rate:
        return audio_bytes

    if in_rate <= 0 or out_rate <= 0:
        raise ValueError(f"Invalid sample rates: in_rate={in_rate}, out_rate={out_rate}")

    # Ensure even byte count before ratecv
    if len(audio_bytes) % 2 != 0:
        audio_bytes = audio_bytes[:-(len(audio_bytes) % 2)]

    if not audio_bytes:
        return b""

    # audioop.ratecv(fragment, width=2, nchannels=1, inrate, outrate, state)
    converted, _ = audioop.ratecv(audio_bytes, 2, 1, in_rate, out_rate, None)

    # Ensure result maintains 2-byte alignment
    if len(converted) % 2 != 0:
        converted = converted[:-(len(converted) % 2)]

    return converted


def pad_pcm16_to_multiple(audio_bytes: bytes, multiple: int = 320) -> bytes:
    """
    Pad PCM 16-bit audio with silence bytes (0x00) so its length is a multiple of `multiple`.
    Useful for Exotel telephony frames which require chunk sizes in multiples of 320 bytes.
    """
    if not audio_bytes:
        return b""

    remainder = len(audio_bytes) % multiple
    if remainder != 0:
        padding_needed = multiple - remainder
        return audio_bytes + (b"\x00" * padding_needed)
    return audio_bytes


def chunk_pcm16(audio_bytes: bytes, chunk_size_bytes: int = 320, pad: bool = False) -> List[bytes]:
    """
    Divide continuous PCM audio bytes into discrete frames of chunk_size_bytes.
    If pad is True, the final frame is padded with silence to reach chunk_size_bytes.
    """
    if not audio_bytes:
        return []

    if pad:
        audio_bytes = pad_pcm16_to_multiple(audio_bytes, chunk_size_bytes)

    chunks: List[bytes] = []
    for i in range(0, len(audio_bytes), chunk_size_bytes):
        chunk = audio_bytes[i : i + chunk_size_bytes]
        if chunk:
            chunks.append(chunk)

    return chunks
