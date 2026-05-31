from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.detail_dao import DetailDAO
from app.models.charging_detail import ChargingDetail
from app.models.charging_order import ChargingOrder

PEAK_PRICE = 1.0
NORMAL_PRICE = 0.7
VALLEY_PRICE = 0.4
SERVICE_FEE_PER_KWH = 0.8


def _get_period(hour: int) -> str:
    if (10 <= hour < 15) or (18 <= hour < 21):
        return "PEAK"
    if (7 <= hour < 10) or (15 <= hour < 18) or (21 <= hour < 23):
        return "NORMAL"
    return "VALLEY"


def _get_period_end(current_time: datetime) -> datetime:
    """返回 current_time 所在计费时段的下一个边界时刻。
    23:00 之后的下一个是次日 0:00（谷时从 23 到次日 7），
    因此不能 replace(hour=24)（Python 不支持），改用 timedelta。
    """
    h = current_time.hour
    boundaries = [7, 10, 15, 18, 21, 23]
    for b in boundaries:
        period_start = current_time.replace(hour=b, minute=0, second=0, microsecond=0)
        if period_start > current_time:
            return period_start
    # 超过 23:00 → 次日 0:00
    from datetime import timedelta
    return (current_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = DetailDAO(session)

    async def calculate_billing(
        self, order: ChargingOrder, pile_power_rate: float,
        is_fault_interrupted: bool = False
    ) -> ChargingDetail:
        duration_hours = (order.end_time - order.start_time).total_seconds() / 3600
        actual_kwh = min(duration_hours * pile_power_rate, order.requested_kwh)
        peak_kwh, normal_kwh, valley_kwh = self._slice_by_period(
            order.start_time, order.end_time, pile_power_rate, actual_kwh
        )

        detail = ChargingDetail(
            order_id=order.id,
            pile_id=order.pile_id,
            total_kwh=round(actual_kwh, 4),
            charge_duration_hours=round(duration_hours, 4),
            start_time=order.start_time,
            end_time=order.end_time,
            peak_kwh=round(peak_kwh, 4),
            normal_kwh=round(normal_kwh, 4),
            valley_kwh=round(valley_kwh, 4),
            peak_fee=round(peak_kwh * PEAK_PRICE, 2),
            normal_fee=round(normal_kwh * NORMAL_PRICE, 2),
            valley_fee=round(valley_kwh * VALLEY_PRICE, 2),
            service_fee=round(actual_kwh * SERVICE_FEE_PER_KWH, 2),
            total_fee=round(
                peak_kwh * PEAK_PRICE + normal_kwh * NORMAL_PRICE +
                valley_kwh * VALLEY_PRICE + actual_kwh * SERVICE_FEE_PER_KWH, 2
            ),
            is_fault_interrupted=is_fault_interrupted,
        )
        return detail

    def _slice_by_period(self, start: datetime, end: datetime, power_rate: float, max_kwh: float):
        peak_kwh = 0.0
        normal_kwh = 0.0
        valley_kwh = 0.0
        total_sliced = 0.0
        current = start

        while current < end and total_sliced < max_kwh:
            period = _get_period(current.hour)
            period_end = min(_get_period_end(current), end)
            slice_hours = (period_end - current).total_seconds() / 3600
            slice_kwh = min(slice_hours * power_rate, max_kwh - total_sliced)

            if period == "PEAK":
                peak_kwh += slice_kwh
            elif period == "NORMAL":
                normal_kwh += slice_kwh
            else:
                valley_kwh += slice_kwh

            total_sliced += slice_kwh
            current = period_end

        return peak_kwh, normal_kwh, valley_kwh

    async def save_detail(self, detail: ChargingDetail) -> ChargingDetail:
        return await self.dao.create(detail)

    async def get_detail(self, order_id: int) -> ChargingDetail | None:
        return await self.dao.get_by_order_id(order_id)
