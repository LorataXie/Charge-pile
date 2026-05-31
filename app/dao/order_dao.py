from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.charging_order import ChargingOrder, OrderStatus
from app.models.waiting_queue import WaitingQueue


class OrderDAO(BaseDAO[ChargingOrder]):
    model = ChargingOrder

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_user_id(self, user_id: int) -> list[ChargingOrder]:
        result = await self.session.execute(
            select(ChargingOrder).where(ChargingOrder.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: OrderStatus) -> list[ChargingOrder]:
        result = await self.session.execute(
            select(ChargingOrder).where(ChargingOrder.status == status)
        )
        return list(result.scalars().all())

    async def get_by_queue_number(self, queue_number: str) -> ChargingOrder | None:
        result = await self.session.execute(
            select(ChargingOrder).where(ChargingOrder.queue_number == queue_number)
        )
        return result.scalar_one_or_none()

    async def get_max_queue_number_for_mode(self, mode: str) -> int:
        result = await self.session.execute(
            select(ChargingOrder.queue_number)
            .where(ChargingOrder.mode == mode, ChargingOrder.queue_number.isnot(None))
            .order_by(ChargingOrder.id.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        if last is None:
            return 0
        try:
            return int(last[1:])
        except (ValueError, IndexError):
            return 0

    async def get_active_order_for_pile(self, pile_id: int) -> ChargingOrder | None:
        result = await self.session.execute(
            select(ChargingOrder).where(
                ChargingOrder.pile_id == pile_id,
                ChargingOrder.status.in_([OrderStatus.CHARGING, OrderStatus.QUEUED])
            )
        )
        return result.scalar_one_or_none()

    async def get_charging_order_for_pile(self, pile_id: int) -> ChargingOrder | None:
        result = await self.session.execute(
            select(ChargingOrder).where(
                ChargingOrder.pile_id == pile_id,
                ChargingOrder.status == OrderStatus.CHARGING
            )
        )
        return result.scalar_one_or_none()
