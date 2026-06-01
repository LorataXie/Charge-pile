"""仿真引擎 – 在一个 Tick 内按实际完成时刻推进充电。"""
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.simulation.clock import clock
from app.services.scheduling_service import SchedulingService
from app.dao.order_dao import OrderDAO
from app.models.charging_order import OrderStatus


class SimulationEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.scheduling = SchedulingService(session)
        self.order_dao = OrderDAO(session)

    async def tick(self) -> dict:
        """推进一个 Tick；若订单中途充满，详单按真实完成时刻生成。"""
        tick_start = clock.now
        tick_end = tick_start + timedelta(minutes=clock.tick_minutes)
        cursor = tick_start
        events = []

        while cursor < tick_end:
            orders = await self.order_dao.get_by_status(OrderStatus.CHARGING)
            if not orders:
                break

            charging = []
            next_finish = None
            for order in orders:
                pile = await self.scheduling.pile_dao.get_by_id(order.pile_id)
                if not pile:
                    continue
                remaining_kwh = max(order.requested_kwh - (order.actual_kwh or 0), 0)
                hours_to_finish = remaining_kwh / pile.power_rate if pile.power_rate else 0
                finish_at = cursor + timedelta(hours=hours_to_finish)
                charging.append((order, pile, finish_at))
                if next_finish is None or finish_at < next_finish:
                    next_finish = finish_at

            if not charging or next_finish is None:
                break

            step_end = min(next_finish, tick_end)
            elapsed_hours = (step_end - cursor).total_seconds() / 3600

            for order, pile, _ in charging:
                order.actual_kwh = min(
                    order.requested_kwh,
                    (order.actual_kwh or 0) + elapsed_hours * pile.power_rate,
                )
                self.session.add(order)
            await self.session.flush()

            cursor = step_end
            clock.set(cursor)

            if step_end >= tick_end:
                break

            completed = [
                order for order, _, finish_at in charging
                if finish_at == step_end or order.actual_kwh >= order.requested_kwh
            ]
            for order in completed:
                await self.scheduling.end_charging(order.id, end_time=step_end)
                events.append(f"订单 {order.queue_number} 充电完成")

        clock.set(tick_end)
        dispatched = await self.scheduling.dispatch_from_waiting_area()
        if dispatched > 0:
            events.append(f"从等候区调度 {dispatched} 辆车入桩")

        return {
            "current_time": clock.now.isoformat(),
            "events": events,
            "dispatched": dispatched,
        }
