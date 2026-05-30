# TickTick MCP Server for Hermes Agent

MCP (Model Context Protocol) server that gives Hermes Agent access to your
TickTick tasks, projects, and Kanban board columns. Uses the official
TickTick Open API with OAuth2 authentication and automatic token refresh.

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

Tokens are saved to `~/.ticktick-mcp/tokens.json` and refreshed automatically.

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

Then restart Hermes. The tools will be auto-discovered.

### Catalog install (once accepted into Hermes catalog)

```bash
hermes mcp catalog
# Select "ticktick" from the picker
```

## Available Tools

| Tool | Description |
|------|-------------|
| `ticktick_list_projects` | List all projects and lists |
| `ticktick_list_tasks` | List tasks in a project (flat view) |
| `ticktick_list_tasks_by_column` | List tasks grouped by Kanban column |
| `ticktick_create_task` | Create a task with title, content, priority, due date, tags |
| `ticktick_update_task` | Update an existing task's fields |
| `ticktick_complete_task` | Mark a task as complete |
| `ticktick_delete_task` | Delete a task |
| `ticktick_get_task` | Get full details of a single task |
| `ticktick_filter_tasks` | Filter tasks by status (incomplete/completed/all) |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TICKTICK_CLIENT_ID` | Yes | -- | OAuth client ID |
| `TICKTICK_CLIENT_SECRET` | Yes | -- | OAuth client secret |
| `TICKTICK_REDIRECT_URI` | No | `http://localhost:3333/callback` | OAuth redirect URI |
| `TICKTICK_CREDENTIALS_PATH` | No | `~/.ticktick-mcp/credentials.json` | Path to credentials file |
| `TICKTICK_TOKENS_PATH` | No | `~/.ticktick-mcp/tokens.json` | Path to tokens file |

## Contributing

This is a community MCP server intended for the
[Hermes Agent MCP Catalog](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp#catalog-one-click-install-for-nous-approved-mcps).

## License

MIT -- see [LICENSE](LICENSE).
