"""Provider-neutral Speech Gateway client."""

from apps.speech.client import SpeechGatewayClient, get_speech_gateway_client
from apps.speech.models import SpeechArtifact

__all__ = ["SpeechArtifact", "SpeechGatewayClient", "get_speech_gateway_client"]
