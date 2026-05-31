from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.charging_pile import ChargingPile, PileStatus


class PileDAO(BaseDAO[ChargingPile]):
    model = ChargingPile

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_mode(self, mode: str) -> list[ChargingPile]:
        result = await self.session.execute(
            select(ChargingPile).where(ChargingPile.mode == mode)
        )
        return list(result.scalars().all())

    async def get_available_by_mode(self, mode: str) -> list[ChargingPile]:
        result = await self.session.execute(
            select(ChargingPile).where(
                ChargingPile.mode == mode,
                ChargingPile.status.in_([PileStatus.IDLE, PileStatus.CHARGING])
            )
        )
        return list(result.scalars().all())
