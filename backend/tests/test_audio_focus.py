import pytest

from apps.audio_focus import AudioFocusCoordinator


@pytest.mark.asyncio
async def test_audio_focus_stays_active_until_every_foreground_owner_releases():
    coordinator = AudioFocusCoordinator()
    transitions = []

    async def listener(active: bool):
        transitions.append(active)

    coordinator.register(listener)
    await coordinator.acquire("speech-one")
    await coordinator.acquire("speech-two")
    await coordinator.release("speech-one")
    assert transitions == [True]
    await coordinator.release("speech-two")
    assert transitions == [True, False]
