"""
api/errors.py — Standard error response shapes and helpers.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def error_response(
    code: str,
    message: str,
    http_status: int = 400,
    details: Optional[list] = None,
    run_id: Optional[str] = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
        "status": "error",
    }
    if details:
        body["error"]["details"] = details
    if run_id:
        body["run_id"] = run_id

    return JSONResponse(status_code=http_status, content=body)


# ── Named constructors for common error codes ─────────────────────────────────

def unauthorized(message: str = "Authentication required") -> JSONResponse:
    return error_response("UNAUTHORIZED", message, 401)


def forbidden(message: str = "Insufficient permissions") -> JSONResponse:
    return error_response("FORBIDDEN", message, 403)


def invalid_input(message: str, details: Optional[list] = None) -> JSONResponse:
    return error_response("INVALID_INPUT", message, 422, details)


def invite_expired() -> JSONResponse:
    return error_response("INVITE_EXPIRED", "This invite link has expired.", 400)


def invite_already_used() -> JSONResponse:
    return error_response("INVITE_ALREADY_USED", "This invite link has already been used.", 400)


def gate1_failed(message: str, run_id: Optional[str] = None) -> JSONResponse:
    return error_response("GATE1_VALIDATION_FAILED", message, 200, run_id=run_id)


def openai_error(message: str = "OpenAI request failed") -> JSONResponse:
    return error_response("OPENAI_ERROR", message, 502)


def openai_timeout() -> JSONResponse:
    return error_response("OPENAI_TIMEOUT", "OpenAI request timed out.", 504)


def job_failed(message: str, run_id: Optional[str] = None) -> JSONResponse:
    return error_response("JOB_FAILED", message, 500, run_id=run_id)


def transcript_parse_fail(message: str) -> JSONResponse:
    return error_response("TRANSCRIPT_PARSE_FAIL", message, 422)


def target_label_mismatch(message: str) -> JSONResponse:
    return error_response("TARGET_LABEL_MISMATCH", message, 422)
