from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.pile_dao import PileDAO
from app.dao.order_dao import OrderDAO
from app.models.charging_pile import ChargingPile, PileStatus


class PileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = PileDAO(session)
        self.order_dao = OrderDAO(session)

    async def get_all_piles(self) -> list[ChargingPile]:
        return list(await self.dao.get_all())

    async def get_pile(self, pile_id: int) -> ChargingPile | None:
        return await self.dao.get_by_id(pile_id)

    async def start_pile(self, pile_id: int) -> ChargingPile:
        pile = await self.dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        if pile.status not in (PileStatus.STOPPED, PileStatus.BROKEN):
            raise ValueError(f"充电桩当前状态为 {pile.status.value}，无法启动")
        pile.status = PileStatus.IDLE
        return await self.dao.update(pile)

    async def stop_pile(self, pile_id: int) -> ChargingPile:
        pile = await self.dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        active = await self.order_dao.get_charging_order_for_pile(pile_id)
        if active:
            raise ValueError("充电桩有正在充电的车辆，无法停止")
        pile.status = PileStatus.STOPPED
        return await self.dao.update(pile)

    async def mark_broken(self, pile_id: int) -> ChargingPile:
        pile = await self.dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        pile.status = PileStatus.BROKEN
        return await self.dao.update(pile)

    async def mark_idle(self, pile_id: int) -> ChargingPile:
        pile = await self.dao.get_by_id(pile_id)
        if not pile:
            raise ValueError("充电桩不存在")
        pile.status = PileStatus.IDLE
        return await self.dao.update(pile)

    async def increment_stats(self, pile_id: int, duration_hours: float, kwh: float) -> None:
        pile = await self.dao.get_by_id(pile_id)
        if pile:
            pile.total_charge_count += 1
            pile.total_charge_duration += round(duration_hours, 4)
            pile.total_charge_kwh += round(kwh, 4)
            await self.dao.update(pile)
