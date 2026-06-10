# TickTick MCP Server for Hermes Agent

MCP (Model Context Protocol) server that gives Hermes Agent access to your
TickTick tasks, projects, and Kanban board columns. Uses the official
TickTick Open API with OAuth2 authentication and automatic token refresh.

## Features

- List projects, tasks (flat or grouped by Kanban column), and filter by status
- Create, update, complete, and delete tasks
- Full task detail view including checklists, tags, priorities, and due dates
- Due date, tag, and priority emoji display in all task views
- OAuth2 with automatic token refresh when TickTick issues a refresh token
- Task ID truncation in list views for privacy-safe screenshots

## Prerequisites

- Python 3.9 or later
- A TickTick account
- A TickTick developer app with OAuth2 credentials from
  [developer.ticktick.com](https://developer.ticktick.com)
- Hermes Agent (any recent version with MCP support)

## Installation

```bash
git clone https://github.com/walice/ticktick-mcp-hermes.git
cd ticktick-mcp-hermes
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Set your TickTick OAuth2 credentials. Choose one method:

**Option A: Environment variables**

```bash
export TICKTICK_CLIENT_ID="your_client_id"
export TICKTICK_CLIENT_SECRET="your_client_secret"
export TICKTICK_REDIRECT_URI="http://localhost:3333/callback"  # default
```

**Option B: Credentials file**

Create `~/.ticktick-mcp/credentials.json`:

```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "redirect_uri": "http://localhost:3333/callback"
}
```

You can override the default paths with these environment variables:

| Variable | Default |
|----------|---------|
| `TICKTICK_CREDENTIALS_PATH` | `~/.ticktick-mcp/credentials.json` |
| `TICKTICK_TOKENS_PATH` | `~/.ticktick-mcp/tokens.json` |

## OAuth Setup

Run the OAuth flow once to obtain your initial tokens:

```bash
python ticktick_mcp.py --oauth
```

This will:
1. Print a URL -- open it in your browser
2. Log into TickTick and authorize the app
3. You will be redirected -- copy the full redirect URL
4. Paste it into the terminal

Tokens are saved to `~/.ticktick-mcp/tokens.json` (chmod 600) and refreshed
automatically when a refresh token is present.

Note: TickTick does not always return a refresh token. In that case the
access token is long-lived (about 180 days) and the server will tell you to
re-run `python ticktick_mcp.py --oauth` when it expires.

## Usage with Hermes Agent

### Manual MCP config

Add to your `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  ticktick:
    command: "/path/to/.venv/bin/python"
    args:
      - "/path/to/ticktick_mcp.py"
```

Then restart Hermes Agent. The tools will be auto-discovered and registered
as `mcp_ticktick_*`.

### Catalog install (once accepted into Hermes catalog)

```bash
hermes mcp catalog
# Select "ticktick" from the picker
```

## Available Tools

| Tool | Description |
|------|-------------|
| `ticktick_list_projects` | List all projects and lists with IDs |
| `ticktick_list_tasks` | List tasks in a project (flat view, with due dates and tags) |
| `ticktick_list_tasks_by_column` | List tasks grouped by Kanban column/section |
| `ticktick_create_task` | Create a task with title, content, priority, due date, tags, checklist |
| `ticktick_update_task` | Update an existing task's fields (priority -1 = leave unchanged) |
| `ticktick_complete_task` | Mark a task as complete |
| `ticktick_delete_task` | Delete a task |
| `ticktick_get_task` | Get full details of a single task (checklists, tags, content) |
| `ticktick_filter_tasks` | Filter tasks by status (incomplete/completed/all) |

### Priority values

| Value | Meaning | Emoji |
|-------|---------|-------|
| 0 | None (default) | (none) |
| 1 | High | red circle |
| 2 | Medium | orange circle |
| 3 | Low | blue circle |
| 5 | No priority | white circle |

### Task display format

Task lists show: status icon, priority emoji, title, due date (if set),
tags (if any), and a truncated task ID for privacy.

## API Coverage

Uses the TickTick Open API v1 for most operations and v2 for batch delete.
Endpoints:

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List projects | GET | `/open/v1/project` |
| Get project data | GET | `/open/v1/project/{id}/data` |
| Create task | POST | `/open/v1/task` |
| Update task | POST | `/open/v1/task/{id}` |
| Complete task | POST | `/open/v1/project/{pid}/task/{id}/complete` |
| Delete task | POST | `/api/v2/batch/task` |

## Contributing

This is a community MCP server intended for the
[Hermes Agent MCP Catalog](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp#catalog-one-click-install-for-nous-approved-mcps).

## License

MIT -- see [LICENSE](LICENSE).
