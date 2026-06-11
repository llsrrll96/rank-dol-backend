from pydantic import BaseModel, EmailStr
from typing import Optional


class SendCodeRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


class VerifyCodeResponse(BaseModel):
    is_new_user: bool
    access_token: Optional[str] = None
    message: str


class RegisterRequest(BaseModel):
    email: str
    username: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse
    message: str
