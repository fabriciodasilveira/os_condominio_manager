from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RoleType = Literal["administrador", "morador", "sindico", "funcionario"]
StatusType = Literal["backlog", "fazendo", "pendentes", "concluido"]
PriorityType = Literal["baixa", "media", "alta", "urgente"]
CategoryType = Literal["eletrica", "hidraulica", "limpeza", "pintura", "seguranca", "outros"]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=3, max_length=120)
    role: RoleType
    apartment: str | None = Field(default=None, max_length=30)


class ResidentCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=3, max_length=120)
    subset_id: int | None = None
    unit_number: str = Field(min_length=1, max_length=30)
    latitude: float | None = None
    longitude: float | None = None
    password: str = Field(min_length=6)


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=6)


class SubsetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class SubsetOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class ManagerCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=3, max_length=120)
    subset_id: int
    password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: RoleType
    apartment: str | None

    class Config:
        from_attributes = True


class ResidentOut(BaseModel):
    id: int
    username: str
    full_name: str
    apartment: str | None
    subset_id: int | None
    subset_name: str | None
    unit_id: int | None
    unit_number: str | None
    latitude: float | None
    longitude: float | None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class WorkOrderOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    priority: str
    status: str
    image_path: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    created_by_id: int
    assigned_to_id: int | None
    history: list["WorkOrderHistoryOut"] = Field(default_factory=list)

    class Config:
        from_attributes = True


class WorkOrderUpdateStatus(BaseModel):
    status: StatusType
    note: str | None = Field(default=None, max_length=1000)


class WorkOrderAssign(BaseModel):
    assigned_to_id: int | None


class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    work_order_id: int | None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: PushKeys


class WorkOrderHistoryOut(BaseModel):
    id: int
    actor_name: str
    actor_role: str
    from_status: str | None
    to_status: str
    note: str
    created_at: datetime

    class Config:
        from_attributes = True


WorkOrderOut.model_rebuild()
