from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.fault_dao import FaultDAO
from app.dao.order_dao import OrderDAO
from app.dao.queue_dao import QueueDAO
from app.models.fault_record import FaultRecord, FaultStatus
from app.models.charging_pile import PileStatus


class FaultService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = FaultDAO(session)
        self.order_dao = OrderDAO(session)
        self.queue_dao = QueueDAO(session)

    async def report_fault(self, pile_id: int, reported_by: int, strategy: str = "PRIORITY") -> FaultRecord:
        record = FaultRecord(
            pile_id=pile_id,
            reported_by=reported_by,
            fault_time=datetime.now(),
            strategy_used=strategy,
            affected_order_count=0,
            status=FaultStatus.ACTIVE,
        )
        return await self.dao.create(record)

    async def resolve_fault(self, fault_id: int) -> FaultRecord:
        record = await self.dao.get_by_id(fault_id)
        if not record:
            raise ValueError("故障记录不存在")
        record.status = FaultStatus.RESOLVED
        record.resolved_time = datetime.now()
        return await self.dao.update(record)

    async def get_active_faults(self) -> list[FaultRecord]:
        return await self.dao.get_active_faults()

    async def get_fault(self, fault_id: int) -> FaultRecord | None:
        return await self.dao.get_by_id(fault_id)

    async def get_all_faults(self) -> list[FaultRecord]:
        return list(await self.dao.get_all())
