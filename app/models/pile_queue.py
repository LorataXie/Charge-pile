from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class PileQueue(BaseModel):
    __tablename__ = "pile_queue"

    order_id: Mapped[int] = mapped_column(ForeignKey("charging_orders.id"), unique=True, nullable=False)
    pile_id: Mapped[int] = mapped_column(ForeignKey("charging_piles.id"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    is_charging: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
