import os
import random
import string
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt
import httpx
from ..common.storage import get_supabase_client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-key-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

VERIFICATION_EXPIRE_MINUTES = 5


# ── 인증 코드 ──────────────────────────────────────────────

def generate_code() -> str:
    """6자리 숫자 인증 코드 생성"""
    return "".join(random.choices(string.digits, k=6))


def create_verification(email: str) -> str:
    """DB에 인증 레코드 생성, 인증 코드 반환"""
    client = get_supabase_client()
    code = generate_code()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_EXPIRE_MINUTES)).isoformat()

    record = {
        "email": email,
        "code": code,
        "expires_at": expires_at,
        "verified": False,
    }

    client.table("email_verifications").insert(record).execute()
    logger.info(f"Verification code created for {email}: {code}")
    return code


def verify_code(email: str, code: str) -> bool:
    """인증 코드 검증. 성공 시 verified=true 처리"""
    client = get_supabase_client()

    # 해당 이메일의 미인증 코드 중 가장 최신 것 조회
    resp = (
        client.table("email_verifications")
        .select("*")
        .eq("email", email)
        .eq("code", code)
        .eq("verified", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not resp.data:
        logger.info(f"No matching verification code for {email}")
        return False

    record = resp.data[0]

    # 만료 체크 (밀리초 부분의 자리수 문제로 인해 파싱되지 않는 현상 방지: 앞 19자리 "YYYY-MM-DDTHH:MM:SS"만 추출)
    expires_at_str = record["expires_at"][:19] 
    expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) > expires_at:
        logger.info(f"Verification code expired for {email}")
        return False

    # verified=true 처리
    client.table("email_verifications").update({"verified": True}).eq("id", record["id"]).execute()
    logger.info(f"Verification code verified for {email}")
    return True


# ── 이메일 발송 ──────────────────────────────────────────────

async def send_verification_email(email: str, code: str) -> bool:
    """Resend API를 통해 인증 코드 이메일 발송"""
    if not RESEND_API_KEY:
        logger.warning(f"RESEND_API_KEY not set. Verification code for {email}: {code}")
        return True

    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM_EMAIL,
                    "to": [email],
                    "subject": "[MyDol] 이메일 인증 코드",
                    "html": f"""
                        <div style="font-family: sans-serif; max-width: 400px; margin: 0 auto; padding: 20px;">
                            <h2 style="color: #333;">이메일 인증</h2>
                            <p>아래 인증 코드를 입력해주세요:</p>
                            <div style="background: #f4f4f4; padding: 16px; text-align: center;
                                        font-size: 32px; font-weight: bold; letter-spacing: 8px;
                                        border-radius: 8px; margin: 20px 0;">
                                {code}
                            </div>
                            <p style="color: #888; font-size: 14px;">
                                이 코드는 {VERIFICATION_EXPIRE_MINUTES}분간 유효합니다.
                            </p>
                        </div>
                    """,
                },
            )
            if response.status_code == 200:
                logger.info(f"Verification email sent to {email}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error sending verification email to {email}: {e}")
        return False


# ── 사용자 관리 ──────────────────────────────────────────────

def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """이메일로 사용자 조회"""
    client = get_supabase_client()
    resp = client.table("users").select("*").eq("email", email).limit(1).execute()
    if resp.data:
        logger.info(f"Found existing user: {email}")
        return resp.data[0]
    return None


def check_username_available(username: str) -> bool:
    """username 중복 검사"""
    client = get_supabase_client()
    resp = client.table("users").select("id").eq("username", username).limit(1).execute()
    return len(resp.data) == 0


def create_user(email: str, username: str) -> Dict[str, Any]:
    """신규 사용자 생성"""
    client = get_supabase_client()
    record = {
        "email": email,
        "username": username,
        "role": "USER",
    }
    resp = client.table("users").insert(record).execute()
    logger.info(f"Created new user: {email} ({username})")
    return resp.data[0]


def update_last_login(user_id: str):
    """last_login_at 업데이트"""
    client = get_supabase_client()
    client.table("users").update(
        {"last_login_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", user_id).execute()
    logger.info(f"Updated last_login_at for user {user_id}")


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """ID로 사용자 조회"""
    client = get_supabase_client()
    resp = client.table("users").select("*").eq("id", user_id).limit(1).execute()
    return resp.data[0] if resp.data else None


# ── JWT ──────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    """JWT Access Token 생성 (7일 만료)"""
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(f"JWT created for user {user_id}")
    return token


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """JWT 디코딩 및 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.info(f"JWT invalid: {e}")
        return None
