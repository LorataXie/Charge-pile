"""仿真引擎 — 累进式充电，不依赖绝对时钟差值。"""
from datetime import datetime
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
        """每 Tick 对所有充电中订单累加 (tick_minutes/60)*功率 度电量。"""
        tick_hours = clock.tick_minutes / 60.0  # 默认 0.25h
        clock.tick()
        events = []

        orders = await self.order_dao.get_by_status(OrderStatus.CHARGING)
        for order in orders:
            pile = await self.scheduling.pile_dao.get_by_id(order.pile_id)
            if not pile:
                continue

            # 累进充电：本次 Tick 充入的电量
            charged_this_tick = tick_hours * pile.power_rate
            order.actual_kwh = (order.actual_kwh or 0) + charged_this_tick

            if order.actual_kwh >= order.requested_kwh:
                order.actual_kwh = order.requested_kwh
                order.end_time = clock.now
                await self.scheduling.end_charging(order.id)
                events.append(f"订单 {order.queue_number} 充电完成")
            else:
                # 仍在充，刷新 actual_kwh
                self.session.add(order)
                await self.session.flush()

        dispatched = await self.scheduling.dispatch_from_waiting_area()
        if dispatched > 0:
            events.append(f"从等候区调度 {dispatched} 辆车入桩")

        return {
            "current_time": clock.now.isoformat(),
            "events": events,
            "dispatched": dispatched,
        }
