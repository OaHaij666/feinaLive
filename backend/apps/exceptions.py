"""通用异常类"""

from typing import Optional


class AppException(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code="NOT_FOUND", status_code=404)


class ValidationException(AppException):
    def __init__(self, message: str = "数据验证失败"):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)


class ExternalServiceException(AppException):
    def __init__(self, message: str = "外部服务错误"):
        super().__init__(message, code="EXTERNAL_SERVICE_ERROR", status_code=502)


class MusicException(AppException):
    def __init__(self, message: str = "音乐服务错误"):
        super().__init__(message, code="MUSIC_ERROR", status_code=500)
