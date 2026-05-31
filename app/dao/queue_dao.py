from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.waiting_queue import WaitingQueue
from app.models.pile_queue import PileQueue
from app.models.charging_order import ChargingOrder, OrderStatus


class QueueDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_to_waiting(self, entry: WaitingQueue) -> WaitingQueue:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def add_to_pile_queue(self, entry: PileQueue) -> PileQueue:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def remove_from_waiting(self, order_id: int) -> None:
        from sqlalchemy import delete
        await self.session.execute(
            delete(WaitingQueue).where(WaitingQueue.order_id == order_id)
        )
        await self.session.flush()

    async def remove_from_pile_queue(self, order_id: int) -> None:
        from sqlalchemy import delete
        await self.session.execute(
            delete(PileQueue).where(PileQueue.order_id == order_id)
        )
        await self.session.flush()

    async def get_waiting_by_order(self, order_id: int) -> WaitingQueue | None:
        result = await self.session.execute(
            select(WaitingQueue).where(WaitingQueue.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_pile_queue_by_order(self, order_id: int) -> PileQueue | None:
        result = await self.session.execute(
            select(PileQueue).where(PileQueue.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_waiting_count_ahead(self, mode: str, position: int) -> int:
        result = await self.session.execute(
            select(func.count(WaitingQueue.id))
            .where(
                WaitingQueue.mode == mode,
                WaitingQueue.position < position
            )
        )
        return result.scalar() or 0

    async def get_next_in_waiting(self, mode: str) -> WaitingQueue | None:
        result = await self.session.execute(
            select(WaitingQueue)
            .where(WaitingQueue.mode == mode, WaitingQueue.is_paused == False)
            .order_by(WaitingQueue.position.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_waiting_by_mode(self, mode: str) -> list[WaitingQueue]:
        result = await self.session.execute(
            select(WaitingQueue)
            .where(WaitingQueue.mode == mode)
            .order_by(WaitingQueue.position.asc())
        )
        return list(result.scalars().all())

    async def get_pile_queue_entries(self, pile_id: int) -> list[PileQueue]:
        result = await self.session.execute(
            select(PileQueue)
            .where(PileQueue.pile_id == pile_id)
            .order_by(PileQueue.position.asc())
        )
        return list(result.scalars().all())

    async def get_pile_queue_size(self, pile_id: int) -> int:
        result = await self.session.execute(
            select(func.count(PileQueue.id)).where(PileQueue.pile_id == pile_id)
        )
        return result.scalar() or 0

    async def get_pile_charging_entry(self, pile_id: int) -> PileQueue | None:
        result = await self.session.execute(
            select(PileQueue).where(
                PileQueue.pile_id == pile_id,
                PileQueue.is_charging == True
            )
        )
        return result.scalar_one_or_none()

    async def set_waiting_paused(self, paused: bool) -> None:
        from sqlalchemy import update
        await self.session.execute(
            update(WaitingQueue).values(is_paused=paused)
        )
        await self.session.flush()

    async def clear_pile_queue_keep_charging(self, pile_id: int) -> list[PileQueue]:
        entries = await self.get_pile_queue_entries(pile_id)
        removed = [e for e in entries if not e.is_charging]
        from sqlalchemy import delete
        for e in removed:
            await self.session.execute(
                delete(PileQueue).where(PileQueue.id == e.id)
            )
        await self.session.flush()
        return removed

    async def reorder_pile_queue_positions(self, pile_id: int) -> None:
        entries = await self.get_pile_queue_entries(pile_id)
        for idx, entry in enumerate(entries, start=1):
            entry.position = idx
        await self.session.flush()

    async def get_all_waiting(self) -> list[WaitingQueue]:
        result = await self.session.execute(
            select(WaitingQueue).order_by(WaitingQueue.position.asc())
        )
        return list(result.scalars().all())

    async def get_total_waiting_and_queue_count(self) -> int:
        waiting = await self.session.execute(
            select(func.count(WaitingQueue.id))
        )
        queue = await self.session.execute(
            select(func.count(PileQueue.id))
        )
        return (waiting.scalar() or 0) + (queue.scalar() or 0)

    async def get_all_waiting_entries(self) -> list[WaitingQueue]:
        result = await self.session.execute(
            select(WaitingQueue).order_by(WaitingQueue.position.asc())
        )
        return list(result.scalars().all())
