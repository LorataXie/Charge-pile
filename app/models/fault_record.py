from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
import enum


class FaultStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class FaultRecord(BaseModel):
    __tablename__ = "fault_records"

    pile_id: Mapped[int] = mapped_column(ForeignKey("charging_piles.id"), nullable=False)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    fault_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    strategy_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    affected_order_count: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[FaultStatus] = mapped_column(SQLEnum(FaultStatus), default=FaultStatus.ACTIVE, nullable=False)
