import os
import re
import uuid
from collections import Counter
from datetime import datetime
import unicodedata

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import Base, engine, get_db
from app.deps import get_current_user, require_roles
from app.models import (
    Association,
    HousingSubset,
    HousingUnit,
    Notification,
    PushSubscription,
    User,
    UserScope,
    WorkOrder,
    WorkOrderHistory,
)
from app.notifications import create_notification, send_push_to_user
from app.schemas import (
    ManagerCreate,
    NotificationOut,
    PasswordResetIn,
    PushSubscriptionIn,
    ResidentCreate,
    ResidentOut,
    SubsetCreate,
    SubsetOut,
    Token,
    UserCreate,
    UserOut,
    WorkOrderAssign,
    WorkOrderOut,
    WorkOrderUpdateStatus,
)
from app.security import create_access_token, get_password_hash, verify_password

try:
    from app.endecos import enderecos as SOURCE_ENDERECOS
except Exception:
    SOURCE_ENDERECOS = {}

VALID_STATUSES = {"backlog", "fazendo", "pendentes", "concluido"}
VALID_PRIORITIES = {"baixa", "media", "alta", "urgente"}
VALID_CATEGORIES = {"eletrica", "hidraulica", "limpeza", "pintura", "seguranca", "outros"}

app = FastAPI(title="Condomínio OS PWA", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.upload_dir, exist_ok=True)
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


def get_or_create_default_association(db: Session) -> Association:
    association = db.query(Association).order_by(Association.id.asc()).first()
    if association:
        return association

    association = Association(name="Associação Principal")
    db.add(association)
    db.flush()
    return association


def get_or_create_default_subset(db: Session, association: Association) -> HousingSubset:
    subset = (
        db.query(HousingSubset)
        .filter(HousingSubset.association_id == association.id)
        .order_by(HousingSubset.id.asc())
        .first()
    )
    if subset:
        return subset

    subset = HousingSubset(association_id=association.id, name="Subcondomínio 1")
    db.add(subset)
    db.flush()
    return subset


def get_or_create_subset_by_name(db: Session, association_id: int, subset_name: str) -> HousingSubset:
    subset = (
        db.query(HousingSubset)
        .filter(HousingSubset.association_id == association_id, HousingSubset.name == subset_name)
        .first()
    )
    if subset:
        return subset

    subset = HousingSubset(association_id=association_id, name=subset_name)
    db.add(subset)
    db.flush()
    return subset


def parse_endereco_key(raw_key: str) -> tuple[str, str] | None:
    """
    Exemplo:
    - condominio1-1 -> (Condominio 1, 1)
    - condominio3-181 -> (Condominio 3, 181)
    """
    text = str(raw_key or "").strip().lower()
    match = re.fullmatch(r"condominio(\d+)-([a-z0-9]+)", text)
    if not match:
        return None

    subset_num = int(match.group(1))
    raw_unit = match.group(2).strip()
    unit_number = str(int(raw_unit)) if raw_unit.isdigit() else raw_unit.upper()
    subset_name = f"Condominio {subset_num}"
    return subset_name, unit_number


def populate_units_from_enderecos(db: Session, association: Association):
    if not isinstance(SOURCE_ENDERECOS, dict) or not SOURCE_ENDERECOS:
        return

    for key, coords in SOURCE_ENDERECOS.items():
        parsed = parse_endereco_key(key)
        if not parsed:
            continue
        subset_name, unit_number = parsed
        subset = get_or_create_subset_by_name(db, association.id, subset_name)

        lat = coords.get("lat") if isinstance(coords, dict) else None
        lng = coords.get("lng") if isinstance(coords, dict) else None
        latitude = float(lat) if lat is not None else None
        longitude = float(lng) if lng is not None else None

        create_or_get_unit(
            db,
            subset_id=subset.id,
            unit_number=unit_number,
            latitude=latitude,
            longitude=longitude,
        )


def create_or_get_unit(
    db: Session,
    subset_id: int,
    unit_number: str,
    latitude: float | None,
    longitude: float | None,
) -> HousingUnit:
    number = unit_number.strip()
    unit = db.query(HousingUnit).filter(HousingUnit.subset_id == subset_id, HousingUnit.number == number).first()
    if not unit:
        unit = HousingUnit(
            subset_id=subset_id,
            number=number,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(unit)
        db.flush()
        return unit

    if latitude is not None:
        unit.latitude = latitude
    if longitude is not None:
        unit.longitude = longitude
    db.flush()
    return unit


def get_user_scope(db: Session, user_id: int) -> UserScope | None:
    return db.query(UserScope).filter(UserScope.user_id == user_id).first()


def upsert_user_scope(
    db: Session,
    user_id: int,
    association_id: int,
    subset_id: int | None = None,
    unit_id: int | None = None,
) -> UserScope:
    scope = get_user_scope(db, user_id)
    if not scope:
        scope = UserScope(
            user_id=user_id,
            association_id=association_id,
            subset_id=subset_id,
            unit_id=unit_id,
        )
        db.add(scope)
    else:
        scope.association_id = association_id
        scope.subset_id = subset_id
        scope.unit_id = unit_id
    db.flush()
    return scope


def ensure_seed_users(db: Session):
    if db.query(User).count() == 0:
        seed = [
            User(
                username="admin1",
                full_name="Administrador Demo",
                role="administrador",
                apartment=None,
                password_hash=get_password_hash("123456"),
            ),
            User(
                username="morador1",
                full_name="Morador Demo",
                role="morador",
                apartment="101",
                password_hash=get_password_hash("123456"),
            ),
            User(
                username="sindico1",
                full_name="Síndico Demo",
                role="sindico",
                apartment=None,
                password_hash=get_password_hash("123456"),
            ),
            User(
                username="funcionario1",
                full_name="Funcionário Demo",
                role="funcionario",
                apartment=None,
                password_hash=get_password_hash("123456"),
            ),
        ]
        db.add_all(seed)
        db.flush()

    # Garantia de administrador mesmo em bases antigas já populadas.
    admin = db.query(User).filter(User.role == "administrador").first()
    if not admin:
        admin = User(
            username="admin1",
            full_name="Administrador Demo",
            role="administrador",
            apartment=None,
            password_hash=get_password_hash("123456"),
        )
        db.add(admin)
        db.flush()



def ensure_structure_and_scopes(db: Session):
    association = get_or_create_default_association(db)
    default_subset = get_or_create_default_subset(db, association)
    populate_units_from_enderecos(db, association)

    users = db.query(User).all()
    for user in users:
        scope = get_user_scope(db, user.id)
        if not scope:
            scope = upsert_user_scope(
                db,
                user_id=user.id,
                association_id=association.id,
                subset_id=None,
                unit_id=None,
            )

        if user.role == "administrador":
            upsert_user_scope(
                db,
                user_id=user.id,
                association_id=association.id,
                subset_id=None,
                unit_id=None,
            )
            continue

        if user.role in {"sindico", "funcionario"}:
            subset_id = scope.subset_id or default_subset.id
            upsert_user_scope(
                db,
                user_id=user.id,
                association_id=association.id,
                subset_id=subset_id,
                unit_id=None,
            )
            continue

        if user.role == "morador":
            subset_id = scope.subset_id or default_subset.id
            number = (user.apartment or str(user.id)).strip()
            unit = create_or_get_unit(db, subset_id=subset_id, unit_number=number, latitude=None, longitude=None)
            user.apartment = unit.number
            upsert_user_scope(
                db,
                user_id=user.id,
                association_id=association.id,
                subset_id=subset_id,
                unit_id=unit.id,
            )

    db.commit()



def create_history_entry(
    db: Session,
    work_order: WorkOrder,
    actor: User,
    from_status: str | None,
    to_status: str,
    note: str,
):
    entry = WorkOrderHistory(
        work_order_id=work_order.id,
        actor_user_id=actor.id,
        actor_name=actor.full_name,
        actor_role=actor.role,
        from_status=from_status,
        to_status=to_status,
        note=note,
    )
    db.add(entry)
    db.flush()
    return entry


def get_scope_subset_id(db: Session, user_id: int) -> int | None:
    scope = get_user_scope(db, user_id)
    return scope.subset_id if scope else None


def order_belongs_to_subset(db: Session, order: WorkOrder, subset_id: int | None) -> bool:
    if subset_id is None:
        return True
    creator_scope = get_user_scope(db, order.created_by_id)
    return bool(creator_scope and creator_scope.subset_id == subset_id)


def list_user_ids_by_subset(db: Session, subset_id: int) -> list[int]:
    return [user_id for (user_id,) in db.query(UserScope.user_id).filter(UserScope.subset_id == subset_id).all()]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalized_sql(column):
    expr = func.lower(func.coalesce(column, ""))
    replacements = [
        ("á", "a"),
        ("à", "a"),
        ("â", "a"),
        ("ã", "a"),
        ("ä", "a"),
        ("é", "e"),
        ("è", "e"),
        ("ê", "e"),
        ("ë", "e"),
        ("í", "i"),
        ("ì", "i"),
        ("î", "i"),
        ("ï", "i"),
        ("ó", "o"),
        ("ò", "o"),
        ("ô", "o"),
        ("õ", "o"),
        ("ö", "o"),
        ("ú", "u"),
        ("ù", "u"),
        ("û", "u"),
        ("ü", "u"),
        ("ç", "c"),
    ]
    for src, dst in replacements:
        expr = func.replace(expr, src, dst)
    return expr


def resident_out_from_user(db: Session, user: User) -> ResidentOut:
    scope = get_user_scope(db, user.id)
    subset = scope.subset if scope and scope.subset else None
    unit = scope.unit if scope and scope.unit else None
    return ResidentOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        apartment=user.apartment,
        subset_id=subset.id if subset else None,
        subset_name=subset.name if subset else None,
        unit_id=unit.id if unit else None,
        unit_number=unit.number if unit else None,
        latitude=unit.latitude if unit else None,
        longitude=unit.longitude if unit else None,
    )


@app.on_event("startup")
def startup_event():
    db = next(get_db())
    try:
        ensure_seed_users(db)
        ensure_structure_and_scopes(db)
    finally:
        db.close()


@app.get("/")
def root():
    return FileResponse("app/static/index.html")


@app.get("/sw.js")
def sw_file():
    return FileResponse("app/static/sw.js")


@app.get("/manifest.json")
def manifest_file():
    return FileResponse("app/static/manifest.json")


@app.post("/api/auth/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if payload.role not in {"morador", "sindico", "funcionario"}:
        raise HTTPException(status_code=400, detail="Perfil inválido")

    if payload.role == "morador" and not payload.apartment:
        raise HTTPException(status_code=400, detail="Apartamento é obrigatório para morador")

    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="Usuário já existe")

    association = get_or_create_default_association(db)
    default_subset = get_or_create_default_subset(db, association)

    user = User(
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        role=payload.role,
        apartment=payload.apartment.strip() if payload.apartment else None,
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    db.flush()

    subset_id = None
    unit_id = None
    if payload.role == "morador":
        unit = create_or_get_unit(
            db,
            subset_id=default_subset.id,
            unit_number=payload.apartment or str(user.id),
            latitude=None,
            longitude=None,
        )
        unit_id = unit.id
        subset_id = default_subset.id
        user.apartment = unit.number
    elif payload.role in {"sindico", "funcionario"}:
        subset_id = default_subset.id

    upsert_user_scope(
        db,
        user_id=user.id,
        association_id=association.id,
        subset_id=subset_id,
        unit_id=unit_id,
    )

    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha incorreto")

    token = create_access_token(user.username)
    return Token(access_token=token)


@app.get("/api/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/api/meta")
def meta_info():
    return {
        "roles": ["administrador", "morador", "sindico", "funcionario"],
        "statuses": ["backlog", "fazendo", "pendentes", "concluido"],
        "priorities": ["baixa", "media", "alta", "urgente"],
        "categories": ["eletrica", "hidraulica", "limpeza", "pintura", "seguranca", "outros"],
    }


@app.get("/api/admin/subsets", response_model=list[SubsetOut])
def list_subsets(
    current_user: User = Depends(require_roles("administrador", "sindico")),
    db: Session = Depends(get_db),
):
    current_scope = get_user_scope(db, current_user.id)
    if not current_scope:
        return []

    query = db.query(HousingSubset).filter(HousingSubset.association_id == current_scope.association_id)
    if current_user.role == "sindico" and current_scope.subset_id:
        query = query.filter(HousingSubset.id == current_scope.subset_id)

    return query.order_by(HousingSubset.name.asc()).all()


@app.post("/api/admin/subsets", response_model=SubsetOut)
def create_subset(
    payload: SubsetCreate,
    current_user: User = Depends(require_roles("administrador")),
    db: Session = Depends(get_db),
):
    scope = get_user_scope(db, current_user.id)
    if not scope:
        raise HTTPException(status_code=400, detail="Administrador sem escopo definido")

    exists = (
        db.query(HousingSubset)
        .filter(HousingSubset.association_id == scope.association_id, HousingSubset.name == payload.name.strip())
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Subconjunto já existe")

    subset = HousingSubset(
        association_id=scope.association_id,
        name=payload.name.strip(),
    )
    db.add(subset)
    db.commit()
    db.refresh(subset)
    return subset


@app.post("/api/admin/managers", response_model=UserOut)
def create_manager(
    payload: ManagerCreate,
    current_user: User = Depends(require_roles("administrador")),
    db: Session = Depends(get_db),
):
    requester_scope = get_user_scope(db, current_user.id)
    if not requester_scope:
        raise HTTPException(status_code=400, detail="Escopo do administrador não definido")

    subset = db.query(HousingSubset).filter(HousingSubset.id == payload.subset_id).first()
    if not subset:
        raise HTTPException(status_code=404, detail="Subconjunto não encontrado")

    if subset.association_id != requester_scope.association_id:
        raise HTTPException(status_code=403, detail="Subconjunto fora da sua associação")

    exists = db.query(User).filter(User.username == payload.username.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="Usuário já existe")

    manager = User(
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        role="sindico",
        apartment=None,
        password_hash=get_password_hash(payload.password),
    )
    db.add(manager)
    db.flush()

    upsert_user_scope(
        db,
        user_id=manager.id,
        association_id=subset.association_id,
        subset_id=subset.id,
        unit_id=None,
    )
    db.commit()
    db.refresh(manager)
    return manager


@app.post("/api/work-orders", response_model=WorkOrderOut)
def create_work_order(
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    priority: str = Form(...),
    image: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoria inválida")

    if priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail="Prioridade inválida")

    image_path = None
    if image:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Somente imagens são permitidas")

        ext = os.path.splitext(image.filename or "")[1] or ".jpg"
        file_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(settings.upload_dir, file_name)
        with open(file_path, "wb") as out:
            out.write(image.file.read())
        image_path = f"/uploads/{file_name}"

    order = WorkOrder(
        title=title,
        description=description,
        category=category,
        priority=priority,
        status="backlog",
        image_path=image_path,
        created_by_id=current_user.id,
    )
    db.add(order)
    db.flush()
    create_history_entry(
        db=db,
        work_order=order,
        actor=current_user,
        from_status=None,
        to_status="backlog",
        note="OS criada e enviada para o Backlog.",
    )

    creator_scope = get_user_scope(db, current_user.id)
    managers_query = db.query(User).filter(User.role == "sindico")
    if creator_scope and creator_scope.subset_id:
        manager_ids = (
            db.query(UserScope.user_id)
            .filter(UserScope.subset_id == creator_scope.subset_id)
            .all()
        )
        manager_ids = [item[0] for item in manager_ids]
        managers_query = managers_query.filter(User.id.in_(manager_ids))

    managers = managers_query.all()
    for manager in managers:
        create_notification(
            db,
            user_id=manager.id,
            title="Nova ordem de serviço",
            message=f"OS #{order.id}: {order.title}",
            work_order_id=order.id,
        )

    db.commit()
    db.refresh(order)
    return order


@app.get("/api/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(
    status_filter: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(WorkOrder).options(selectinload(WorkOrder.history))

    if current_user.role == "morador":
        query = query.filter(WorkOrder.created_by_id == current_user.id)

    if current_user.role == "funcionario":
        query = query.filter(or_(WorkOrder.assigned_to_id == current_user.id, WorkOrder.assigned_to_id.is_(None)))

    if current_user.role == "sindico":
        subset_id = get_scope_subset_id(db, current_user.id)
        if subset_id:
            resident_ids = list_user_ids_by_subset(db, subset_id)
            if not resident_ids:
                return []
            query = query.filter(WorkOrder.created_by_id.in_(resident_ids))

    if status_filter:
        query = query.filter(WorkOrder.status == status_filter)
    if category:
        query = query.filter(WorkOrder.category == category)
    if priority:
        query = query.filter(WorkOrder.priority == priority)
    if q:
        like_q = f"%{q}%"
        query = query.filter(or_(WorkOrder.title.ilike(like_q), WorkOrder.description.ilike(like_q)))

    return query.order_by(WorkOrder.created_at.desc()).all()


@app.patch("/api/work-orders/{work_order_id}/assign", response_model=WorkOrderOut)
def assign_work_order(
    work_order_id: int,
    payload: WorkOrderAssign,
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    if current_user.role == "sindico":
        sindico_subset = get_scope_subset_id(db, current_user.id)
        if not order_belongs_to_subset(db, order, sindico_subset):
            raise HTTPException(status_code=403, detail="Você não pode atribuir esta OS")

    if payload.assigned_to_id is not None:
        worker = db.query(User).filter(User.id == payload.assigned_to_id, User.role == "funcionario").first()
        if not worker:
            raise HTTPException(status_code=400, detail="Funcionário inválido")

        if current_user.role == "sindico":
            sindico_subset = get_scope_subset_id(db, current_user.id)
            worker_subset = get_scope_subset_id(db, worker.id)
            if sindico_subset and worker_subset != sindico_subset:
                raise HTTPException(status_code=403, detail="Funcionário fora do seu subconjunto")

    order.assigned_to_id = payload.assigned_to_id
    db.flush()

    if payload.assigned_to_id:
        create_notification(
            db,
            user_id=payload.assigned_to_id,
            title="Nova OS atribuída",
            message=f"Você recebeu a OS #{order.id}: {order.title}",
            work_order_id=order.id,
        )

    db.commit()
    db.refresh(order)
    return order


@app.patch("/api/work-orders/{work_order_id}/status", response_model=WorkOrderOut)
def update_status(
    work_order_id: int,
    payload: WorkOrderUpdateStatus,
    current_user: User = Depends(require_roles("sindico", "funcionario", "administrador")),
    db: Session = Depends(get_db),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Status inválido")

    order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    if current_user.role == "sindico":
        sindico_subset = get_scope_subset_id(db, current_user.id)
        if not order_belongs_to_subset(db, order, sindico_subset):
            raise HTTPException(status_code=403, detail="Você não pode alterar esta OS")

    if current_user.role == "funcionario":
        if order.assigned_to_id not in {None, current_user.id}:
            raise HTTPException(status_code=403, detail="Você não pode alterar esta OS")
        if order.assigned_to_id is None:
            order.assigned_to_id = current_user.id

    previous = order.status
    order.status = payload.status
    if payload.status == "concluido":
        order.resolved_at = datetime.utcnow()

    db.flush()

    changed_status = previous != payload.status
    note = (payload.note or "").strip()

    if changed_status or note:
        history_note = note or f"Status alterado de {previous} para {payload.status}."
        create_history_entry(
            db=db,
            work_order=order,
            actor=current_user,
            from_status=previous,
            to_status=payload.status,
            note=history_note,
        )

        notify_title = "Status da OS atualizado" if changed_status else "Atualização da OS"
        note_preview = history_note[:120]
        notify_msg = f"OS #{order.id} agora está em: {payload.status}. Atualização: {note_preview}"
        create_notification(db, order.created_by_id, notify_title, notify_msg, work_order_id=order.id)
        send_push_to_user(db, order.created_by_id, notify_title, notify_msg, work_order_id=order.id)

    db.commit()
    db.refresh(order)
    return order


@app.get("/api/workers", response_model=list[UserOut])
def list_workers(
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.role == "funcionario")
    if current_user.role == "sindico":
        subset_id = get_scope_subset_id(db, current_user.id)
        if subset_id:
            worker_ids = list_user_ids_by_subset(db, subset_id)
            if not worker_ids:
                return []
            query = query.filter(User.id.in_(worker_ids))
    return query.all()


@app.get("/api/admin/residents", response_model=list[ResidentOut])
def list_residents(
    q: str | None = None,
    subset_id: int | None = None,
    limit: int = 50,
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    query = db.query(User).join(UserScope, UserScope.user_id == User.id).filter(User.role == "morador")

    if current_user.role == "sindico":
        sindico_subset = get_scope_subset_id(db, current_user.id)
        if not sindico_subset:
            return []
        query = query.filter(UserScope.subset_id == sindico_subset)

    if current_user.role == "administrador" and subset_id:
        query = query.filter(UserScope.subset_id == subset_id)

    text = (q or "").strip()
    if text:
        tokens = [normalize_text(token) for token in text.split() if token.strip()]
        query = query.outerjoin(HousingUnit, HousingUnit.id == UserScope.unit_id).outerjoin(
            HousingSubset, HousingSubset.id == UserScope.subset_id
        )
        searchable_fields = [
            normalized_sql(User.full_name),
            normalized_sql(User.username),
            normalized_sql(User.apartment),
            normalized_sql(HousingUnit.number),
            normalized_sql(HousingSubset.name),
        ]
        conditions = []
        for token in tokens:
            like_q = f"%{token}%"
            conditions.append(or_(*[field.like(like_q) for field in searchable_fields]))
        if conditions:
            query = query.filter(and_(*conditions))

    residents = query.order_by(User.full_name.asc()).limit(limit).all()
    return [resident_out_from_user(db, user) for user in residents]


@app.post("/api/admin/residents", response_model=ResidentOut)
def create_resident(
    payload: ResidentCreate,
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    exists = db.query(User).filter(User.username == payload.username.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="Usuário já existe")

    requester_scope = get_user_scope(db, current_user.id)
    if not requester_scope:
        raise HTTPException(status_code=400, detail="Escopo do usuário não definido")

    target_subset_id = payload.subset_id
    if current_user.role == "sindico":
        target_subset_id = requester_scope.subset_id

    if not target_subset_id:
        default_subset = get_or_create_default_subset(db, get_or_create_default_association(db))
        target_subset_id = default_subset.id

    subset = db.query(HousingSubset).filter(HousingSubset.id == target_subset_id).first()
    if not subset:
        raise HTTPException(status_code=404, detail="Subconjunto não encontrado")

    if subset.association_id != requester_scope.association_id:
        raise HTTPException(status_code=403, detail="Subconjunto fora da sua associação")

    unit = create_or_get_unit(
        db,
        subset_id=subset.id,
        unit_number=payload.unit_number,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    resident = User(
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        role="morador",
        apartment=unit.number,
        password_hash=get_password_hash(payload.password),
    )
    db.add(resident)
    db.flush()

    upsert_user_scope(
        db,
        user_id=resident.id,
        association_id=subset.association_id,
        subset_id=subset.id,
        unit_id=unit.id,
    )

    db.commit()
    db.refresh(resident)
    return resident_out_from_user(db, resident)


@app.patch("/api/admin/residents/{resident_id}/reset-password")
def reset_resident_password(
    resident_id: int,
    payload: PasswordResetIn,
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    resident = db.query(User).filter(User.id == resident_id, User.role == "morador").first()
    if not resident:
        raise HTTPException(status_code=404, detail="Morador não encontrado")

    if current_user.role == "sindico":
        sindico_subset = get_scope_subset_id(db, current_user.id)
        resident_scope = get_user_scope(db, resident.id)
        if not resident_scope or resident_scope.subset_id != sindico_subset:
            raise HTTPException(status_code=403, detail="Morador fora do seu subconjunto")

    resident.password_hash = get_password_hash(payload.password)
    db.commit()
    return {"ok": True}


@app.get("/api/map/open-work-orders")
def open_work_orders_map(
    current_user: User = Depends(require_roles("sindico", "administrador")),
    db: Session = Depends(get_db),
):
    query = (
        db.query(WorkOrder, HousingUnit, HousingSubset)
        .join(UserScope, UserScope.user_id == WorkOrder.created_by_id)
        .join(HousingUnit, HousingUnit.id == UserScope.unit_id)
        .join(HousingSubset, HousingSubset.id == UserScope.subset_id)
        .filter(
            WorkOrder.status != "concluido",
            HousingUnit.latitude.isnot(None),
            HousingUnit.longitude.isnot(None),
        )
        .order_by(WorkOrder.created_at.desc())
    )

    if current_user.role == "sindico":
        sindico_subset = get_scope_subset_id(db, current_user.id)
        if not sindico_subset:
            return []
        query = query.filter(UserScope.subset_id == sindico_subset)

    rows = query.all()
    return [
        {
            "work_order_id": order.id,
            "title": order.title,
            "status": order.status,
            "priority": order.priority,
            "category": order.category,
            "subset_id": subset.id,
            "subset_name": subset.name,
            "unit_number": unit.number,
            "latitude": unit.latitude,
            "longitude": unit.longitude,
        }
        for order, unit, subset in rows
    ]


@app.get("/api/notifications", response_model=list[NotificationOut])
def list_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )


@app.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notificação não encontrada")

    notification.is_read = True
    db.commit()
    return {"ok": True}


@app.post("/api/push/subscribe")
def subscribe_push(
    payload: PushSubscriptionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == payload.endpoint).first()
    if not sub:
        sub = PushSubscription(
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            user_id=current_user.id,
        )
        db.add(sub)
    else:
        sub.user_id = current_user.id
        sub.p256dh = payload.keys.p256dh
        sub.auth = payload.keys.auth

    db.commit()
    return {"ok": True}


@app.get("/api/push/public-key")
def get_push_public_key():
    return {"publicKey": settings.vapid_public_key}


@app.get("/api/reports/summary")
def reports_summary(
    current_user: User = Depends(require_roles("sindico", "funcionario", "administrador")),
    db: Session = Depends(get_db),
):
    query = db.query(WorkOrder)

    if current_user.role == "funcionario":
        query = query.filter(WorkOrder.assigned_to_id == current_user.id)

    if current_user.role == "sindico":
        subset_id = get_scope_subset_id(db, current_user.id)
        if subset_id:
            resident_ids = list_user_ids_by_subset(db, subset_id)
            if not resident_ids:
                return {
                    "total_ordens": 0,
                    "por_status": {},
                    "por_categoria": {},
                    "por_prioridade": {},
                    "tempo_medio_resolucao_horas": 0,
                }
            query = query.filter(WorkOrder.created_by_id.in_(resident_ids))

    orders = query.all()
    total = len(orders)

    by_status = dict(Counter(order.status for order in orders))
    by_category = dict(Counter(order.category for order in orders))
    by_priority = dict(Counter(order.priority for order in orders))

    resolution_hours = []
    for order in orders:
        if order.resolved_at:
            delta = order.resolved_at - order.created_at
            resolution_hours.append(delta.total_seconds() / 3600)

    avg_resolution = round(sum(resolution_hours) / len(resolution_hours), 2) if resolution_hours else 0

    return {
        "total_ordens": total,
        "por_status": by_status,
        "por_categoria": by_category,
        "por_prioridade": by_priority,
        "tempo_medio_resolucao_horas": avg_resolution,
    }
