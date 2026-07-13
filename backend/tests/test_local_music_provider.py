import base64
import wave

import pytest

from apps.music.providers.local import LocalMusicProvider


def _write_silent_wav(path, *, seconds: int = 1) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * seconds)


@pytest.mark.asyncio
async def test_local_provider_scans_inspects_and_resolves_files(tmp_path):
    song = tmp_path / "晴天.wav"
    _write_silent_wav(song)
    provider = LocalMusicProvider([str(tmp_path)], cache_seconds=3600)

    results = await provider.search("晴天")
    assert len(results) == 1
    assert results[0].title == "晴天"

    track = await provider.inspect(results[0].source_id)
    stream = await provider.resolve_stream(results[0].source_id)
    assert track.provider == "local"
    assert track.duration_seconds == 1
    assert stream.local_path == str(song.resolve())
    assert stream.url == ""


@pytest.mark.asyncio
async def test_local_provider_rejects_source_ids_outside_configured_root(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    outside = tmp_path / "private.wav"
    _write_silent_wav(outside)
    provider = LocalMusicProvider([str(root)])
    escaped = base64.urlsafe_b64encode(b"../private.wav").decode("ascii").rstrip("=")

    with pytest.raises(ValueError, match="escaped"):
        await provider.inspect(f"0:{escaped}")
    with pytest.raises(ValueError, match="Invalid"):
        await provider.inspect(f"-1:{escaped}")
