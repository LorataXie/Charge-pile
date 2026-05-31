from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel
import enum


class PileStatus(str, enum.Enum):
    IDLE = "IDLE"
    CHARGING = "CHARGING"
    BROKEN = "BROKEN"
    STOPPED = "STOPPED"


class ChargingPile(BaseModel):
    __tablename__ = "charging_piles"

    pile_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(1), nullable=False)
    power_rate: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[PileStatus] = mapped_column(SQLEnum(PileStatus), default=PileStatus.IDLE, nullable=False)
    total_charge_count: Mapped[int] = mapped_column(default=0, nullable=False)
    total_charge_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_charge_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
