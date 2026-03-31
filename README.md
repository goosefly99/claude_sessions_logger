# Claude Session Logger

A local MCP server that keeps a running log of what you accomplish across Claude sessions. Each task you complete gets recorded to a daily JSONL file, and substantial work is automatically promoted to a cumulative weekly worklog — giving you a persistent, searchable record of your AI-assisted productivity.

## Why

Claude conversations are ephemeral. You finish a session, close the window, and the work you did fades into chat history. This server solves that by giving Claude a set of tools to log tasks as they happen. At the end of a week you have a clean Markdown summary of the important things you shipped, without the noise of minor fixes and formatting tweaks.

## Features

- **Daily task logs** — JSONL files with one entry per completed task, including summary, detail notes, tags, project name, status, and estimated duration.
- **Weekly worklog** — A cumulative Markdown file (Monday–Sunday) that automatically captures substantial work. Tasks with detail notes, 15+ minute duration, or meaningful tags are included; trivial changes like typos and lint fixes are filtered out.
- **UTF-8 text sanitization** — All text fields are cleaned on input: NFKC Unicode normalization, control character removal, surrogate stripping, and whitespace collapsing. No broken characters in your logs.
- **Rebuild from source** — Weekly worklogs can be regenerated from raw daily data at any time, so edits to daily logs are always reflected.

## Requirements

- Python 3.11+
- Claude Desktop or Claude Code

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/claude-session-logger.git
cd claude-session-logger
pip install -e .
```

Verify:

```bash
python -c "from session_logger.server import mcp; print('OK')"
```

## Setup

### Claude Desktop (Windows/macOS)

Open the config file:

```
# Windows
notepad %APPDATA%\Claude\claude_desktop_config.json

# macOS
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Add the server to the `mcpServers` section:

```json
{
  "mcpServers": {
    "session-logger": {
      "command": "python",
      "args": ["-m", "session_logger.server"],
      "cwd": "C:\\path\\to\\claude-session-logger"
    }
  }
}
```

Restart Claude Desktop after saving.

### Claude Code (CLI)

```bash
claude mcp add session-logger --scope user -- python -m session_logger.server
```

To enable automatic logging, add this to your `CLAUDE.md` or project custom instructions:

> After completing each distinct task, call `session_log_task` with a one-line summary, relevant tags, and status. Log automatically whenever you commit changes with Git.

## Tools

| Tool | Description |
| --- | --- |
| `session_log_task` | Record a task to today's daily log. Substantial entries are auto-appended to the weekly worklog. |
| `session_view_log` | View a day's entries in Markdown or JSON format. Defaults to today. |
| `session_list_days` | List all dates with log entries, reverse chronological. |
| `session_daily_summary` | Aggregate stats for a day: task counts by status, total duration, tags, projects. |
| `session_weekly_worklog` | View the cumulative Mon–Sun worklog. Use `rebuild=true` to regenerate from raw daily data. |

## Task fields

| Field | Required | Description |
| --- | --- | --- |
| `summary` | Yes | One-line description of the completed work |
| `detail` | No | Longer notes, context, or follow-up items |
| `status` | No | `completed` (default), `partial`, `blocked`, or `deferred` |
| `tags` | No | Category labels like `bugfix`, `refactor`, `docs` |
| `project` | No | Project or repo name for grouping |
| `duration_minutes` | No | Estimated time spent (0–1440) |

## How the weekly worklog works

When a task is logged, the server classifies it as **substantial** or **minor**:

**Substantial** (included in the weekly worklog):
- Has detail text
- Duration of 15 minutes or more
- Carries tags beyond trivial categories

**Minor** (daily log only):
- Tagged only with `typo`, `formatting`, `whitespace`, `lint`, `cleanup`, `trivial`, `style`, `nit`, or `cosmetic`
- No detail text and under 15 minutes

Substantial tasks are appended to `worklog-YYYY-WNN.md` as they're logged. Each ISO week (Monday–Sunday) gets its own file. The `session_weekly_worklog` tool can also rebuild the worklog from raw daily JSONL data if entries are edited or deleted after the fact.

## File structure

```
~/.claude-session-logs/
├── 2026-03-31.jsonl            # Daily task log (one JSON object per line)
├── 2026-04-01.jsonl
├── worklog-2026-W14.md         # Weekly worklog (Mon Mar 30 – Sun Apr 5)
└── ...
```

## Configuration

Set `SESSION_LOG_DIR` to change the log directory:

```bash
# Linux/macOS
export SESSION_LOG_DIR=~/Documents/claude-logs

# Windows (persistent)
setx SESSION_LOG_DIR "C:\Users\you\Documents\claude-logs"
```

Default: `~/.claude-session-logs/`

## Reading logs outside Claude

```bash
# View today's raw entries
cat ~/.claude-session-logs/2026-03-31.jsonl | python -m json.tool --json-lines

# View this week's worklog
cat ~/.claude-session-logs/worklog-2026-W14.md

# Count tasks by project across all logs
cat ~/.claude-session-logs/*.jsonl | python -c "
import sys, json
from collections import Counter
c = Counter(json.loads(l).get('project','(none)') for l in sys.stdin)
for proj, n in c.most_common(): print(f'{n:4d}  {proj}')
"
```

## Project layout

```
claude-session-logger/
├── pyproject.toml
├── README.md
└── session_logger/
    ├── __init__.py
    ├── sanitize.py     # UTF-8 text cleaning and tag normalization
    ├── models.py       # Pydantic schemas: TaskEntry, DailySummary, WeeklyWorklogEntry
    ├── store.py        # File I/O: daily JSONL, weekly Markdown, summaries
    └── server.py       # FastMCP server and tool definitions
```

## License

MIT
