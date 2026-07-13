"""Explicit gateway failures; unsupported features are never silently dropped."""


class SpeechGatewayError(Exception):
    status_code = 502
    code = "speech_gateway_error"


class ProviderNotFoundError(SpeechGatewayError):
    status_code = 404
    code = "provider_not_found"


class ProviderUnavailableError(SpeechGatewayError):
    status_code = 503
    code = "provider_unavailable"


class UnsupportedCapabilityError(SpeechGatewayError):
    status_code = 422
    code = "unsupported_capability"


class SynthesisError(SpeechGatewayError):
    status_code = 502
    code = "synthesis_failed"
