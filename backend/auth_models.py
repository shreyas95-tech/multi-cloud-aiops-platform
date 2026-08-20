"""Pydantic request/response models for Auth, RBAC, and KB features."""

from pydantic import BaseModel, Field
from typing import Literal


# Request models


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(..., min_length=8)
    role: Literal['Admin', 'L1_User']


class PasswordResetRequest(BaseModel):
    username: str = Field(..., min_length=1)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


# Response models


class LoginResponse(BaseModel):
    access_token: str
    role: str
    requires_password_change: bool


class UserResponse(BaseModel):
    username: str
    role: str
    created_at: str


class KBDocumentMeta(BaseModel):
    id: int
    title: str
    filename: str
    content_type: str
    file_size: int
    uploaded_by: str
    uploaded_at: str
