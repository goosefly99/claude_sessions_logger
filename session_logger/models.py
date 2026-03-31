"""Pydantic models for session log entries."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .sanitize import sanitize_tags, sanitize_text


class TaskStatus(str, Enum):
    """Completion status of a logged task."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


# Tags that indicate trivial changes — excluded from the weekly worklog
MINOR_TAGS = frozenset({
    "typo", "formatting", "whitespace", "lint", "cleanup",
    "trivial", "style", "nit", "cosmetic",
})


class TaskEntry(BaseModel):
    """A single task-completion record written to the daily log."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="ISO-8601 timestamp when the task was logged",
    )
    summary: str = Field(
        ...,
        description="One-line description of the completed task",
        min_length=1,
        max_length=500,
    )
    detail: Optional[str] = Field(
        default=None,
        description="Optional longer description, notes, or context",
        max_length=2000,
    )
    status: TaskStatus = Field(
        default=TaskStatus.COMPLETED,
        description="Completion status: completed | partial | blocked | deferred",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional category tags (e.g. 'bugfix', 'refactor', 'docs')",
        max_length=10,
    )
    project: Optional[str] = Field(
        default=None,
        description="Optional project or repo name for grouping",
        max_length=200,
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Estimated minutes spent on the task",
        ge=0,
        le=1440,
    )

    # ── Sanitization validators ──────────────────────────────────────────

    @field_validator("summary", mode="before")
    @classmethod
    def sanitize_summary(cls, v: str) -> str:
        result = sanitize_text(v)
        if not result:
            raise ValueError("Summary cannot be empty after sanitization")
        return result

    @field_validator("detail", mode="before")
    @classmethod
    def sanitize_detail(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_text(v)

    @field_validator("project", mode="before")
    @classmethod
    def sanitize_project(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_text(v)

    @field_validator("tags", mode="before")
    @classmethod
    def sanitize_tag_list(cls, v: list[str]) -> list[str]:
        return sanitize_tags(v)

    # ── Worklog classification ───────────────────────────────────────────

    def is_substantial(self) -> bool:
        """Determine if this entry is substantial enough for the weekly worklog.

        Substantial means: has detail text, took 15+ minutes, or carries
        tags beyond trivial cosmetic fixes.
        """
        if self.detail:
            return True
        if self.duration_minutes is not None and self.duration_minutes >= 15:
            return True
        if self.tags and not set(self.tags).issubset(MINOR_TAGS):
            return True
        return False


class DailySummary(BaseModel):
    """Aggregated view of a single day's log."""

    date: str = Field(..., description="Date string YYYY-MM-DD")
    task_count: int = Field(..., description="Total tasks logged")
    completed: int = Field(default=0)
    partial: int = Field(default=0)
    blocked: int = Field(default=0)
    deferred: int = Field(default=0)
    total_duration_minutes: Optional[int] = Field(default=None)
    tags: list[str] = Field(default_factory=list, description="Unique tags seen")
    projects: list[str] = Field(default_factory=list, description="Unique projects seen")


class WeeklyWorklogEntry(BaseModel):
    """A single entry in the weekly worklog — derived from a substantial TaskEntry."""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(..., description="Date YYYY-MM-DD when the task was logged")
    time: str = Field(..., description="Time HH:MM when the task was logged")
    summary: str = Field(..., description="Task summary")
    detail: Optional[str] = Field(default=None, description="Extended notes")
    project: Optional[str] = Field(default=None, description="Project name")
    tags: list[str] = Field(default_factory=list)
    duration_minutes: Optional[int] = Field(default=None)

    @classmethod
    def from_task(cls, task: TaskEntry) -> WeeklyWorklogEntry:
        """Create a worklog entry from a substantial TaskEntry."""
        return cls(
            date=task.timestamp.strftime("%Y-%m-%d"),
            time=task.timestamp.strftime("%H:%M"),
            summary=task.summary,
            detail=task.detail,
            project=task.project,
            tags=task.tags,
            duration_minutes=task.duration_minutes,
        )
