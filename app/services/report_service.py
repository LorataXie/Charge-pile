from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.dao.detail_dao import DetailDAO
from app.dao.report_dao import ReportDAO
from app.models.charging_pile import ChargingPile
from app.models.report import Report, ReportType
from app.simulation.clock import clock


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.detail_dao = DetailDAO(session)
        self.dao = ReportDAO(session)

    async def generate_report(self, report_type_str: str, period_start: datetime | None = None) -> Report:
        report_type = ReportType(report_type_str.upper())
        now = clock.now
        if period_start is None:
            if report_type == ReportType.DAILY:
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = period_start + timedelta(days=1)
            elif report_type == ReportType.WEEKLY:
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
                period_end = period_start + timedelta(days=7)
            else:
                period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                period_end = (period_start + timedelta(days=32)).replace(day=1)
        else:
            if report_type == ReportType.DAILY:
                period_end = period_start + timedelta(days=1)
            elif report_type == ReportType.WEEKLY:
                period_end = period_start + timedelta(days=7)
            else:
                period_end = (period_start + timedelta(days=32)).replace(day=1)

        aggregation = await self.detail_dao.get_aggregated_by_pile(period_start, period_end)
        rows_by_pile = {row["pile_id"]: row for row in aggregation}
        pile_result = await self.session.execute(
            select(ChargingPile).order_by(ChargingPile.mode.asc(), ChargingPile.pile_code.asc())
        )
        piles = list(pile_result.scalars().all())
        report_rows = []
        for pile in piles:
            row = rows_by_pile.get(pile.id, {})
            report_rows.append({
                "pile_id": pile.id,
                "pile_code": pile.pile_code,
                "charge_count": row.get("charge_count", 0),
                "total_duration": row.get("total_duration", 0.0),
                "total_kwh": row.get("total_kwh", 0.0),
                "total_peak_fee": row.get("total_peak_fee", 0.0),
                "total_normal_fee": row.get("total_normal_fee", 0.0),
                "total_valley_fee": row.get("total_valley_fee", 0.0),
                "total_service_fee": row.get("total_service_fee", 0.0),
                "total_fee": row.get("total_fee", 0.0),
            })

        report = Report(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            generated_at=now,
            report_data={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "piles": report_rows,
                "summary": {
                    "total_charges": sum(p["charge_count"] for p in report_rows),
                    "total_duration": sum(p["total_duration"] for p in report_rows),
                    "total_kwh": sum(p["total_kwh"] for p in report_rows),
                    "total_charging_fee": sum(
                        p["total_peak_fee"] + p["total_normal_fee"] + p["total_valley_fee"]
                        for p in report_rows
                    ),
                    "total_service_fee": sum(p["total_service_fee"] for p in report_rows),
                    "total_fee": sum(p["total_fee"] for p in report_rows),
                }
            }
        )
        return await self.dao.create(report)

    async def get_reports(self) -> list[Report]:
        return list(await self.dao.get_all())

    async def get_report(self, report_id: int) -> Report | None:
        return await self.dao.get_by_id(report_id)
