"""Daily log file storage and weekly worklog — JSONL files per day, Markdown per week."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import DailySummary, TaskEntry, TaskStatus, WeeklyWorklogEntry

# ── Defaults ────────────────────────────────────────────────────────────
DEFAULT_LOG_DIR = os.path.expanduser("~/.claude-session-logs")

STATUS_EMOJI = {
    TaskStatus.COMPLETED: "\u2705",
    TaskStatus.PARTIAL: "\U0001f536",
    TaskStatus.BLOCKED: "\U0001f6ab",
    TaskStatus.DEFERRED: "\u23f3",
}


def _log_dir() -> Path:
    """Resolve and ensure the log directory exists."""
    directory = Path(os.environ.get("SESSION_LOG_DIR", DEFAULT_LOG_DIR))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _log_path(target_date: date) -> Path:
    """Return the JSONL path for a given date."""
    return _log_dir() / f"{target_date.isoformat()}.jsonl"


def _worklog_path(iso_year: int, iso_week: int) -> Path:
    """Return the weekly worklog Markdown path for a given ISO week."""
    return _log_dir() / f"worklog-{iso_year}-W{iso_week:02d}.md"


def _week_boundaries(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (monday, sunday) for a given ISO week."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ── Write ────────────────────────────────────────────────────────────────

def append_entry(entry: TaskEntry) -> Path:
    """Append a single TaskEntry to the day's JSONL file.

    If the entry is substantial, also appends to the weekly worklog.
    """
    target_date = entry.timestamp.date()
    path = _log_path(target_date)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")

    # Auto-append substantial entries to the weekly worklog
    if entry.is_substantial():
        worklog_entry = WeeklyWorklogEntry.from_task(entry)
        _append_worklog_entry(worklog_entry, target_date)

    return path


def _append_worklog_entry(entry: WeeklyWorklogEntry, target_date: date) -> Path:
    """Append a worklog entry to the current week's Markdown file."""
    iso_year, iso_week, _ = target_date.isocalendar()
    path = _worklog_path(iso_year, iso_week)

    # Create file with header if it doesn't exist
    if not path.exists():
        monday, sunday = _week_boundaries(iso_year, iso_week)
        header = (
            f"# Weekly Worklog — {iso_year}-W{iso_week:02d}\n\n"
            f"**{monday.isoformat()}** to **{sunday.isoformat()}**\n\n"
            f"---\n\n"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header)

    # Format and append the entry
    proj_str = f" [{entry.project}]" if entry.project else ""
    dur_str = f" ({entry.duration_minutes}m)" if entry.duration_minutes else ""
    tag_str = f"  `{'` `'.join(entry.tags)}`" if entry.tags else ""

    block = f"### {entry.date} {entry.time}{proj_str}{dur_str}\n\n"
    block += f"**{entry.summary}**{tag_str}\n\n"

    if entry.detail:
        block += f"{entry.detail}\n\n"

    block += "---\n\n"

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(block)

    return path


# ── Read ─────────────────────────────────────────────────────────────────

def read_entries(target_date: date) -> list[TaskEntry]:
    """Read all entries for a given date. Returns empty list if no log exists."""
    path = _log_path(target_date)
    if not path.exists():
        return []
    entries: list[TaskEntry] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(TaskEntry.model_validate_json(line))
    return entries


def list_dates() -> list[date]:
    """Return sorted list of all dates that have log files."""
    log_dir = _log_dir()
    dates: list[date] = []
    for child in log_dir.iterdir():
        if child.suffix == ".jsonl":
            try:
                dates.append(date.fromisoformat(child.stem))
            except ValueError:
                continue
    dates.sort()
    return dates


def read_weekly_worklog(iso_year: int, iso_week: int) -> Optional[str]:
    """Read the weekly worklog Markdown for a given ISO week.

    Returns None if no worklog exists for that week.
    """
    path = _worklog_path(iso_year, iso_week)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def list_worklogs() -> list[tuple[int, int]]:
    """Return sorted list of (iso_year, iso_week) tuples for available worklogs."""
    log_dir = _log_dir()
    weeks: list[tuple[int, int]] = []
    for child in log_dir.iterdir():
        if child.name.startswith("worklog-") and child.suffix == ".md":
            # Parse "worklog-2026-W13.md"
            try:
                parts = child.stem.replace("worklog-", "").split("-W")
                year = int(parts[0])
                week = int(parts[1])
                weeks.append((year, week))
            except (ValueError, IndexError):
                continue
    weeks.sort()
    return weeks


# ── Summarise ────────────────────────────────────────────────────────────

def build_summary(target_date: date) -> Optional[DailySummary]:
    """Build an aggregate summary for a single day."""
    entries = read_entries(target_date)
    if not entries:
        return None

    status_counts = Counter(e.status for e in entries)
    all_tags: set[str] = set()
    all_projects: set[str] = set()
    total_mins = 0
    has_duration = False

    for entry in entries:
        all_tags.update(entry.tags)
        if entry.project:
            all_projects.add(entry.project)
        if entry.duration_minutes is not None:
            total_mins += entry.duration_minutes
            has_duration = True

    return DailySummary(
        date=target_date.isoformat(),
        task_count=len(entries),
        completed=status_counts.get(TaskStatus.COMPLETED, 0),
        partial=status_counts.get(TaskStatus.PARTIAL, 0),
        blocked=status_counts.get(TaskStatus.BLOCKED, 0),
        deferred=status_counts.get(TaskStatus.DEFERRED, 0),
        total_duration_minutes=total_mins if has_duration else None,
        tags=sorted(all_tags),
        projects=sorted(all_projects),
    )


def build_weekly_summary(iso_year: int, iso_week: int) -> str:
    """Build a weekly summary from daily session logs for the given ISO week.

    This reconstructs the summary from raw JSONL data (not the worklog file),
    so it always reflects the current state of the daily logs.
    """
    monday, sunday = _week_boundaries(iso_year, iso_week)

    all_entries: list[TaskEntry] = []
    current = monday
    while current <= sunday:
        all_entries.extend(read_entries(current))
        current += timedelta(days=1)

    if not all_entries:
        return (
            f"# Weekly Summary — {iso_year}-W{iso_week:02d}\n\n"
            f"**{monday.isoformat()}** to **{sunday.isoformat()}**\n\n"
            f"_No tasks logged this week._\n"
        )

    substantial = [e for e in all_entries if e.is_substantial()]
    minor = [e for e in all_entries if not e.is_substantial()]

    all_tags: set[str] = set()
    all_projects: set[str] = set()
    total_mins = 0
    has_duration = False

    for e in all_entries:
        all_tags.update(e.tags)
        if e.project:
            all_projects.add(e.project)
        if e.duration_minutes is not None:
            total_mins += e.duration_minutes
            has_duration = True

    lines: list[str] = [
        f"# Weekly Summary — {iso_year}-W{iso_week:02d}\n",
        f"**{monday.isoformat()}** to **{sunday.isoformat()}**\n",
    ]

    # Stats
    parts = [f"**{len(all_entries)}** total tasks ({len(substantial)} substantial)"]
    if has_duration:
        hours, mins = divmod(total_mins, 60)
        dur = f"{hours}h {mins}m" if hours else f"{mins}m"
        parts.append(f"~{dur} logged")
    if all_projects:
        parts.append(f"projects: {', '.join(sorted(all_projects))}")
    lines.append(" · ".join(parts) + "\n")

    # Substantial entries — grouped by date
    if substantial:
        lines.append("## Key Work\n")
        by_date: dict[str, list[TaskEntry]] = {}
        for e in substantial:
            d = e.timestamp.strftime("%Y-%m-%d")
            by_date.setdefault(d, []).append(e)

        for d in sorted(by_date):
            lines.append(f"### {d}\n")
            for e in by_date[d]:
                proj_str = f" [{e.project}]" if e.project else ""
                dur_str = f" ({e.duration_minutes}m)" if e.duration_minutes else ""
                tag_str = f"  `{'` `'.join(e.tags)}`" if e.tags else ""
                lines.append(f"- **{e.summary}**{proj_str}{dur_str}{tag_str}")
                if e.detail:
                    for detail_line in e.detail.splitlines():
                        lines.append(f"  {detail_line}")
            lines.append("")

    # Minor entries — collapsed
    if minor:
        lines.append(f"## Minor Changes ({len(minor)})\n")
        for e in minor:
            lines.append(f"- {e.summary}")
        lines.append("")

    return "\n".join(lines)


# ── Markdown rendering ──────────────────────────────────────────────────

def render_daily_markdown(target_date: date) -> str:
    """Render the full daily log as a Markdown document."""
    entries = read_entries(target_date)
    if not entries:
        return f"# Session Log — {target_date.isoformat()}\n\n_No tasks logged._\n"

    summary = build_summary(target_date)
    lines: list[str] = [f"# Session Log — {target_date.isoformat()}\n"]

    # Stats header
    if summary:
        parts = [f"**{summary.task_count}** tasks"]
        if summary.total_duration_minutes is not None:
            hours, mins = divmod(summary.total_duration_minutes, 60)
            dur = f"{hours}h {mins}m" if hours else f"{mins}m"
            parts.append(f"~{dur} logged")
        if summary.tags:
            parts.append(f"tags: {', '.join(summary.tags)}")
        lines.append(" · ".join(parts) + "\n")

    # Entries
    for entry in entries:
        emoji = STATUS_EMOJI.get(entry.status, "")
        ts = entry.timestamp.strftime("%H:%M")
        tag_str = f"  `{'` `'.join(entry.tags)}`" if entry.tags else ""
        proj_str = f" [{entry.project}]" if entry.project else ""
        dur_str = f" ({entry.duration_minutes}m)" if entry.duration_minutes else ""

        lines.append(f"- {emoji} **{ts}**{proj_str} {entry.summary}{dur_str}{tag_str}")

        if entry.detail:
            for detail_line in entry.detail.splitlines():
                lines.append(f"  {detail_line}")

    lines.append("")  # trailing newline
    return "\n".join(lines)
