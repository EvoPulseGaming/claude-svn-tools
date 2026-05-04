# svn-tools

Gives Claude (Cowork / Claude Code) read and working-copy access to a local Subversion repository by wrapping the `svn` command-line client as MCP tools.

## What it exposes

Read-only: `svn_status`, `svn_log`, `svn_diff`, `svn_info`, `svn_list`, `svn_cat`, `svn_blame`.

Working-copy mutations (never writes to the repo): `svn_update`, `svn_checkout`, `svn_add`, `svn_revert`, `svn_merge`, `svn_resolve`.

`svn commit` is deliberately NOT exposed — commits are always done by you.

## Prerequisites

- The Subversion command-line client (`svn`) must be on `PATH` for the process running Claude. Verify with `svn --version`.
- Python 3.8 or newer must be on `PATH` as `python`. The MCP server is a single zero-dependency Python script.
- Credentials must be cached (the typical case after one successful interactive `svn` command). The server runs `svn` with `--non-interactive`, so it will not prompt for a password — if creds aren't cached, commands will fail with an authentication error and you can run a single `svn` command yourself to re-cache them.

## Configuration

All configuration is via environment variables in `.mcp.json`:

| Variable               | Default | Purpose                                                                |
|------------------------|---------|------------------------------------------------------------------------|
| `SVN_DEFAULT_WC`       | (none)  | Default working-copy path used when a tool call omits `path` / `cwd`. |
| `SVN_TIMEOUT_SEC`      | `60`    | Hard timeout per `svn` invocation.                                     |
| `SVN_MAX_OUTPUT_BYTES` | `200000`| Cap on returned stdout+stderr; over this is truncated with a marker.   |

Set `SVN_DEFAULT_WC` to your usual working copy (e.g. `K:\\5.7-patch-april-26`) so you don't have to pass `cwd` on every call.

## Layout

```
svn-tools/
├── .claude-plugin/plugin.json   # plugin manifest
├── .mcp.json                    # MCP server registration
├── server/svn_mcp_server.py     # the server (Python, no deps)
├── skills/svn-usage/SKILL.md    # tells Claude how/when to use the tools
└── README.md
```

## Safety model

The server passes `--non-interactive` to every `svn` call so it cannot hang waiting for a prompt. Output is byte-capped to keep large `log -v` or recursive `diff` outputs from blowing up the chat. The bundled skill instructs Claude to confirm in chat before any mutating call (`update`, `revert`, `merge`, `add`, `resolve`, `checkout`).

## Troubleshooting

- "svn executable not found on PATH" → install Subversion or fix PATH for the Cowork/Claude process. On Windows, TortoiseSVN's bundled CLI works if you tick the "command line client tools" install option, or use the standalone Apache distribution.
- Auth errors → run any `svn` command yourself once interactively to re-cache credentials.
- Truncated output → narrow the request (specific path, smaller `-r` range, lower `--limit`).
