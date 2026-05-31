from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.simulation.clock import clock
from app.services.scheduling_service import SchedulingService
from app.services.billing_service import BillingService
from app.dao.order_dao import OrderDAO
from app.dao.queue_dao import QueueDAO
from app.models.charging_order import OrderStatus


class SimulationEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.scheduling = SchedulingService(session)
        self.order_dao = OrderDAO(session)
        self.queue_dao = QueueDAO(session)
        self.billing = BillingService(session)

    async def tick(self) -> dict:
        """Advance time by one tick and process all charging progress."""
        clock.tick()
        current_time = clock.now

        events = []

        orders = await self.order_dao.get_by_status(OrderStatus.CHARGING)
        for order in orders:
            if order.start_time is None:
                continue
            elapsed = (current_time - order.start_time).total_seconds() / 3600
            pile = await self.scheduling.pile_dao.get_by_id(order.pile_id)
            if not pile:
                continue
            charged_kwh = elapsed * pile.power_rate

            if charged_kwh >= order.requested_kwh:
                order.actual_kwh = order.requested_kwh
                order.end_time = current_time
                await self.scheduling.end_charging(order.id)
                events.append(f"订单 {order.queue_number} 充电完成")

        dispatched = await self.scheduling.dispatch_from_waiting_area()
        if dispatched > 0:
            events.append(f"调度 {dispatched} 辆车进入充电区")

        return {
            "current_time": current_time.isoformat(),
            "events": events,
            "dispatched": dispatched,
        }

    async def fast_forward(self, target_time: datetime) -> dict:
        """Fast forward to a target time, processing ticks."""
        total_events = []
        while clock.now < target_time:
            result = await self.tick()
            total_events.extend(result["events"])
        return {"current_time": clock.now.isoformat(), "events": total_events}
