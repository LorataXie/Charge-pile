from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.charging_detail import ChargingDetail
from app.models.charging_pile import ChargingPile


class DetailDAO(BaseDAO[ChargingDetail]):
    model = ChargingDetail

    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_order_id(self, order_id: int) -> ChargingDetail | None:
        result = await self.session.execute(
            select(ChargingDetail).where(ChargingDetail.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_time_range(
        self, start: datetime, end: datetime
    ) -> list[ChargingDetail]:
        result = await self.session.execute(
            select(ChargingDetail).where(
                ChargingDetail.end_time >= start,
                ChargingDetail.end_time < end
            )
        )
        return list(result.scalars().all())

    async def get_aggregated_by_pile(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        result = await self.session.execute(
            select(
                ChargingDetail.pile_id,
                func.count(ChargingDetail.id).label("charge_count"),
                func.sum(ChargingDetail.charge_duration_hours).label("total_duration"),
                func.sum(ChargingDetail.total_kwh).label("total_kwh"),
                func.sum(ChargingDetail.peak_fee).label("total_peak_fee"),
                func.sum(ChargingDetail.normal_fee).label("total_normal_fee"),
                func.sum(ChargingDetail.valley_fee).label("total_valley_fee"),
                func.sum(ChargingDetail.service_fee).label("total_service_fee"),
                func.sum(ChargingDetail.total_fee).label("total_fee"),
            )
            .where(ChargingDetail.end_time >= start, ChargingDetail.end_time < end)
            .group_by(ChargingDetail.pile_id)
        )
        return [
            {
                "pile_id": row[0],
                "charge_count": row[1],
                "total_duration": float(row[2] or 0),
                "total_kwh": float(row[3] or 0),
                "total_peak_fee": float(row[4] or 0),
                "total_normal_fee": float(row[5] or 0),
                "total_valley_fee": float(row[6] or 0),
                "total_service_fee": float(row[7] or 0),
                "total_fee": float(row[8] or 0),
            }
            for row in result.all()
        ]
