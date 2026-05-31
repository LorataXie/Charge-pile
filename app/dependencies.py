from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config.settings import settings
from app.services.user_service import UserService
from app.services.scheduling_service import SchedulingService
from app.services.billing_service import BillingService
from app.services.pile_service import PileService
from app.services.fault_service import FaultService
from app.services.report_service import ReportService

if "sqlite" in settings.DATABASE_URL:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        payload = UserService.decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")
    return payload


async def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


def get_scheduling_service(db: AsyncSession = Depends(get_db)) -> SchedulingService:
    return SchedulingService(db)


def get_billing_service(db: AsyncSession = Depends(get_db)) -> BillingService:
    return BillingService(db)


def get_pile_service(db: AsyncSession = Depends(get_db)) -> PileService:
    return PileService(db)


def get_fault_service(db: AsyncSession = Depends(get_db)) -> FaultService:
    return FaultService(db)


def get_report_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    return ReportService(db)
