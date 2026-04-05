"""Shared response schemas used across multiple routers."""

from pydantic import BaseModel


class OkResponse(BaseModel):
    ok: bool = True


class OkMessageResponse(BaseModel):
    ok: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    error: str
