"""NestJS-compatible HTTP errors.

NestJS returns ``{ statusCode, message, error }`` where ``message`` is a string
(HttpException) or a string[] (ValidationPipe). Both frontends read
``data.message``. We reproduce that body for every error path so the existing
error handling in the UIs keeps working unchanged.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Status code -> the "error" label NestJS uses.
_ERROR_LABEL = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
}


class ApiError(StarletteHTTPException):
    """An HttpException-style error carrying a human message."""

    def __init__(self, status_code: int, message: str | list[str]):
        super().__init__(status_code=status_code, detail=message)


def bad_request(message: str) -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, message)


def unauthorized(message: str) -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, message)


def forbidden(message: str) -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, message)


def not_found(message: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, message)


def _body(status_code: int, message: str | list[str]) -> dict:
    return {
        "statusCode": status_code,
        "message": message,
        "error": _ERROR_LABEL.get(status_code, "Error"),
    }


def _humanise(err: dict) -> str:
    """Turn a Pydantic validation error into a NestJS-ish sentence."""
    loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
    field = ".".join(loc) or "request"
    return f"{field}: {err.get('msg', 'is invalid')}"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code, content=_body(exc.status_code, exc.detail)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_: Request, exc: RequestValidationError):
        # NestJS ValidationPipe answers 400 with a list of messages.
        messages = [_humanise(e) for e in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_body(status.HTTP_400_BAD_REQUEST, messages),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):  # pragma: no cover
        return JSONResponse(
            status_code=500,
            content=_body(500, "Internal server error"),
        )
