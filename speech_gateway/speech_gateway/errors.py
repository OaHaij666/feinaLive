"""Classified failures controlling fallback and circuit-breaker behavior."""


class SpeechGatewayError(Exception):
    status_code = 502
    code = "speech_gateway_error"
    retryable = False


class InvalidSpeechRequestError(SpeechGatewayError):
    status_code = 422
    code = "invalid_speech_request"


class ProviderNotFoundError(SpeechGatewayError):
    status_code = 404
    code = "provider_not_found"


class ProviderUnavailableError(SpeechGatewayError):
    status_code = 503
    code = "provider_unavailable"
    retryable = True


class CircuitOpenError(ProviderUnavailableError):
    code = "provider_circuit_open"


class UnsupportedCapabilityError(SpeechGatewayError):
    status_code = 422
    code = "unsupported_capability"


class UpstreamAuthenticationError(SpeechGatewayError):
    status_code = 502
    code = "upstream_authentication_failed"


class UpstreamRateLimitError(SpeechGatewayError):
    status_code = 503
    code = "upstream_rate_limited"
    retryable = True


class SynthesisError(SpeechGatewayError):
    status_code = 502
    code = "synthesis_failed"
    retryable = True
