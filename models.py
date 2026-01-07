# TrojanTracks/api/models.py

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# =============================================================================
# USER MODEL
# =============================================================================

class User(Base):
    """
    User model for authentication and team membership.
    First user created is automatically admin.
    """
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Authentication fields
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    
    # Authorization
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Password reset tokens
    reset_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    
    # Relationships
    memberships: Mapped[List["TeamMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    messages_sent: Mapped[List["Message"]] = relationship(
        back_populates="sender",
        foreign_keys="Message.sender_id",
        cascade="all, delete-orphan"
    )
    task_assignments: Mapped[List["TaskAssignee"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )


# =============================================================================
# PROJECT MODEL
# =============================================================================

class Project(Base):
    """
    Project model - top-level organization unit.
    Contains teams, columns, and tasks.
    """
    __tablename__ = "projects"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Project details
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    
    # Relationships
    columns: Mapped[List["Column"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )
    teams: Mapped[List["Team"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )
    messages: Mapped[List["Message"]] = relationship(
        foreign_keys="Message.project_id",
        cascade="all, delete-orphan"
    )


# =============================================================================
# TEAM MODELS
# =============================================================================

class Team(Base):
    """
    Team model - groups users within a project.
    Each team has members with different roles (member, lead).
    """
    __tablename__ = "teams"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Team details
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Relationships
    project: Mapped["Project"] = relationship(back_populates="teams")
    members: Mapped[List["TeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan"
    )
    messages: Mapped[List["Message"]] = relationship(
        foreign_keys="Message.team_id",
        cascade="all, delete-orphan"
    )


class TeamMember(Base):
    """
    TeamMember model - join table between teams and users.
    Tracks role (member or lead) for each user in a team.
    """
    __tablename__ = "team_members"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Foreign keys
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Role: "member" or "lead"
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    
    # Relationships
    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )


# =============================================================================
# COLUMN MODEL
# =============================================================================

class Column(Base):
    """
    Column model - kanban board columns (e.g., To Do, In Progress, Done).
    Each project can have multiple columns.
    """
    __tablename__ = "columns"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Column details
    name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    project: Mapped["Project"] = relationship(back_populates="columns")
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="column",
        cascade="all, delete-orphan"
    )


# =============================================================================
# TASK MODELS
# =============================================================================

class Task(Base):
    """
    Task model - work items that can be assigned to multiple users.
    Tasks belong to a project and optionally to a column.
    Task completion is tracked per assignee.
    """
    __tablename__ = "tasks"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Task details
    title: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Foreign keys
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    column_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("columns.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Ordering (for drag-and-drop)
    rank: Mapped[Optional[float]] = mapped_column(Float, default=1000.0, nullable=True)
    
    # Relationships
    project: Mapped["Project"] = relationship(back_populates="tasks")
    column: Mapped[Optional["Column"]] = relationship(back_populates="tasks")
    assignees: Mapped[List["TaskAssignee"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan"
    )


class TaskAssignee(Base):
    """
    TaskAssignee model - join table between tasks and users.
    Tracks individual completion status and summary for each assignee.
    """
    __tablename__ = "task_assignees"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Foreign keys
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Completion tracking (per assignee)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    task: Mapped["Task"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship(back_populates="task_assignments")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_user"),
    )


# =============================================================================
# MESSAGE MODEL
# =============================================================================

class Message(Base):
    """
    Message model - chat/messaging system.
    Supports three scopes:
    - GLOBAL: visible to all users
    - TEAM: visible to team members
    - USER: direct message to specific user
    """
    __tablename__ = "messages"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    
    # Message details
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    scope: Mapped[str] = mapped_column(String(20), default="GLOBAL", nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Optional context (depends on scope)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    recipient_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    
    # Relationships
    sender: Mapped["User"] = relationship(
        foreign_keys=[sender_id],
        back_populates="messages_sent"
    )