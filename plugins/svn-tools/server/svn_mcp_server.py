"""
svn-tools MCP server.

A zero-dependency Python MCP server that wraps the local `svn` command-line
client and exposes a curated set of operations as MCP tools.

Speaks MCP (JSON-RPC 2.0) over stdio using newline-delimited JSON messages.

Environment variables:
  SVN_DEFAULT_WC          Default working-copy path used when a tool call
                          omits `path` / `cwd`. Optional.
  SVN_TIMEOUT_SEC         Max seconds any single svn invocation may run.
                          Default 60.
  SVN_MAX_OUTPUT_BYTES    Cap on combined stdout+stderr returned to the
                          client. Output beyond the cap is truncated with
                          a clear marker. Default 200_000.
"""

import json
import os
import shlex
import subprocess
import sys
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SERVER_NAME = "svn-tools"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

DEFAULT_WC = os.environ.get("SVN_DEFAULT_WC", "").strip() or None
TIMEOUT_SEC = int(os.environ.get("SVN_TIMEOUT_SEC", "60"))
MAX_OUTPUT_BYTES = int(os.environ.get("SVN_MAX_OUTPUT_BYTES", "200000"))


# ---------------------------------------------------------------------------
# svn invocation
# ---------------------------------------------------------------------------

def _resolve_cwd(cwd: Optional[str]) -> Optional[str]:
    """Pick the working directory for the svn process."""
    if cwd and cwd.strip():
        return cwd
    return DEFAULT_WC


def run_svn(args: list[str], cwd: Optional[str] = None) -> dict:
    """
    Run `svn <args>` and return a dict suitable for an MCP tool result.

    Always passes --non-interactive so svn never hangs waiting for input.
    Relies on cached credentials (the user confirmed cached auth).
    """
    cmd = ["svn", "--non-interactive"] + list(args)
    work_dir = _resolve_cwd(cwd)

    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
            check=False,
        )
    except FileNotFoundError:
        return _err(
            "svn executable not found on PATH. Install Subversion or "
            "ensure `svn` is on PATH for the process running Claude."
        )
    except subprocess.TimeoutExpired:
        return _err(
            f"svn timed out after {TIMEOUT_SEC}s. "
            f"Command was: svn {' '.join(shlex.quote(a) for a in args)}"
        )
    except Exception as exc:  # noqa: BLE001
        return _err(f"Failed to run svn: {exc!r}")

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    body = stdout
    if stderr:
        body = f"{stdout}\n--- stderr ---\n{stderr}" if stdout else stderr

    truncated = False
    if len(body.encode("utf-8", "replace")) > MAX_OUTPUT_BYTES:
        body = body.encode("utf-8", "replace")[:MAX_OUTPUT_BYTES].decode(
            "utf-8", "replace"
        )
        body += (
            f"\n\n[output truncated to {MAX_OUTPUT_BYTES} bytes — re-run with "
            "narrower scope, e.g. a specific path or smaller revision range]"
        )
        truncated = True

    header = (
        f"$ svn {' '.join(shlex.quote(a) for a in args)}\n"
        f"(cwd={work_dir or '<none>'}, exit={proc.returncode}"
        f"{', truncated' if truncated else ''})\n\n"
    )
    return _ok(header + body, is_error=proc.returncode != 0)


def _ok(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _err(text: str) -> dict:
    return _ok(text, is_error=True)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
#
# Each tool maps cleanly to an `svn <subcommand>` invocation. We deliberately
# do NOT expose `commit` — write-to-repo operations should be done by the
# user. We DO expose local mutations (`add`, `revert`, `update`, `merge`,
# `resolve`, `checkout`) because they only touch the working copy.

TOOLS: list[dict] = [
    {
        "name": "svn_status",
        "description": (
            "Show the status of files in a Subversion working copy. "
            "Use this before suggesting any change so you know the current "
            "state of the WC."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "File or directory path to check. Defaults to '.' "
                        "(the working-copy root)."
                    ),
                },
                "cwd": {
                    "type": "string",
                    "description": "Working-copy directory svn runs from.",
                },
                "show_updates": {
                    "type": "boolean",
                    "description": "Pass -u to also show out-of-date items.",
                },
                "verbose": {"type": "boolean"},
            },
        },
    },
    {
        "name": "svn_log",
        "description": "Show commit log for a path or revision range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "description": "Max number of revisions to show (-l).",
                    "default": 20,
                },
                "revision": {
                    "type": "string",
                    "description": (
                        "Revision or range, e.g. 'HEAD', '1234', "
                        "'1200:1250', '{2026-01-01}:HEAD'."
                    ),
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Pass -v to include changed paths.",
                },
            },
        },
    },
    {
        "name": "svn_diff",
        "description": (
            "Show diff for local changes, between revisions, or between "
            "paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "revision": {
                    "type": "string",
                    "description": (
                        "Revision or range, e.g. 'BASE', 'HEAD', '1234', "
                        "'1200:1250'."
                    ),
                },
                "old": {"type": "string", "description": "--old=<arg>"},
                "new": {"type": "string", "description": "--new=<arg>"},
                "git_style": {
                    "type": "boolean",
                    "description": "Pass --git for git-style diffs.",
                },
            },
        },
    },
    {
        "name": "svn_info",
        "description": (
            "Show metadata about a working copy or repo URL (revision, "
            "URL, repo root, last-changed author, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "revision": {"type": "string"},
            },
        },
    },
    {
        "name": "svn_list",
        "description": "List directory contents in the repo (svn ls).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repo URL or working-copy path.",
                },
                "cwd": {"type": "string"},
                "revision": {"type": "string"},
                "verbose": {"type": "boolean"},
                "recursive": {"type": "boolean"},
            },
        },
    },
    {
        "name": "svn_cat",
        "description": "Print the contents of a file at a given revision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repo URL or working-copy path.",
                },
                "cwd": {"type": "string"},
                "revision": {
                    "type": "string",
                    "description": "Revision (default HEAD/BASE).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "svn_blame",
        "description": "Annotate a file with revision/author per line.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "revision": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "svn_update",
        "description": (
            "Update a working copy to a given revision (default HEAD). "
            "Touches the working copy only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "revision": {"type": "string", "description": "Default HEAD."},
                "accept": {
                    "type": "string",
                    "description": (
                        "Conflict resolution: postpone, base, mine-conflict, "
                        "theirs-conflict, mine-full, theirs-full."
                    ),
                },
            },
        },
    },
    {
        "name": "svn_checkout",
        "description": (
            "Check out a working copy from a repo URL. WRITES TO DISK at "
            "`dest` — only run when the user has explicitly asked for a "
            "checkout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Repo URL."},
                "dest": {
                    "type": "string",
                    "description": "Local directory to create.",
                },
                "revision": {"type": "string"},
                "depth": {
                    "type": "string",
                    "description": (
                        "empty, files, immediates, infinity (default)."
                    ),
                },
            },
            "required": ["url", "dest"],
        },
    },
    {
        "name": "svn_add",
        "description": (
            "Schedule paths for addition under version control. Affects the "
            "working copy only — does not commit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "One or more paths to add.",
                },
                "cwd": {"type": "string"},
                "force": {"type": "boolean"},
                "no_ignore": {"type": "boolean"},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "svn_revert",
        "description": (
            "DESTRUCTIVE on the working copy: discards local edits to the "
            "given paths. Only invoke after explicit user confirmation in "
            "chat."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to revert.",
                },
                "cwd": {"type": "string"},
                "recursive": {"type": "boolean"},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "svn_merge",
        "description": (
            "Merge changes between sources/revisions into a working copy. "
            "Touches the working copy only — does not commit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Merge source URL or path.",
                },
                "source2": {
                    "type": "string",
                    "description": (
                        "Optional second source for two-URL merge syntax."
                    ),
                },
                "target": {
                    "type": "string",
                    "description": "Target WC path. Defaults to '.'.",
                },
                "cwd": {"type": "string"},
                "revision": {"type": "string", "description": "-r N or N:M."},
                "dry_run": {"type": "boolean"},
                "reintegrate": {"type": "boolean"},
                "accept": {
                    "type": "string",
                    "description": (
                        "Conflict resolution mode (see svn_update)."
                    ),
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "svn_resolve",
        "description": "Resolve conflicts on paths in the working copy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "cwd": {"type": "string"},
                "accept": {
                    "type": "string",
                    "description": (
                        "Required: working, base, mine-conflict, "
                        "theirs-conflict, mine-full, theirs-full."
                    ),
                },
                "recursive": {"type": "boolean"},
            },
            "required": ["paths", "accept"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _flag(args: list[str], cond: Any, flag: str) -> None:
    if cond:
        args.append(flag)


def _opt(args: list[str], value: Any, flag: str) -> None:
    if value is not None and value != "":
        args.extend([flag, str(value)])


def call_tool(name: str, params: dict) -> dict:
    p = params or {}
    cwd = p.get("cwd")

    if name == "svn_status":
        a = ["status"]
        _flag(a, p.get("show_updates"), "-u")
        _flag(a, p.get("verbose"), "-v")
        a.append(p.get("path") or ".")
        return run_svn(a, cwd)

    if name == "svn_log":
        a = ["log"]
        _opt(a, p.get("limit", 20), "-l")
        _opt(a, p.get("revision"), "-r")
        _flag(a, p.get("verbose"), "-v")
        if p.get("path"):
            a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_diff":
        a = ["diff"]
        _opt(a, p.get("revision"), "-r")
        _opt(a, p.get("old"), "--old")
        _opt(a, p.get("new"), "--new")
        _flag(a, p.get("git_style"), "--git")
        if p.get("path"):
            a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_info":
        a = ["info"]
        _opt(a, p.get("revision"), "-r")
        if p.get("path"):
            a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_list":
        a = ["list"]
        _opt(a, p.get("revision"), "-r")
        _flag(a, p.get("verbose"), "-v")
        _flag(a, p.get("recursive"), "-R")
        if p.get("path"):
            a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_cat":
        if not p.get("path"):
            return _err("svn_cat requires `path`.")
        a = ["cat"]
        _opt(a, p.get("revision"), "-r")
        a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_blame":
        if not p.get("path"):
            return _err("svn_blame requires `path`.")
        a = ["blame"]
        _opt(a, p.get("revision"), "-r")
        a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_update":
        a = ["update"]
        _opt(a, p.get("revision"), "-r")
        _opt(a, p.get("accept"), "--accept")
        if p.get("path"):
            a.append(p["path"])
        return run_svn(a, cwd)

    if name == "svn_checkout":
        if not p.get("url") or not p.get("dest"):
            return _err("svn_checkout requires `url` and `dest`.")
        a = ["checkout"]
        _opt(a, p.get("revision"), "-r")
        _opt(a, p.get("depth"), "--depth")
        a.extend([p["url"], p["dest"]])
        return run_svn(a, cwd)

    if name == "svn_add":
        paths = p.get("paths") or []
        if not paths:
            return _err("svn_add requires non-empty `paths`.")
        a = ["add"]
        _flag(a, p.get("force"), "--force")
        _flag(a, p.get("no_ignore"), "--no-ignore")
        a.extend(paths)
        return run_svn(a, cwd)

    if name == "svn_revert":
        paths = p.get("paths") or []
        if not paths:
            return _err("svn_revert requires non-empty `paths`.")
        a = ["revert"]
        _flag(a, p.get("recursive"), "-R")
        a.extend(paths)
        return run_svn(a, cwd)

    if name == "svn_merge":
        if not p.get("source"):
            return _err("svn_merge requires `source`.")
        a = ["merge"]
        _opt(a, p.get("revision"), "-r")
        _flag(a, p.get("dry_run"), "--dry-run")
        _flag(a, p.get("reintegrate"), "--reintegrate")
        _opt(a, p.get("accept"), "--accept")
        a.append(p["source"])
        if p.get("source2"):
            a.append(p["source2"])
        if p.get("target"):
            a.append(p["target"])
        return run_svn(a, cwd)

    if name == "svn_resolve":
        paths = p.get("paths") or []
        accept = p.get("accept")
        if not paths or not accept:
            return _err("svn_resolve requires `paths` and `accept`.")
        a = ["resolve", "--accept", accept]
        _flag(a, p.get("recursive"), "-R")
        a.extend(paths)
        return run_svn(a, cwd)

    return _err(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# JSON-RPC plumbing (stdio, newline-delimited)
# ---------------------------------------------------------------------------

def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def handle(message: dict) -> Optional[dict]:
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no id) get no response.
    if req_id is None:
        # e.g. notifications/initialized — nothing to do.
        return None

    if method == "initialize":
        return _response(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        )

    if method == "tools/list":
        return _response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}
        try:
            result = call_tool(tool_name, tool_args)
        except Exception as exc:  # noqa: BLE001
            result = _err(f"Tool {tool_name} crashed: {exc!r}")
        return _response(req_id, result)

    if method == "ping":
        return _response(req_id, {})

    return _error(req_id, -32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            _send(_error(None, -32700, f"Parse error: {exc}"))
            continue

        # Handle batched arrays per JSON-RPC 2.0 (rare for MCP, but safe).
        if isinstance(msg, list):
            for sub in msg:
                resp = handle(sub)
                if resp is not None:
                    _send(resp)
        else:
            resp = handle(msg)
            if resp is not None:
                _send(resp)


if __name__ == "__main__":
    main()
