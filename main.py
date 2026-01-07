# TrojanTracks/api/main.py
from __future__ import annotations

# ── stdlib ─────────────────────────────────────────────────────────────────────
import os
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Dict

# ── third-party ────────────────────────────────────────────────────────────────
from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field, ConfigDict
from passlib.hash import bcrypt
from sqlalchemy import (
    String, Text, Boolean, ForeignKey, func, select, delete, update, Integer,
    UniqueConstraint, or_, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# --------------------------
# Config
# --------------------------
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

_raw = os.getenv(
    "ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
ALLOW_ORIGINS = [o.strip() for o in _raw if o.strip()]

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-prod")
JWT_ALG = "HS256"
ACCESS_MIN = int(os.getenv("ACCESS_MIN", "120"))  # 2h default
RESET_TOKEN_TTL_MIN = int(os.getenv("RESET_TOKEN_TTL_MIN", "60"))


def _now_utc() -> datetime:
    return datetime.utcnow()


# --------------------------
# App & CORS
# --------------------------
# NEW:
# Serve static files (CSS, images)
app = FastAPI(title="TrojanTracks API – Teams/Tasks/Messages")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (if they exist)
if os.path.isdir("../static"):
    app.mount("/static", StaticFiles(directory="../static"), name="static")
# Serve static UI at /app (if folder exists)
# app.mount("/app", StaticFiles(directory="static", html=True), name="static")


# --------------------------
# DB
# --------------------------
engine = create_async_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


# --------------------------
# Models
# --------------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, default=None)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    reset_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    memberships: Mapped[List["TeamMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages_sent: Mapped[List["Message"]] = relationship(back_populates="sender", foreign_keys="Message.sender_id")
    task_assignments: Mapped[List["TaskAssignee"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    key: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    columns: Mapped[List["Column"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    teams: Mapped[List["Team"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    
    project: Mapped["Project"] = relationship(back_populates="teams")
    members: Mapped[List["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="member")  # member, lead
    
    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")
    
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)


class Column(Base):
    __tablename__ = "columns"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    
    project: Mapped["Project"] = relationship(back_populates="columns")
    tasks: Mapped[List["Task"]] = relationship(back_populates="column", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    column_id: Mapped[Optional[int]] = mapped_column(ForeignKey("columns.id", ondelete="SET NULL"), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    rank: Mapped[Optional[float]] = mapped_column(Float, default=1000.0)
    
    project: Mapped["Project"] = relationship(back_populates="tasks")
    column: Mapped[Optional["Column"]] = relationship(back_populates="tasks")
    assignees: Mapped[List["TaskAssignee"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    task: Mapped["Task"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship(back_populates="task_assignments")
    
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_user"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(20), default="GLOBAL")  # GLOBAL, TEAM, USER
    text: Mapped[str] = mapped_column(Text)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    recipient_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id], back_populates="messages_sent")


# --------------------------
# Schemas
# --------------------------
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: Optional[str] = None


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetIn(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=6, max_length=128)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=2, max_length=10)


class ProjectOut(BaseModel):
    id: int
    name: str
    key: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: int


class TeamMemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    project_id: int
    order: int = 0


class ColumnOut(BaseModel):
    id: int
    name: str
    project_id: int
    order: int
    model_config = ConfigDict(from_attributes=True)


class TaskAssigneeOut(BaseModel):
    user_id: int
    username: str
    is_completed: bool
    completed_at: Optional[datetime] = None
    completed_summary: Optional[str] = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    project_id: int
    column_id: Optional[int] = None
    assignee_ids: Optional[List[int]] = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    project_id: int
    column_id: Optional[int] = None
    is_completed: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    assignees: List[TaskAssigneeOut] = []
    model_config = ConfigDict(from_attributes=True)


class TaskCompleteIn(BaseModel):
    summary: str = Field(min_length=1)


class TaskAssigneesChange(BaseModel):
    add: Optional[List[int]] = None
    remove: Optional[List[int]] = None


class ProgressOut(BaseModel):
    project_id: int
    total: int
    completed: int
    percent: float


class MessageCreate(BaseModel):
    text: str = Field(min_length=1)
    project_id: Optional[int] = None
    team_id: Optional[int] = None
    recipient_user_id: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    sender_id: int
    scope: str
    text: str
    project_id: Optional[int] = None
    team_id: Optional[int] = None
    recipient_user_id: Optional[int] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --------------------------
# Auth helpers
# --------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(pw: str) -> str:
    return bcrypt.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.verify(pw, hashed)


def create_access_token(data: dict, minutes: int = ACCESS_MIN) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=minutes)})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    cred_exc = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = int(payload.get("sub", 0))
    except JWTError:
        raise cred_exc
    user = await db.scalar(select(User).where(User.id == uid))
    if not user:
        raise cred_exc
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


async def is_team_admin_or_lead(project_id: int, user: User, db: AsyncSession) -> bool:
    if user.is_admin:
        return True
    lead = await db.scalar(
        select(TeamMember)
        .join(Team)
        .where(Team.project_id == project_id, TeamMember.user_id == user.id, TeamMember.role == "lead")
    )
    return lead is not None


async def require_admin_or_lead_for_project(project_id: int, user: User, db: AsyncSession):
    if not await is_team_admin_or_lead(project_id, user, db):
        raise HTTPException(403, "Admin or team lead required")


# --------------------------
# WebSocket Hub (simple)
# --------------------------
class ConnectionHub:
    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, project_id: int, ws: WebSocket):
        await ws.accept()
        if project_id not in self.connections:
            self.connections[project_id] = []
        self.connections[project_id].append(ws)

    def disconnect(self, project_id: int, ws: WebSocket):
        if project_id in self.connections:
            self.connections[project_id].remove(ws)

    async def broadcast(self, project_id: int, message: dict):
        if project_id in self.connections:
            for ws in self.connections[project_id]:
                try:
                    await ws.send_json(message)
                except:
                    pass


hub = ConnectionHub()


# --------------------------
# Startup
# --------------------------
@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --------------------------
# Public / Auth
# --------------------------
@app.get("/")
async def root():
    return {"message": "TrojanTracks online", "docs": "/docs"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/auth/whoami", response_model=UserOut)
async def whoami(user: User = Depends(get_current_user)) -> UserOut:
    return user


@app.post("/auth/register", response_model=UserOut, status_code=201)
async def register(
    payload: UserCreate,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserOut:
    count = await db.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        if not token:
            raise HTTPException(401, "Admin token required")
        try:
            payload_jwt = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            uid = int(payload_jwt.get("sub", 0))
            requester = await db.scalar(select(User).where(User.id == uid))
            if not requester or not requester.is_admin:
                raise HTTPException(403, "Admin only")
        except JWTError:
            raise HTTPException(401, "Invalid token")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        email=payload.email,
        is_admin=(count == 0),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenOut)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)) -> TokenOut:
    who = form.username.strip()
    user = await db.scalar(
        select(User).where(or_(User.username == who, User.email == who.lower()))
    )
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(access_token=token)


@app.post("/auth/change-password")
async def change_password(payload: PasswordChangeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, "Old password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"ok": True}


@app.post("/auth/forgot")
async def forgot_password(payload: ForgotIn, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = _now_utc() + timedelta(minutes=RESET_TOKEN_TTL_MIN)
        await db.commit()
        return {"ok": True, "reset_token": token, "expires_minutes": RESET_TOKEN_TTL_MIN}
    return {"ok": True}


@app.post("/auth/reset")
async def reset_password(payload: ResetIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.reset_token == payload.token))
    if not user or not user.reset_token_expires or user.reset_token_expires < _now_utc():
        if user:
            user.reset_token = None
            user.reset_token_expires = None
            await db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.password_hash = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()
    return {"ok": True, "message": "Password reset successful"}


# --------------------------
# Users / Admin
# --------------------------
@app.get("/users", response_model=List[UserOut])
async def list_users(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> List[UserOut]:
    stmt = select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like)))
    stmt = stmt.order_by(User.id).offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@app.post("/users", response_model=UserOut, status_code=201)
async def admin_create_user(payload: UserCreate, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> UserOut:
    user = User(username=payload.username, password_hash=hash_password(payload.password), email=payload.email)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post("/users/{user_id}/promote", response_model=UserOut)
async def promote_one(user_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(404, "User not found")
    user.is_admin = True
    await db.commit()
    await db.refresh(user)
    return user


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


# --------------------------
# Projects
# --------------------------
@app.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectCreate, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> ProjectOut:
    proj = Project(name=payload.name, key=payload.key)
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj


@app.get("/projects", response_model=List[ProjectOut])
async def list_projects(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> List[ProjectOut]:
    res = await db.execute(select(Project).order_by(Project.id))
    return list(res.scalars().all())


@app.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> ProjectOut:
    proj = await db.scalar(select(Project).where(Project.id == project_id))
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


@app.put("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, payload: ProjectCreate, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> ProjectOut:
    proj = await db.scalar(select(Project).where(Project.id == project_id))
    if not proj:
        raise HTTPException(404, "Project not found")
    proj.name = payload.name
    proj.key = payload.key
    await db.commit()
    await db.refresh(proj)
    return proj


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()


@app.get("/projects/{project_id}/people/bench", response_model=List[UserOut])
async def bench_people(project_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> List[UserOut]:
    in_team_ids = (
        select(TeamMember.user_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.project_id == project_id)
    )
    res = await db.execute(select(User).where(User.id.not_in(in_team_ids)).order_by(User.username))
    return list(res.scalars().all())


# --------------------------
# Teams
# --------------------------
@app.post("/teams", status_code=201)
async def create_team(payload: TeamCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_admin_or_lead_for_project(payload.project_id, user, db)
    team = Team(name=payload.name, project_id=payload.project_id)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return {"id": team.id, "name": team.name, "project_id": team.project_id}


@app.post("/teams/{team_id}/members", status_code=201)
async def add_team_member(team_id: int, payload: TeamMemberAdd, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = await db.scalar(select(Team).where(Team.id == team_id))
    if not team:
        raise HTTPException(404, "Team not found")
    await require_admin_or_lead_for_project(team.project_id, user, db)

    existing = await db.scalar(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id)
    )
    if existing:
        existing.role = payload.role
    else:
        db.add(TeamMember(team_id=team_id, user_id=payload.user_id, role=payload.role))
    await db.commit()
    return {"ok": True}


# --------------------------
# Columns
# --------------------------
@app.post("/columns", response_model=ColumnOut, status_code=201)
async def create_column(payload: ColumnCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> ColumnOut:
    await require_admin_or_lead_for_project(payload.project_id, user, db)
    col = Column(name=payload.name, project_id=payload.project_id, order=payload.order)
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return col


@app.get("/columns", response_model=List[ColumnOut])
async def list_columns(project_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> List[ColumnOut]:
    res = await db.execute(select(Column).where(Column.project_id == project_id).order_by(Column.order))
    return list(res.scalars().all())


@app.put("/columns/{column_id}", response_model=ColumnOut)
async def update_column(column_id: int, payload: ColumnCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> ColumnOut:
    col = await db.scalar(select(Column).where(Column.id == column_id))
    if not col:
        raise HTTPException(404, "Column not found")
    await require_admin_or_lead_for_project(col.project_id, user, db)
    col.name = payload.name
    col.order = payload.order
    await db.commit()
    await db.refresh(col)
    return col


@app.delete("/columns/{column_id}", status_code=204)
async def delete_column(column_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    col = await db.scalar(select(Column).where(Column.id == column_id))
    if not col:
        raise HTTPException(404, "Column not found")
    await require_admin_or_lead_for_project(col.project_id, user, db)
    await db.execute(delete(Column).where(Column.id == column_id))
    await db.commit()


# --------------------------
# Tasks
# --------------------------
def _task_to_out(task: Task) -> TaskOut:
    aouts: List[TaskAssigneeOut] = []
    for ta in task.assignees:
        aouts.append(TaskAssigneeOut(
            user_id=ta.user_id,
            username=ta.user.username if ta.user else f"id:{ta.user_id}",
            is_completed=ta.is_completed,
            completed_at=ta.completed_at,
            completed_summary=ta.completed_summary
        ))
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        project_id=task.project_id,
        column_id=task.column_id,
        is_completed=task.is_completed,
        created_at=task.created_at,
        completed_at=task.completed_at,
        assignees=aouts
    )


async def _refresh_task_completion(task: Task, db: AsyncSession) -> None:
    total = int((await db.scalar(
        select(func.count()).select_from(TaskAssignee).where(TaskAssignee.task_id == task.id)
    )) or 0)
    if total == 0:
        task.is_completed = False
        task.completed_at = None
        return

    done = int((await db.scalar(
        select(func.count()).select_from(TaskAssignee).where(TaskAssignee.task_id == task.id, TaskAssignee.is_completed == True)
    )) or 0)

    if done == total:
        latest = await db.scalar(select(func.max(TaskAssignee.completed_at)).where(TaskAssignee.task_id == task.id))
        task.is_completed = True
        task.completed_at = latest or datetime.utcnow()
    else:
        task.is_completed = False
        task.completed_at = None


@app.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskOut:
    await require_admin_or_lead_for_project(payload.project_id, user, db)

    if payload.column_id:
        found = await db.scalar(
            select(Column).where(Column.id == payload.column_id, Column.project_id == payload.project_id)
        )
        if not found:
            raise HTTPException(404, "Column not found in project")

    task = Task(
        title=payload.title,
        description=payload.description,
        project_id=payload.project_id,
        column_id=payload.column_id
    )
    db.add(task)
    await db.flush()

    if payload.assignee_ids:
        for uid in sorted(set(payload.assignee_ids)):
            u = await db.scalar(select(User).where(User.id == uid))
            if not u:
                raise HTTPException(404, f"Assignee {uid} not found")
            db.add(TaskAssignee(task_id=task.id, user_id=uid))

    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


@app.get("/tasks", response_model=List[TaskOut])
async def list_tasks(
    project_id: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[TaskOut]:
    stmt = select(Task)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if q:
        stmt = stmt.where(Task.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Task.id).offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    tasks = list(res.scalars().unique().all())
    return [_task_to_out(t) for t in tasks]


@app.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskOut:
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    return _task_to_out(task)


@app.put("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, payload: TaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskOut:
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    await require_admin_or_lead_for_project(task.project_id, user, db)
    
    task.title = payload.title
    task.description = payload.description
    task.column_id = payload.column_id
    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    await require_admin_or_lead_for_project(task.project_id, user, db)
    await db.execute(delete(Task).where(Task.id == task_id))
    await db.commit()


@app.post("/tasks/{task_id}/assignees", response_model=TaskOut)
async def change_assignees(task_id: int, payload: TaskAssigneesChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskOut:
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    await require_admin_or_lead_for_project(task.project_id, user, db)

    if payload.add:
        for uid in sorted(set(payload.add)):
            exists = await db.scalar(
                select(TaskAssignee).where(TaskAssignee.task_id == task_id, TaskAssignee.user_id == uid)
            )
            if not exists:
                u = await db.scalar(select(User).where(User.id == uid))
                if not u:
                    raise HTTPException(404, f"User {uid} not found")
                db.add(TaskAssignee(task_id=task_id, user_id=uid))

    if payload.remove:
        await db.execute(
            delete(TaskAssignee).where(TaskAssignee.task_id == task_id, TaskAssignee.user_id.in_(payload.remove))
        )

    await db.flush()
    await _refresh_task_completion(task, db)
    await db.commit()
    await db.refresh(task)

    prog = await compute_progress(task.project_id, db)
    await hub.broadcast(task.project_id, {"type": "progress", **prog.model_dump()})
    return _task_to_out(task)


@app.post("/tasks/{task_id}/complete/me", response_model=TaskOut)
async def complete_task_me(task_id: int, payload: TaskCompleteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskOut:
    task = await db.scalar(select(Task).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")

    ta = await db.scalar(
        select(TaskAssignee).where(TaskAssignee.task_id == task_id, TaskAssignee.user_id == user.id)
    )
    if not ta:
        if not await is_team_admin_or_lead(task.project_id, user, db):
            raise HTTPException(403, "You are not assigned to this task")
        ta = TaskAssignee(task_id=task_id, user_id=user.id)
        db.add(ta)
        await db.flush()

    if not payload.summary or not payload.summary.strip():
        raise HTTPException(400, "Completion summary is required")

    ta.is_completed = True
    ta.completed_at = datetime.utcnow()
    ta.completed_summary = payload.summary.strip()

    await db.flush()
    await _refresh_task_completion(task, db)
    await db.commit()
    await db.refresh(task)

    prog = await compute_progress(task.project_id, db)
    await hub.broadcast(task.project_id, {"type": "progress", **prog.model_dump()})
    return _task_to_out(task)


# --------------------------
# Progress
# --------------------------
async def compute_progress(project_id: int, db: AsyncSession) -> ProgressOut:
    total = int((await db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id))) or 0)
    completed = int((await db.scalar(
        select(func.count()).select_from(Task).where(Task.project_id == project_id, Task.is_completed == True)
    )) or 0)
    percent = float(round((completed / total) * 100, 2)) if total else 0.0
    return ProgressOut(project_id=project_id, total=total, completed=completed, percent=percent)


@app.get("/projects/{project_id}/progress", response_model=ProgressOut)
async def get_progress(project_id: int, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> ProgressOut:
    return await compute_progress(project_id, db)


@app.get("/projects/{project_id}/tasks/status")
async def project_task_status(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
) -> Dict[str, List[TaskOut]]:
    res = await db.execute(select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc()))
    tasks = list(res.scalars().unique().all())
    completed, pending = [], []
    for t in tasks:
        out = _task_to_out(t)
        (completed if t.is_completed else pending).append(out)
    return {"completed": completed, "pending": pending}


# --------------------------
# Messages
# --------------------------
def infer_scope(team_id: Optional[int], recipient_user_id: Optional[int]) -> str:
    if recipient_user_id:
        return "USER"
    if team_id:
        return "TEAM"
    return "GLOBAL"


@app.post("/messages", response_model=MessageOut, status_code=201)
async def post_message(payload: MessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MessageOut:
    scope = infer_scope(payload.team_id, payload.recipient_user_id)

    if scope == "TEAM" and not user.is_admin:
        tm = await db.scalar(select(TeamMember).where(TeamMember.team_id == payload.team_id, TeamMember.user_id == user.id))
        if not tm:
            raise HTTPException(403, "Must be a member of the team to post")
    if payload.recipient_user_id:
        exists = await db.scalar(select(User).where(User.id == payload.recipient_user_id))
        if not exists:
            raise HTTPException(404, "Recipient user not found")

    msg = Message(
        sender_id=user.id,
        scope=scope,
        text=payload.text,
        project_id=payload.project_id,
        team_id=payload.team_id,
        recipient_user_id=payload.recipient_user_id,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


@app.get("/messages/inbox", response_model=List[MessageOut])
async def inbox(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[MessageOut]:
    team_ids = [tid for (tid,) in (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )).all()]
    stmt = select(Message).where(
        (Message.scope == "GLOBAL") |
        ((Message.scope == "TEAM") & (Message.team_id.in_(team_ids) if team_ids else False)) |
        ((Message.scope == "USER") & (Message.recipient_user_id == user.id))
    ).order_by(Message.created_at.desc()).offset((page - 1) * limit).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


# --------------------------
# WebSocket
# --------------------------
@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: int):
    await hub.connect(project_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(project_id, websocket)


# --------------------------
# Run
# --------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)