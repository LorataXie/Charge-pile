from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class WaitingQueue(BaseModel):
    __tablename__ = "waiting_queue"

    order_id: Mapped[int] = mapped_column(ForeignKey("charging_orders.id"), unique=True, nullable=False)
    queue_number: Mapped[str] = mapped_column(String(10), nullable=False)
    mode: Mapped[str] = mapped_column(String(1), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
