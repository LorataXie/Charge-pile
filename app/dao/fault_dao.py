from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.fault_record import FaultRecord, FaultStatus


class FaultDAO(BaseDAO[FaultRecord]):
    model = FaultRecord

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_active_faults(self) -> list[FaultRecord]:
        result = await self.session.execute(
            select(FaultRecord).where(FaultRecord.status == FaultStatus.ACTIVE)
        )
        return list(result.scalars().all())

    async def get_by_pile_id(self, pile_id: int) -> list[FaultRecord]:
        result = await self.session.execute(
            select(FaultRecord).where(FaultRecord.pile_id == pile_id)
        )
        return list(result.scalars().all())
