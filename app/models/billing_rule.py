from sqlalchemy import String, Float, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
import enum


class PeriodType(str, enum.Enum):
    PEAK = "PEAK"
    NORMAL = "NORMAL"
    VALLEY = "VALLEY"


class BillingRule(BaseModel):
    __tablename__ = "billing_rules"

    period_type: Mapped[PeriodType] = mapped_column(SQLEnum(PeriodType), nullable=False)
    price_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    service_fee_per_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    start_hour: Mapped[int] = mapped_column(nullable=False)
    end_hour: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(String(100), nullable=True)
