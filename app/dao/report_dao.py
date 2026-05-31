from sqlalchemy.ext.asyncio import AsyncSession
from app.dao.base import BaseDAO
from app.models.report import Report


class ReportDAO(BaseDAO[Report]):
    model = Report

    def __init__(self, session: AsyncSession):
        super().__init__(session)
