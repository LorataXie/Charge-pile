from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.user_dao import UserDAO
from app.models.user import User
from config.settings import settings


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 100000)
    return f"pbkdf2:sha256:100000${salt}${h.hex()}"


def verify_password(password: str, hash_str: str) -> bool:
    parts = hash_str.split("$")
    if len(parts) != 3:
        return False
    _, salt, stored = parts
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 100000)
    return h.hex() == stored


class UserService:
    def __init__(self, session: AsyncSession):
        self.dao = UserDAO(session)

    async def register(self, username: str, password: str, role: str = "client") -> User:
        existing = await self.dao.get_by_username(username)
        if existing:
            raise ValueError("用户名已存在")
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        return await self.dao.create(user)

    async def login(self, username: str, password: str) -> str:
        user = await self.dao.get_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("用户名或密码错误")
        return self._create_token(user)

    def _create_token(self, user: User) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        claims = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "exp": expire,
        }
        return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            raise ValueError("无效的认证令牌")

    async def get_user(self, user_id: int) -> User | None:
        return await self.dao.get_by_id(user_id)
