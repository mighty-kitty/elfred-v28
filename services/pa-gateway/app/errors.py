# -*- coding: utf-8 -*-
"""Execution book 11.2 unified error codes."""
from fastapi import HTTPException

ERROR_CODES = {
    "AUTH_REQUIRED": 401, "CONSENT_REQUIRED": 403, "SERVICE_UNAVAILABLE": 503,
    "TOOL_UNAVAILABLE": 404, "APPROVAL_REQUIRED": 409, "POLICY_DENIED": 403,
    "CONFLICT": 409, "TIMEOUT": 504, "RETRYABLE_UPSTREAM": 502,
    "INVALID_OUTPUT": 422, "CANCELLED": 409, "DATA_REVOKED": 403, "NOT_FOUND": 404,
}


class ApiError(HTTPException):
    def __init__(self, code: str, detail: str = ""):
        status = ERROR_CODES.get(code, 500)
        self.code = code
        super().__init__(status_code=status, detail={"code": code, "message": detail or code})


def not_found(detail: str = "not found"):
    return ApiError("NOT_FOUND", detail)


def bad_request(detail: str = ""):
    return ApiError("INVALID_OUTPUT", detail)
