from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class ChargingDetail(BaseModel):
    __tablename__ = "charging_details"

    order_id: Mapped[int] = mapped_column(ForeignKey("charging_orders.id"), nullable=False)
    pile_id: Mapped[int] = mapped_column(ForeignKey("charging_piles.id"), nullable=False)
    total_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    charge_duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    peak_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    normal_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valley_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    peak_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    normal_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valley_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    service_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_fault_interrupted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def charging_fee(self) -> float:
        return round(self.peak_fee + self.normal_fee + self.valley_fee, 2)
