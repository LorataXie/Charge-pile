from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.vehicle import Vehicle


class VehicleDAO(BaseDAO[Vehicle]):
    model = Vehicle

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_user_id(self, user_id: int) -> list[Vehicle]:
        result = await self.session.execute(
            select(Vehicle).where(Vehicle.user_id == user_id)
        )
        return list(result.scalars().all())
