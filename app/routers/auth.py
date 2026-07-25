"""Auth routes: /auth/signup, /auth/login, /auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthUser, get_current_user
from app.db import get_session
from app.schemas.auth import LoginBody, SignupBody
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
async def signup(body: SignupBody, session: AsyncSession = Depends(get_session)):
    return await auth_service.signup(session, body)


@router.post("/login")
async def login(body: LoginBody, session: AsyncSession = Depends(get_session)):
    return await auth_service.login(session, body)


@router.get("/me")
async def me(user: AuthUser = Depends(get_current_user)):
    # Returns the decoded token payload verbatim (sub, role, tenantId, iat, exp).
    return user
