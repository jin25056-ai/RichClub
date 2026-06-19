from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.mongo import get_db
from app.schemas.auth import RefreshRequest, TokenResponse, UserCreate, UserLogin, UserOut
from app.services.user_service import authenticate_user, create_user, find_user_by_id, serialize_user

router = APIRouter(prefix="/auth", tags=["auth"])


def db_dep() -> AsyncIOMotorDatabase:
    return get_db()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: UserCreate, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """회원가입 - 이메일 중복 확인 후 bcrypt 암호화 저장"""
    try:
        user = await create_user(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    serialized = serialize_user(user)
    return TokenResponse(
        access_token=create_access_token(serialized["id"]),
        refresh_token=create_refresh_token(serialized["id"]),
        user=UserOut(**serialized),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """로그인 - access token (1시간) + refresh token (14일) 발급"""
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    serialized = serialize_user(user)
    return TokenResponse(
        access_token=create_access_token(serialized["id"]),
        refresh_token=create_refresh_token(serialized["id"]),
        user=UserOut(**serialized),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """refresh token으로 새 access token 발급"""
    try:
        user_id = decode_token(body.refresh_token, token_type="refresh")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )

    user = await find_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    serialized = serialize_user(user)
    return TokenResponse(
        access_token=create_access_token(serialized["id"]),
        refresh_token=create_refresh_token(serialized["id"]),
        user=UserOut(**serialized),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    """현재 로그인 사용자 정보 조회 (Bearer token 필요)"""
    return UserOut(**serialize_user(current_user))
