from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class Vehicle(BaseModel):
    __tablename__ = "vehicles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    battery_capacity: Mapped[float] = mapped_column(Float, nullable=False)
