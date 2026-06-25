from fastapi import APIRouter, Depends, HTTPException, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.db.mongo import get_db
from app.schemas.auth import RefreshRequest, TokenResponse, UserCreate, UserLogin, UserOut
from app.services.email_service import is_email_verified, send_verification_code, verify_code
from app.services.user_service import authenticate_user, create_user, find_user_by_id, serialize_user

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_MAX_AGE = 60 * 60
REFRESH_TOKEN_MAX_AGE = 60 * 60 * 24 * 14


def db_dep() -> AsyncIOMotorDatabase:
    return get_db()


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=ACCESS_TOKEN_MAX_AGE, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="none", max_age=REFRESH_TOKEN_MAX_AGE, path="/")


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


@router.post("/email/send-code", status_code=200, summary="이메일 인증코드 발송")
async def send_code(body: EmailRequest, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """6자리 인증코드를 이메일로 발송 (5분 유효)"""
    try:
        await send_verification_code(db, body.email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {str(e)}")
    return {"message": "인증코드가 발송되었습니다."}


@router.post("/email/verify-code", status_code=200, summary="이메일 인증코드 검증")
async def verify_email_code(body: VerifyRequest, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """인증코드 검증"""
    ok = await verify_code(db, body.email, body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="인증코드가 올바르지 않거나 만료되었습니다.")
    return {"message": "이메일 인증이 완료되었습니다."}


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: UserCreate, response: Response, db: AsyncIOMotorDatabase = Depends(db_dep)):
    """회원가입 - 이메일 인증 완료 후 가입 가능"""
    verified = await is_email_verified(db, body.email)
    if not verified:
        raise HTTPException(status_code=400, detail="이메일 인증이 필요합니다.")

    try:
        user = await create_user(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    serialized = serialize_user(user)
    access_token = create_access_token(serialized["id"])
    refresh_token = create_refresh_token(serialized["id"])
    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut(**serialized))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, response: Response, db: AsyncIOMotorDatabase = Depends(db_dep)):
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    serialized = serialize_user(user)
    access_token = create_access_token(serialized["id"])
    refresh_token = create_refresh_token(serialized["id"])
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut(**serialized))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, response: Response, db: AsyncIOMotorDatabase = Depends(db_dep)):
    try:
        user_id = decode_token(body.refresh_token, token_type="refresh")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 refresh token입니다.")
    user = await find_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")
    serialized = serialize_user(user)
    access_token = create_access_token(serialized["id"])
    refresh_token = create_refresh_token(serialized["id"])
    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut(**serialized))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "로그아웃 되었습니다."}


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    return UserOut(**serialize_user(current_user))
