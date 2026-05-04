# claude-svn-tools

Subversion (SVN) integration for [Claude Code](https://docs.claude.com/en/docs/claude-code) and [Cowork](https://claude.com/product/cowork).

Wraps the local `svn` CLI as MCP tools so Claude can run `status`, `log`, `diff`, `info`, `list`, `cat`, `blame`, `update`, `checkout`, `add`, `revert`, `merge`, and `resolve` against your working copy. `svn commit` is intentionally NOT exposed — repo writes stay your call.

## Install

### Cowork

Two ways:

**Drag-and-drop into chat (easiest).** Download [`svn-tools.plugin`](./svn-tools.plugin), then drag it from File Explorer / Finder into any open Cowork conversation. It'll render as an install card — click install. (Double-clicking the file from your file manager won't do anything — there's no OS file association.)

**Or via the Customize menu.** Cowork tab → **Customize** in the left sidebar → **Add plugins** → **Upload a file** → drag in or browse to the file. Cowork's picker may filter to `.zip` only — if so, just rename `svn-tools.plugin` → `svn-tools.zip` (it's the same archive either way) and try again.

### Claude Code

```
/plugin marketplace add EvoPulseGaming/claude-svn-tools
/plugin install svn-tools@claude-svn-tools
```

## Prerequisites

- The Subversion command-line client (`svn`) on `PATH`. Verify with `svn --version`.
- Python 3.8+ on `PATH` as `python`. The MCP server is a single zero-dependency Python script.
- Cached SVN credentials. The server runs `svn` with `--non-interactive`, so it never prompts for a password — if creds aren't cached, commands fail with a clear authentication error and you can re-cache them by running any `svn` command interactively once.

## Configuration

After install, point the plugin at your default working copy by editing the installed plugin's `.mcp.json`:

```json
{
  "mcpServers": {
    "svn": {
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/server/svn_mcp_server.py"],
      "env": {
        "SVN_DEFAULT_WC": "K:\\my-project",
        "SVN_TIMEOUT_SEC": "60",
        "SVN_MAX_OUTPUT_BYTES": "200000"
      }
    }
  }
}
```

| Variable | Default | Purpose |
|---|---|---|
| `SVN_DEFAULT_WC` | (none) | Default working-copy path used when a tool call omits `path` / `cwd`. |
| `SVN_TIMEOUT_SEC` | `60` | Hard timeout per `svn` invocation. |
| `SVN_MAX_OUTPUT_BYTES` | `200000` | Cap on returned stdout+stderr; truncated past this with a marker. |

## Updating

After editing anything under `plugins/svn-tools/`:

1. Bump `version` in both `plugins/svn-tools/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
2. Rebuild the bundle: `cd plugins/svn-tools && zip -r ../../svn-tools.plugin . -x "*/__pycache__/*"`
3. Commit and push.

## License

[Unlicense](./LICENSE) — public domain dedication. Do whatever you want with it.
