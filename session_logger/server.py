"""FastMCP server exposing task-logging tools for Claude Desktop sessions."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .models import TaskEntry, TaskStatus
from .store import (
    append_entry,
    build_summary,
    build_weekly_summary,
    list_dates,
    list_worklogs,
    read_entries,
    read_weekly_worklog,
    render_daily_markdown,
)

mcp = FastMCP("session_logger_mcp")

# ── Input models ─────────────────────────────────────────────────────────


class LogTaskInput(BaseModel):
    """Input for logging a completed task."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    summary: str = Field(
        ...,
        description="One-line description of the completed task",
        min_length=1,
        max_length=500,
    )
    detail: Optional[str] = Field(
        default=None,
        description="Optional longer notes, context, or follow-ups",
        max_length=2000,
    )
    status: str = Field(
        default="completed",
        description="Task status: completed | partial | blocked | deferred",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Category tags (e.g. 'bugfix', 'refactor', 'docs')",
    )
    project: Optional[str] = Field(
        default=None,
        description="Project or repo name for grouping",
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Estimated minutes spent on the task",
        ge=0,
        le=1440,
    )


class ViewLogInput(BaseModel):
    """Input for viewing a daily log."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    date: Optional[str] = Field(
        default=None,
        description="Date to view in YYYY-MM-DD format. Defaults to today.",
    )
    format: str = Field(
        default="markdown",
        description="Output format: 'markdown' for readable text, 'json' for structured data",
    )


class ListDaysInput(BaseModel):
    """Input for listing available log dates."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    last_n: Optional[int] = Field(
        default=None,
        description="Return only the N most recent days. Omit for all.",
        ge=1,
        le=365,
    )


class SummaryInput(BaseModel):
    """Input for getting a daily summary."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    date: Optional[str] = Field(
        default=None,
        description="Date in YYYY-MM-DD format. Defaults to today.",
    )


class WeeklyWorklogInput(BaseModel):
    """Input for viewing or rebuilding the weekly worklog."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    year: Optional[int] = Field(
        default=None,
        description="ISO year (e.g. 2026). Defaults to current week.",
        ge=2020,
        le=2100,
    )
    week: Optional[int] = Field(
        default=None,
        description="ISO week number (1-53). Defaults to current week.",
        ge=1,
        le=53,
    )
    rebuild: bool = Field(
        default=False,
        description="If true, regenerate the summary from raw daily logs "
        "instead of reading the running worklog file.",
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _resolve_date(date_str: Optional[str]) -> date:
    """Parse a date string or return today."""
    if date_str is None:
        return date.today()
    return date.fromisoformat(date_str)


def _resolve_week(
    year: Optional[int], week: Optional[int]
) -> tuple[int, int]:
    """Resolve ISO year/week, defaulting to the current week."""
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return (year or iso_year, week or iso_week)


def _validate_status(raw: str) -> TaskStatus:
    """Convert a raw status string into the enum, with a helpful error."""
    try:
        return TaskStatus(raw.lower())
    except ValueError:
        valid = ", ".join(s.value for s in TaskStatus)
        raise ValueError(
            f"Invalid status '{raw}'. Valid options: {valid}"
        )


# ── Tools ────────────────────────────────────────────────────────────────


@mcp.tool(
    name="session_log_task",
    annotations={
        "title": "Log a completed task",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def session_log_task(params: LogTaskInput) -> str:
    """Record a completed (or in-progress) task to today's session log.

    Call this after finishing a task, fixing a bug, completing a refactor,
    or any other discrete unit of work. Substantial entries (those with
    detail text, 15+ min duration, or meaningful tags) are automatically
    added to the weekly worklog.

    All text fields are sanitized to remove non-UTF-8 characters.

    Args:
        params: Task details including summary, optional tags, status, etc.

    Returns:
        str: Confirmation message with the logged entry timestamp.
    """
    status = _validate_status(params.status)

    entry = TaskEntry(
        summary=params.summary,
        detail=params.detail,
        status=status,
        tags=params.tags,
        project=params.project,
        duration_minutes=params.duration_minutes,
    )

    path = append_entry(entry)

    ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    worklog_note = " (added to weekly worklog)" if entry.is_substantial() else ""
    return (
        f"Logged to {path.name} at {ts}{worklog_note}\n"
        f"  Summary: {entry.summary}\n"
        f"  Status:  {entry.status.value}\n"
        f"  Tags:    {', '.join(entry.tags) if entry.tags else '---'}"
    )


@mcp.tool(
    name="session_view_log",
    annotations={
        "title": "View a daily session log",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def session_view_log(params: ViewLogInput) -> str:
    """View all tasks logged for a given day (defaults to today).

    Supports both Markdown (human-readable) and JSON (structured) output.

    Args:
        params: Date and format options.

    Returns:
        str: The daily log in the requested format.
    """
    target = _resolve_date(params.date)

    if params.format == "json":
        entries = read_entries(target)
        data = [json.loads(e.model_dump_json()) for e in entries]
        return json.dumps({"date": target.isoformat(), "entries": data}, indent=2)

    return render_daily_markdown(target)


@mcp.tool(
    name="session_list_days",
    annotations={
        "title": "List days with session logs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def session_list_days(params: ListDaysInput) -> str:
    """List all dates that have session log entries.

    Returns dates in reverse chronological order. Use last_n to limit results.

    Args:
        params: Optional count limiter.

    Returns:
        str: Markdown list of dates with task counts.
    """
    all_dates = list_dates()
    if not all_dates:
        return "No session logs found yet."

    # Reverse chronological
    all_dates = list(reversed(all_dates))
    if params.last_n is not None:
        all_dates = all_dates[: params.last_n]

    lines = [f"## Session Logs ({len(all_dates)} day{'s' if len(all_dates) != 1 else ''})\n"]
    for d in all_dates:
        summary = build_summary(d)
        count = summary.task_count if summary else 0
        lines.append(f"- **{d.isoformat()}** --- {count} task{'s' if count != 1 else ''}")

    return "\n".join(lines)


@mcp.tool(
    name="session_daily_summary",
    annotations={
        "title": "Get a daily session summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def session_daily_summary(params: SummaryInput) -> str:
    """Generate an aggregate summary for a given day's session log.

    Includes task counts by status, total duration, unique tags, and projects.

    Args:
        params: Date to summarise (defaults to today).

    Returns:
        str: JSON summary object.
    """
    target = _resolve_date(params.date)
    summary = build_summary(target)

    if summary is None:
        return json.dumps({"date": target.isoformat(), "message": "No tasks logged."})

    return summary.model_dump_json(indent=2)


@mcp.tool(
    name="session_weekly_worklog",
    annotations={
        "title": "View the weekly worklog",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def session_weekly_worklog(params: WeeklyWorklogInput) -> str:
    """View the cumulative weekly worklog for a given ISO week.

    The weekly worklog is a running Markdown summary that captures only
    substantial work — tasks with detail notes, significant duration (15+
    minutes), or meaningful tags. Minor changes like typos, formatting,
    and lint fixes are excluded.

    By default reads the running worklog file that is updated incrementally
    as tasks are logged. Use rebuild=true to regenerate the summary from
    raw daily log data (useful if entries were modified or deleted).

    Args:
        params: ISO year/week and optional rebuild flag.

    Returns:
        str: The weekly worklog as Markdown.
    """
    iso_year, iso_week = _resolve_week(params.year, params.week)

    if params.rebuild:
        return build_weekly_summary(iso_year, iso_week)

    content = read_weekly_worklog(iso_year, iso_week)
    if content is None:
        # Fall back to building from daily logs
        return build_weekly_summary(iso_year, iso_week)

    return content


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
