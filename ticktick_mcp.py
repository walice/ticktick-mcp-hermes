#!/usr/bin/env python3
"""TickTick MCP Server for Hermes Agent.

Provides MCP tools for TickTick task management via the TickTick Open API.
Handles OAuth2 authentication and automatic token refresh.

Tools:
  ticktick_list_projects       - List all TickTick projects/lists
  ticktick_list_tasks          - List tasks in a project
  ticktick_list_tasks_by_column - List tasks grouped by column/section
  ticktick_create_task         - Create a new task
  ticktick_update_task         - Update an existing task
  ticktick_complete_task       - Mark a task as complete
  ticktick_delete_task         - Delete a task
  ticktick_get_task            - Get task details
  ticktick_filter_tasks        - Filter tasks by status

Environment variables:
  TICKTICK_CLIENT_ID         - OAuth client ID (required)
  TICKTICK_CLIENT_SECRET     - OAuth client secret (required)
  TICKTICK_REDIRECT_URI      - OAuth redirect URI (default: http://localhost:3333/callback)
  TICKTICK_CREDENTIALS_PATH  - Path to credentials JSON (default: ~/.ticktick-mcp/credentials.json)
  TICKTICK_TOKENS_PATH       - Path to tokens JSON (default: ~/.ticktick-mcp/tokens.json)
"""

import asyncio
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

# --- Paths (configurable via env vars) ---
DEFAULT_DIR = Path(os.path.expanduser("~/.ticktick-mcp"))
CREDENTIALS_PATH = Path(
    os.environ.get("TICKTICK_CREDENTIALS_PATH", str(DEFAULT_DIR / "credentials.json"))
)
TOKENS_PATH = Path(
    os.environ.get("TICKTICK_TOKENS_PATH", str(DEFAULT_DIR / "tokens.json"))
)

# --- API endpoints ---
TICKTICK_AUTH_URL = "https://ticktick.com/oauth/authorize"
TICKTICK_TOKEN_URL = "https://api.ticktick.com/oauth/token"
API_BASE = "https://api.ticktick.com"
OPEN_API = f"{API_BASE}/open/v1"
V2_API = f"{API_BASE}/api/v2"

# --- MCP Server ---
mcp = FastMCP("ticktick", log_level="ERROR")


# -- Auth helpers ----------------------------------------------------------


def get_client_credentials():
    """Get OAuth credentials from env vars or credentials file.

    Checks TICKTICK_CLIENT_ID / TICKTICK_CLIENT_SECRET first (env vars),
    then falls back to the credentials JSON file.
    """
    client_id = os.environ.get("TICKTICK_CLIENT_ID")
    client_secret = os.environ.get("TICKTICK_CLIENT_SECRET")
    redirect_uri = os.environ.get(
        "TICKTICK_REDIRECT_URI", "http://localhost:3333/callback"
    )

    if client_id and client_secret:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }

    if not CREDENTIALS_PATH.exists():
        print(
            "ERROR: No credentials found. Set TICKTICK_CLIENT_ID and "
            "TICKTICK_CLIENT_SECRET env vars, or create a credentials file at "
            f"{CREDENTIALS_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
        creds.setdefault("redirect_uri", redirect_uri)
        return creds


def load_tokens():
    if not TOKENS_PATH.exists():
        return None
    with open(TOKENS_PATH) as f:
        return json.load(f)


def save_tokens(tokens):
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)
    TOKENS_PATH.chmod(0o600)


async def refresh_access_token(refresh_token):
    creds = get_client_credentials()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TICKTICK_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "scope": "tasks:read tasks:write",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            )
        new_tokens = resp.json()
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
        new_tokens.setdefault("refresh_token", refresh_token)
        save_tokens(new_tokens)
        return new_tokens


async def get_valid_token():
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError("No OAuth tokens found. Run with --oauth first.")
    expires_at = tokens.get("expires_at", 0)
    if time.time() >= expires_at - 60:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise RuntimeError(
                "Access token expired and no refresh token is available "
                "(TickTick does not always issue one). Re-run with --oauth."
            )
        tokens = await refresh_access_token(refresh_token)
    return tokens["access_token"]


async def _do(path, method="GET", data=None, retried=False):
    """Make an authenticated request to the TickTick Open API."""
    token = await get_valid_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{OPEN_API}{path}"

    async with httpx.AsyncClient() as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, params=data)
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            resp = await client.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code == 401 and not retried:
            tokens = load_tokens()
            if tokens and tokens.get("refresh_token"):
                await refresh_access_token(tokens["refresh_token"])
                return await _do(path, method, data, retried=True)
            raise RuntimeError(
                "Token expired and no refresh token available. Re-run --oauth."
            )

        if resp.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} failed ({resp.status_code}): {resp.text[:300]}"
            )

        return resp.json() if resp.text else {}


async def _do_v2(method, path, data=None):
    """Make an authenticated request to the TickTick v2 API."""
    token = await get_valid_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{V2_API}{path}"

    async with httpx.AsyncClient() as client:
        if method == "POST":
            resp = await client.post(url, headers=headers, json=data)
        else:
            resp = await client.get(url, headers=headers)

        if resp.status_code >= 400:
            raise RuntimeError(
                f"v2 {method} {path} failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json() if resp.text else {}


# -- Helpers ---------------------------------------------------------------


def _fmt_due(task: dict) -> str:
    """Return a readable due-date string for a task, or empty string."""
    due = task.get("dueDate")
    if not due:
        return ""
    try:
        dt_str = due[:10]  # "2026-05-30T12:00:00+0000" -> "2026-05-30"
        return f" [Due: {dt_str}]"
    except (IndexError, TypeError):
        return f" [Due: {due}]"


# -- MCP Tools -------------------------------------------------------------


@mcp.tool(
    name="ticktick_list_projects", description="List all TickTick projects/lists"
)
async def list_projects() -> str:
    """Get all projects from TickTick."""
    try:
        projects = await _do("/project")
        result = []
        for p in projects:
            name = p.get("name", "Unnamed")
            pid = p.get("id", "?")
            kind = p.get("kind", "")
            kind_tag = f" [{kind}]" if kind else ""
            result.append(f"  \u2022 {name}{kind_tag} (ID: {pid})")
        if not result:
            return "No projects found."
        return f"TickTick Projects ({len(result)}):\n" + "\n".join(result)
    except Exception as e:
        return f"Error listing projects: {e}"


@mcp.tool(
    name="ticktick_list_tasks", description="List tasks in a TickTick project"
)
async def list_tasks(project_id: str) -> str:
    """List all tasks in a project (from project data endpoint)."""
    try:
        data = await _do(f"/project/{project_id}/data")
        tasks = data.get("tasks", [])
        project_name = data.get("project", {}).get("name", project_id)
        if not tasks:
            return f"No tasks in project '{project_name}'."
        lines = [f"Tasks in '{project_name}' ({len(tasks)}):"]
        for t in tasks:
            status = "\u2713" if t.get("status") == 1 else "\u25CB"
            priority = t.get("priority", 0)
            prio_map = {
                0: "",
                1: "\U0001F534",
                2: "\U0001F7E0",
                3: "\U0001F535",
                5: "\u26AA",
            }
            prio_str = prio_map.get(priority, "")
            title = t.get("title", "Untitled")
            task_id = t.get("id", "?")
            due_str = _fmt_due(t)
            tags_str = (
                f" [{', '.join(t.get('tags', []))}]" if t.get("tags") else ""
            )
            lines.append(
                f"  {status} {prio_str} {title}{due_str}{tags_str}"
                f" ({task_id[:8]}...)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tasks: {e}"


@mcp.tool(
    name="ticktick_list_tasks_by_column",
    description="List tasks in a TickTick project, grouped by column/section",
)
async def list_tasks_by_column(project_id: str, column_name: str = "") -> str:
    """List tasks in a project grouped by their columns (Kanban board view).

    Args:
        project_id: Project ID to query
        column_name: Optional column name to filter by. If empty, shows all columns.
    """
    try:
        data = await _do(f"/project/{project_id}/data")
        tasks = data.get("tasks", [])
        columns = data.get("columns", [])
        project_name = data.get("project", {}).get("name", project_id)

        col_map = {c["id"]: c["name"] for c in columns}
        col_by_name = {c["name"].strip().lower(): c["id"] for c in columns}

        if not tasks:
            return f"No tasks in project '{project_name}'."

        grouped: dict[str, list] = {}
        uncategorized: list = []
        for t in tasks:
            cid = t.get("columnId")
            if cid and cid in col_map:
                grouped.setdefault(cid, []).append(t)
            else:
                uncategorized.append(t)

        filter_cid = None
        filter_col_name = column_name.strip()
        if filter_col_name:
            filter_lower = filter_col_name.lower()
            if filter_lower in col_by_name:
                filter_cid = col_by_name[filter_lower]
            else:
                for cname, cid in col_by_name.items():
                    if filter_lower in cname or cname in filter_lower:
                        filter_cid = cid
                        filter_col_name = col_map.get(cid, filter_col_name)
                        break

        lines = [f"Project: {project_name}"]
        if filter_cid is not None:
            target_tasks = grouped.get(filter_cid, [])
            col_title = col_map.get(filter_cid, filter_col_name)
            lines.append(f"\n\u2501 {col_title} ({len(target_tasks)} tasks)")
            for t in target_tasks:
                status = "\u2713" if t.get("status") == 1 else "\u25CB"
                title = t.get("title", "Untitled")
                due_str = _fmt_due(t)
                tags_str = (
                    f" [{', '.join(t.get('tags', []))}]" if t.get("tags") else ""
                )
                lines.append(f"  {status} {title}{due_str}{tags_str}")
        else:
            sorted_cols = sorted(columns, key=lambda c: c.get("sortOrder", 0))
            for col in sorted_cols:
                cid = col["id"]
                col_tasks = grouped.get(cid, [])
                col_title = col["name"]
                lines.append(f"\n\u2501 {col_title} ({len(col_tasks)} tasks)")
                for t in col_tasks:
                    status = "\u2713" if t.get("status") == 1 else "\u25CB"
                    title = t.get("title", "Untitled")
                    due_str = _fmt_due(t)
                    tags_str = (
                        f" [{', '.join(t.get('tags', []))}]"
                        if t.get("tags")
                        else ""
                    )
                    lines.append(f"  {status} {title}{due_str}{tags_str}")
            if uncategorized:
                lines.append(
                    f"\n\u2501 Uncategorized ({len(uncategorized)} tasks)"
                )
                for t in uncategorized:
                    status = "\u2713" if t.get("status") == 1 else "\u25CB"
                    title = t.get("title", "Untitled")
                    due_str = _fmt_due(t)
                    lines.append(f"  {status} {title}{due_str}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing tasks by column: {e}"


@mcp.tool(name="ticktick_create_task", description="Create a new task in TickTick")
async def create_task(
    title: str,
    project_id: str,
    content: str = "",
    priority: int = 0,
    due_date: str = "",
    tags: str = "",
    checklist: str = "",
) -> str:
    """Create a task in TickTick.

    Args:
        title: Task title (required)
        project_id: Project/list ID to add the task to
        content: Task description/notes
        priority: Priority level (0=none, 1=high, 2=medium, 3=low, 5=no priority)
        due_date: Due date ISO format (e.g. '2026-05-30T12:00:00+0000')
        tags: Comma-separated list of tags
        checklist: Comma-separated checklist items
    """
    try:
        payload = {
            "title": title,
            "projectId": project_id,
            "content": content,
            "priority": priority,
        }
        if due_date:
            payload["dueDate"] = due_date
        if tags:
            payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if checklist:
            payload["items"] = [
                {"title": t.strip(), "status": 0}
                for t in checklist.split(",")
                if t.strip()
            ]
        result = await _do("/task", "POST", payload)
        task_id = result.get("id", "unknown")
        return f"Task created: {title} (ID: {task_id})"
    except Exception as e:
        return f"Error creating task: {e}"


@mcp.tool(
    name="ticktick_update_task", description="Update an existing task in TickTick"
)
async def update_task(
    project_id: str,
    task_id: str,
    title: str = "",
    content: str = "",
    priority: int = -1,
    due_date: str = "",
    tags: str = "",
) -> str:
    """Update a task's fields.

    Args:
        project_id: The project containing the task
        task_id: The task ID to update
        title: New title
        content: New description
        priority: Priority level (-1=leave unchanged, 0=none, 1=high,
            2=medium, 3=low, 5=no priority)
        due_date: Due date ISO format
        tags: Comma-separated list of tags
    """
    try:
        data = await _do(f"/project/{project_id}/data")
        current = None
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                current = t
                break
        if not current:
            return f"Task {task_id} not found in project {project_id}."

        payload = dict(current)
        if title:
            payload["title"] = title
        if content:
            payload["content"] = content
        if priority >= 0:
            payload["priority"] = priority
        if due_date:
            payload["dueDate"] = due_date
        if tags:
            payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        await _do(f"/task/{task_id}", "POST", payload)
        return f"Task {task_id} updated."
    except Exception as e:
        return f"Error updating task: {e}"


@mcp.tool(
    name="ticktick_complete_task",
    description="Mark a task as complete in TickTick",
)
async def complete_task(project_id: str, task_id: str) -> str:
    """Complete a task by project ID and task ID."""
    try:
        await _do(f"/project/{project_id}/task/{task_id}/complete", "POST")
        return f"Task {task_id[:8]}... completed."
    except Exception as e:
        return f"Error completing task: {e}"


@mcp.tool(name="ticktick_delete_task", description="Delete a task from TickTick")
async def delete_task(project_id: str, task_id: str) -> str:
    """Delete a task by project ID and task ID."""
    try:
        payload = {"delete": [{"projectId": project_id, "taskId": task_id}]}
        await _do_v2("POST", "/batch/task", payload)
        return f"Task {task_id[:8]}... deleted."
    except Exception as e:
        return f"Error deleting task: {e}"


@mcp.tool(
    name="ticktick_get_task",
    description="Get a single task's details from TickTick",
)
async def get_task(project_id: str, task_id: str) -> str:
    """Get detailed information about a specific task."""
    try:
        data = await _do(f"/project/{project_id}/data")
        task = None
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                task = t
                break
        if not task:
            return f"Task {task_id} not found in project {project_id}."

        CHECK = "\u2713"
        CROSS = "\u25CB"
        if task.get("status") == 1:
            status_str = f"{CHECK} Completed"
        else:
            status_str = f"{CROSS} Active"
        lines = [
            f"Title: {task.get('title', 'Untitled')}",
            f"ID: {task.get('id', '?')}",
            f"Status: {status_str}",
        ]
        if task.get("content"):
            lines.append(f"Content: {task['content']}")
        if task.get("priority"):
            prio = {1: "High", 2: "Medium", 3: "Low", 5: "None"}.get(
                task["priority"], str(task["priority"])
            )
            lines.append(f"Priority: {prio}")
        if task.get("dueDate"):
            lines.append(f"Due: {task['dueDate']}")
        if task.get("tags"):
            lines.append(f"Tags: {', '.join(task['tags'])}")
        if task.get("items"):
            items = task["items"]
            done = sum(1 for i in items if i.get("status") == 1)
            lines.append(f"Checklist: {done}/{len(items)}")
            for i in items:
                ck = "\u2713" if i.get("status") == 1 else "\u25CB"
                lines.append(f"  {ck} {i.get('title', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting task: {e}"


@mcp.tool(
    name="ticktick_filter_tasks",
    description="Filter tasks in a project by status",
)
async def filter_tasks(project_id: str, status: str = "incomplete") -> str:
    """Filter tasks in a project.

    Args:
        project_id: Project ID to filter in
        status: 'incomplete', 'completed', or 'all' (default: incomplete)
    """
    try:
        data = await _do(f"/project/{project_id}/data")
        all_tasks = data.get("tasks", [])
        project_name = data.get("project", {}).get("name", project_id)

        if status == "completed":
            tasks = [t for t in all_tasks if t.get("status") == 1]
        elif status == "incomplete":
            tasks = [t for t in all_tasks if t.get("status") != 1]
        else:
            tasks = all_tasks

        if not tasks:
            return f"No {status} tasks in '{project_name}'."
        lines = [
            f"{status.capitalize()} tasks in '{project_name}' ({len(tasks)}):"
        ]
        for t in tasks:
            tstatus = "\u2713" if t.get("status") == 1 else "\u25CB"
            title = t.get("title", "Untitled")
            due_str = _fmt_due(t)
            lines.append(f"  {tstatus} {title}{due_str} ({t.get('id', '?')[:8]}...)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error filtering tasks: {e}"


# -- OAuth Setup -----------------------------------------------------------


async def run_oauth_setup():
    """Run the OAuth flow interactively to obtain initial tokens."""
    creds = get_client_credentials()
    client_id = creds["client_id"]
    redirect_uri = creds["redirect_uri"]

    print("\n=== TickTick OAuth Setup ===")
    print("1. Open this URL in your browser:")
    print()
    auth_url = (
        f"{TICKTICK_AUTH_URL}?"
        f"client_id={urllib.parse.quote(client_id)}&"
        f"scope=tasks:read+tasks:write&"
        f"state=hermes-ticktick&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code"
    )
    print(f"   {auth_url}")
    print()
    print("2. Log into TickTick and authorize the app.")
    print("3. Paste the FULL redirect URL you get:")
    callback_url = input("> ").strip()

    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if not code:
        print("ERROR: No 'code' found in URL.")
        sys.exit(1)

    print("\nExchanging code for tokens...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TICKTICK_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": creds["client_secret"],
            },
        )
        if resp.status_code != 200:
            print(f"ERROR ({resp.status_code}): {resp.text}")
            sys.exit(1)
        tokens = resp.json()

    expires_in = tokens.get("expires_in", 3600)
    tokens["expires_at"] = time.time() + expires_in
    save_tokens(tokens)
    print(f"\n\u2713 OAuth complete! Token expires in {expires_in}s")
    print(f"  Has refresh_token: {bool(tokens.get('refresh_token'))}")
    print(f"  Stored at: {TOKENS_PATH}")


# -- Main ------------------------------------------------------------------


if __name__ == "__main__":
    if "--oauth" in sys.argv:
        asyncio.run(run_oauth_setup())
    else:
        if not TOKENS_PATH.exists():
            print("ERROR: No OAuth tokens found.", file=sys.stderr)
            print("Run with --oauth first.", file=sys.stderr)
            sys.exit(1)
        mcp.run()
