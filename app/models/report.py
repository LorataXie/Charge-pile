from datetime import datetime
from sqlalchemy import String, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
import enum


class ReportType(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class Report(BaseModel):
    __tablename__ = "reports"

    report_type: Mapped[ReportType] = mapped_column(SQLEnum(ReportType), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False)
