import logging
from fastapi import APIRouter, HTTPException

from .schemas import (
    SendCodeRequest,
    VerifyCodeRequest,
    VerifyCodeResponse,
    RegisterRequest,
    AuthResponse,
    UserResponse,
)
from .services import (
    create_verification,
    verify_code,
    send_verification_email,
    find_user_by_email,
    check_username_available,
    create_user,
    update_last_login,
    create_access_token,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/send-code")
async def send_code(body: SendCodeRequest):
    """인증 코드 발송"""
    logger.info(f"Send code request for: {body.email}")

    # 인증 코드 생성 및 DB 저장
    code = create_verification(body.email)

    # 이메일 발송
    sent = await send_verification_email(body.email, code)
    if not sent:
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다.")

    return {"success": True, "message": "인증 코드가 발송되었습니다."}


@router.post("/verify", response_model=VerifyCodeResponse)
def verify(body: VerifyCodeRequest):
    """인증 코드 검증 → 신규/기존 사용자 분기"""
    logger.info(f"Verify code request for: {body.email}")

    # 코드 검증
    is_valid = verify_code(body.email, body.code)
    if not is_valid:
        raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않거나 만료되었습니다.")

    # 기존 사용자 확인
    user = find_user_by_email(body.email)

    if user:
        # 기존 사용자 → JWT 발급
        update_last_login(user["id"])
        token = create_access_token(str(user["id"]), user["email"])
        logger.info(f"Existing user login: {body.email}")
        return VerifyCodeResponse(
            is_new_user=False,
            access_token=token,
            message="로그인 성공",
        )
    else:
        # 신규 사용자 → 닉네임 입력 필요
        logger.info(f"New user detected: {body.email}")
        return VerifyCodeResponse(
            is_new_user=True,
            access_token=None,
            message="신규 사용자입니다. 닉네임을 입력해주세요.",
        )


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest):
    """회원가입 완료 (인증 완료 후 닉네임 입력)"""
    logger.info(f"Register request: {body.email} / {body.username}")

    # 이메일 인증 완료 여부 확인
    from ..common.storage import get_supabase_client
    client = get_supabase_client()
    verification = (
        client.table("email_verifications")
        .select("*")
        .eq("email", body.email)
        .eq("verified", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not verification.data:
        raise HTTPException(status_code=400, detail="이메일 인증이 완료되지 않았습니다.")

    # 이미 가입된 이메일인지 확인
    existing = find_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    # username 중복 검사
    if not check_username_available(body.username):
        raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임입니다.")

    # username 유효성 검사
    if not body.username or len(body.username) < 2 or len(body.username) > 50:
        raise HTTPException(status_code=400, detail="닉네임은 2자 이상 50자 이하여야 합니다.")

    # 사용자 생성
    user = create_user(body.email, body.username)
    update_last_login(user["id"])

    # JWT 발급
    token = create_access_token(str(user["id"]), user["email"])

    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=str(user["id"]),
            email=user["email"],
            username=user["username"],
            role=user["role"],
        ),
        message="회원가입 완료",
    )
