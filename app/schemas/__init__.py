from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4)
    role: str = Field(default="client")


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    model_config = {"from_attributes": True}


class ChargeRequest(BaseModel):
    vehicle_id: int
    mode: str = Field(..., pattern="^[FT]$")
    requested_kwh: float = Field(..., gt=0)


class ModifyChargeRequest(BaseModel):
    new_mode: Optional[str] = Field(None, pattern="^[FT]$")
    new_kwh: Optional[float] = Field(None, gt=0)


class ChargeOrderResponse(BaseModel):
    id: int
    user_id: int
    vehicle_id: int
    queue_number: Optional[str]
    mode: str
    requested_kwh: float
    actual_kwh: Optional[float]
    status: str
    pile_id: Optional[int]
    queue_position: Optional[int]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class QueueStatusResponse(BaseModel):
    order_id: int
    queue_number: Optional[str]
    mode: str
    status: str
    waiting_count_ahead: int
    pile_id: Optional[int]


class PileResponse(BaseModel):
    id: int
    pile_code: str
    mode: str
    power_rate: float
    status: str
    total_charge_count: int
    total_charge_duration: float
    total_charge_kwh: float

    model_config = {"from_attributes": True}


class PileWithVehicles(BaseModel):
    id: int
    pile_code: str
    mode: str
    power_rate: float
    status: str
    total_charge_count: int
    total_charge_duration: float
    total_charge_kwh: float
    queue_vehicles: list[dict] = []

    model_config = {"from_attributes": True}


class BillingDetailResponse(BaseModel):
    id: int
    order_id: int
    pile_id: int
    total_kwh: float
    charge_duration_hours: float
    start_time: datetime
    end_time: datetime
    peak_kwh: float
    normal_kwh: float
    valley_kwh: float
    peak_fee: float  # 峰时充电费用
    normal_fee: float  # 平时充电费用
    valley_fee: float  # 谷时充电费用
    charging_fee: float = 0.0  # 充电费用合计 = peak_fee + normal_fee + valley_fee
    service_fee: float
    total_fee: float
    is_fault_interrupted: bool
    created_at: datetime  # 详单生成时间

    model_config = {"from_attributes": True}


class FaultReportRequest(BaseModel):
    strategy: str = Field(default="PRIORITY", pattern="^(PRIORITY|TIME_ORDER)$")


class FaultRescheduleRequest(BaseModel):
    strategy: str = Field(default="PRIORITY", pattern="^(PRIORITY|TIME_ORDER)$")


class FaultResponse(BaseModel):
    id: int
    pile_id: int
    reported_by: int
    fault_time: datetime
    resolved_time: Optional[datetime]
    strategy_used: Optional[str]
    affected_order_count: int
    status: str

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    report_type: str = Field(..., pattern="^(DAILY|WEEKLY|MONTHLY)$")
    period_start: Optional[datetime] = None


class ReportResponse(BaseModel):
    id: int
    report_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    report_data: dict

    model_config = {"from_attributes": True}


class SimTimeResponse(BaseModel):
    current_time: str
    tick_minutes: int


class MessageResponse(BaseModel):
    message: str
    detail: Optional[dict] = None
