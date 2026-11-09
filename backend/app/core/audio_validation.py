import hashlib

WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
WAV_RIFF = b"RIFF"
MP4_FTYP = b"ftyp"


def sniff_audio_type(data: bytes) -> tuple[str, str] | None:
    """Return (mime_type, extension) based on magic bytes; never trust the client MIME."""
    if len(data) >= 12 and data[:4] == WAV_RIFF and data[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if len(data) >= 4 and data[:4] == WEBM_MAGIC:
        return "audio/webm", "webm"
    if len(data) >= 12 and data[4:8] == MP4_FTYP:
        return "audio/mp4", "m4a"
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
