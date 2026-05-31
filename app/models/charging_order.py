from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
import enum


class OrderStatus(str, enum.Enum):
    WAITING = "WAITING"
    QUEUED = "QUEUED"
    CHARGING = "CHARGING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAULT_INTERRUPTED = "FAULT_INTERRUPTED"


class ChargingOrder(BaseModel):
    __tablename__ = "charging_orders"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    queue_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mode: Mapped[str] = mapped_column(String(1), nullable=False)
    requested_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    actual_kwh: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus), default=OrderStatus.WAITING, nullable=False)
    pile_id: Mapped[int | None] = mapped_column(ForeignKey("charging_piles.id"), nullable=True)
    queue_position: Mapped[int | None] = mapped_column(nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
