from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.detail_dao import DetailDAO
from app.dao.report_dao import ReportDAO
from app.models.report import Report, ReportType


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.detail_dao = DetailDAO(session)
        self.dao = ReportDAO(session)

    async def generate_report(self, report_type_str: str, period_start: datetime | None = None) -> Report:
        report_type = ReportType(report_type_str.upper())
        now = datetime.now()
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
        report = Report(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            generated_at=now,
            report_data={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "piles": aggregation,
                "summary": {
                    "total_charges": sum(p["charge_count"] for p in aggregation),
                    "total_kwh": sum(p["total_kwh"] for p in aggregation),
                    "total_fee": sum(p["total_fee"] for p in aggregation),
                }
            }
        )
        return await self.dao.create(report)

    async def get_reports(self) -> list[Report]:
        return list(await self.dao.get_all())

    async def get_report(self, report_id: int) -> Report | None:
        return await self.dao.get_by_id(report_id)
