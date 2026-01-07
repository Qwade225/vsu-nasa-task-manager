# TrojanTracks/api/schemas.py

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, EmailStr


# =============================================================================
# AUTHENTICATION SCHEMAS
# =============================================================================

class TokenOut(BaseModel):
    """Response schema for login endpoint"""
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    """Schema for creating a new user"""
    username: str = Field(min_length=3, max_length=64, description="Unique username")
    password: str = Field(min_length=6, max_length=128, description="User password")
    email: Optional[EmailStr] = Field(None, description="Optional email address")


class UserOut(BaseModel):
    """Response schema for user data"""
    id: int
    username: str
    email: Optional[EmailStr] = None
    is_admin: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PasswordChangeIn(BaseModel):
    """Schema for changing password"""
    old_password: str = Field(description="Current password")
    new_password: str = Field(min_length=6, max_length=128, description="New password")


class ForgotIn(BaseModel):
    """Schema for forgot password request"""
    email: EmailStr = Field(description="Email address for password reset")


class ResetIn(BaseModel):
    """Schema for password reset with token"""
    token: str = Field(min_length=8, max_length=256, description="Reset token from email")
    new_password: str = Field(min_length=6, max_length=128, description="New password")


class PromoteBulkIn(BaseModel):
    """Schema for bulk promoting users to admin"""
    user_ids: Optional[List[int]] = Field(None, description="List of user IDs to promote")
    emails: Optional[List[EmailStr]] = Field(None, description="List of emails to promote")
    usernames: Optional[List[str]] = Field(None, description="List of usernames to promote")


# =============================================================================
# PROJECT SCHEMAS
# =============================================================================

class ProjectCreate(BaseModel):
    """Schema for creating a new project"""
    name: str = Field(min_length=1, max_length=120, description="Project name")
    key: str = Field(min_length=2, max_length=10, description="Project key (e.g., ROBOT)")


class ProjectOut(BaseModel):
    """Response schema for project data"""
    id: int
    name: str
    key: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# TEAM SCHEMAS
# =============================================================================

class TeamCreate(BaseModel):
    """Schema for creating a new team"""
    name: str = Field(min_length=1, max_length=120, description="Team name")
    project_id: int = Field(description="Project ID this team belongs to")


class TeamOut(BaseModel):
    """Response schema for team data"""
    id: int
    name: str
    project_id: int
    
    model_config = ConfigDict(from_attributes=True)


class TeamMemberAdd(BaseModel):
    """Schema for adding a user to a team"""
    user_id: int = Field(description="User ID to add to team")
    role: str = Field(default="member", description="Role: 'member' or 'lead'")


class TeamMemberOut(BaseModel):
    """Response schema for team member data"""
    id: int
    team_id: int
    user_id: int
    role: str
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# COLUMN SCHEMAS
# =============================================================================

class ColumnCreate(BaseModel):
    """Schema for creating a new column"""
    name: str = Field(min_length=1, max_length=50, description="Column name (e.g., 'To Do')")
    project_id: int = Field(description="Project ID this column belongs to")
    order: int = Field(default=0, description="Display order (lower = left)")


class ColumnOut(BaseModel):
    """Response schema for column data"""
    id: int
    name: str
    project_id: int
    order: int
    
    model_config = ConfigDict(from_attributes=True)


class ColumnWithTasksOut(BaseModel):
    """Response schema for column with its tasks"""
    id: int
    name: str
    order: int
    tasks: List["TaskOut"] = []
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# TASK SCHEMAS
# =============================================================================

class TaskCreate(BaseModel):
    """Schema for creating a new task"""
    title: str = Field(min_length=1, max_length=200, description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    project_id: int = Field(description="Project ID this task belongs to")
    column_id: Optional[int] = Field(None, description="Column ID (optional)")
    assignee_ids: Optional[List[int]] = Field(None, description="List of user IDs to assign")


class TaskAssigneeOut(BaseModel):
    """Response schema for task assignee data"""
    user_id: int
    username: str
    is_completed: bool
    completed_at: Optional[datetime] = None
    completed_summary: Optional[str] = None


class TaskOut(BaseModel):
    """Response schema for task data"""
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
    """Schema for marking a task complete"""
    summary: str = Field(min_length=1, description="Summary of work completed")


class TaskAssigneesChange(BaseModel):
    """Schema for adding/removing task assignees"""
    add: Optional[List[int]] = Field(None, description="User IDs to add as assignees")
    remove: Optional[List[int]] = Field(None, description="User IDs to remove as assignees")


class TaskUpdate(BaseModel):
    """Schema for updating task details"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    column_id: Optional[int] = None
    rank: Optional[float] = None


# =============================================================================
# BOARD SCHEMAS
# =============================================================================

class BoardOut(BaseModel):
    """Response schema for full board view (project with columns and tasks)"""
    project_id: int
    project_key: str
    project_name: str
    columns: List[ColumnWithTasksOut] = []
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PROGRESS SCHEMAS
# =============================================================================

class ProgressOut(BaseModel):
    """Response schema for project progress statistics"""
    project_id: int
    total: int = Field(description="Total number of tasks")
    completed: int = Field(description="Number of completed tasks")
    percent: float = Field(description="Completion percentage")


# =============================================================================
# MESSAGE SCHEMAS
# =============================================================================

class MessageCreate(BaseModel):
    """Schema for creating a new message"""
    text: str = Field(min_length=1, description="Message text")
    project_id: Optional[int] = Field(None, description="Project context (optional)")
    team_id: Optional[int] = Field(None, description="Team ID for team messages")
    recipient_user_id: Optional[int] = Field(None, description="User ID for direct messages")


class MessageOut(BaseModel):
    """Response schema for message data"""
    id: int
    sender_id: int
    scope: str  # GLOBAL, TEAM, or USER
    text: str
    project_id: Optional[int] = None
    team_id: Optional[int] = None
    recipient_user_id: Optional[int] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# DEPRECATED / LEGACY SCHEMAS (for backwards compatibility)
# =============================================================================

# Old naming convention - kept for backwards compatibility
IssueCreate = TaskCreate
IssueOut = TaskOut

# Note: Consider removing these in future versions after updating frontend