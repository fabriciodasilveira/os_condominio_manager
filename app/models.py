from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Association(Base):
    __tablename__ = "associations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subsets: Mapped[list["HousingSubset"]] = relationship(back_populates="association")
    user_scopes: Mapped[list["UserScope"]] = relationship(back_populates="association")


class HousingSubset(Base):
    __tablename__ = "housing_subsets"
    __table_args__ = (
        UniqueConstraint("association_id", "name", name="uq_subset_association_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    association_id: Mapped[int] = mapped_column(ForeignKey("associations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    association: Mapped["Association"] = relationship(back_populates="subsets")
    units: Mapped[list["HousingUnit"]] = relationship(back_populates="subset")
    user_scopes: Mapped[list["UserScope"]] = relationship(back_populates="subset")


class HousingUnit(Base):
    __tablename__ = "housing_units"
    __table_args__ = (
        UniqueConstraint("subset_id", "number", name="uq_unit_subset_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subset_id: Mapped[int] = mapped_column(ForeignKey("housing_subsets.id"), index=True)
    number: Mapped[str] = mapped_column(String(30), index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subset: Mapped["HousingSubset"] = relationship(back_populates="units")
    user_scopes: Mapped[list["UserScope"]] = relationship(back_populates="unit")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), index=True)
    apartment: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    created_orders: Mapped[list["WorkOrder"]] = relationship(
        back_populates="created_by", foreign_keys="WorkOrder.created_by_id"
    )
    assigned_orders: Mapped[list["WorkOrder"]] = relationship(
        back_populates="assigned_to", foreign_keys="WorkOrder.assigned_to_id"
    )
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["PushSubscription"]] = relationship(back_populates="user")
    scope: Mapped["UserScope | None"] = relationship(back_populates="user", uselist=False)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(140), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="backlog", index=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    created_by: Mapped["User"] = relationship(back_populates="created_orders", foreign_keys=[created_by_id])
    assigned_to: Mapped["User | None"] = relationship(back_populates="assigned_orders", foreign_keys=[assigned_to_id])
    history: Mapped[list["WorkOrderHistory"]] = relationship(
        back_populates="work_order",
        cascade="all, delete-orphan",
        order_by="WorkOrderHistory.created_at.desc()",
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="notifications")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(500), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class UserScope(Base):
    __tablename__ = "user_scopes"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    association_id: Mapped[int] = mapped_column(ForeignKey("associations.id"), index=True)
    subset_id: Mapped[int | None] = mapped_column(ForeignKey("housing_subsets.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("housing_units.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="scope")
    association: Mapped["Association"] = relationship(back_populates="user_scopes")
    subset: Mapped["HousingSubset | None"] = relationship(back_populates="user_scopes")
    unit: Mapped["HousingUnit | None"] = relationship(back_populates="user_scopes")


class WorkOrderHistory(Base):
    __tablename__ = "work_order_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(120))
    actor_role: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="history")
