from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user
from ..db import get_db
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, UserResponse
from ..security import hash_password, verify_password


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.scalar(select(User).where(func.lower(User.username) == payload.username.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
    count = await db.scalar(select(func.count()).select_from(User))
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role="admin" if not count else "user",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists") from None
    await db.refresh(user)
    request.session["user_id"] = user.id
    return user


@router.post("/login", response_model=UserResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.scalar(select(User).where(func.lower(User.username) == payload.username.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    request.session["user_id"] = user.id
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=UserResponse | None)
async def me(user: User | None = Depends(current_user)) -> User | None:
    return user
