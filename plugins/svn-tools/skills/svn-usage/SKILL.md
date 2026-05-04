---
name: svn-usage
description: Use this skill any time the user asks about Subversion (SVN) — checking working-copy state, reading commit history, viewing diffs, updating, merging, or any other svn-prefixed operation. Triggers include mentions of "svn", "subversion", "working copy", "trunk", "branches", "tags", "revision", "merge", "checkout", or filenames inside a known SVN working copy. Also triggers when the user asks "what changed", "who wrote this line", or "what's the latest" in a context where the project is under SVN.
---

# SVN usage

This plugin exposes the local `svn` CLI to Claude as MCP tools prefixed `svn_*`. Use those tools whenever the user asks anything about a Subversion working copy or repository.

## Tool inventory

Read-only:
- `svn_status` — current state of the WC
- `svn_log` — commit history
- `svn_diff` — local edits or revision-to-revision diff
- `svn_info` — metadata (URL, revision, last author, etc.)
- `svn_list` — list directory contents (WC or repo URL)
- `svn_cat` — file contents at a revision
- `svn_blame` — annotate a file with revision/author per line

Working-copy mutations (no repo writes):
- `svn_update` — pull latest from server
- `svn_checkout` — create a new working copy
- `svn_add` — schedule paths for addition
- `svn_revert` — discard local edits (DESTRUCTIVE)
- `svn_merge` — merge changes into WC (does not commit)
- `svn_resolve` — mark conflicts resolved

Note: `svn commit` is intentionally NOT exposed. The user always runs commits themselves.

## Workflow rules

1. Before suggesting any change, run `svn_status` so you know the actual state of the WC. Don't assume.
2. Before invoking any mutation tool (`svn_update`, `svn_revert`, `svn_merge`, `svn_add`, `svn_resolve`, `svn_checkout`), confirm with the user in chat. State exactly which paths and what will happen. `svn_revert` and `svn_merge` are especially worth flagging because they overwrite local content.
3. Prefer read-only tools to investigate before proposing actions. Almost every question about "what's going on" is answerable with status + log + diff.
4. Pass `cwd` (working-copy directory) when the user has multiple checkouts or when the default working copy isn't set. If a default is configured via `SVN_DEFAULT_WC`, omit `cwd` to use it.
5. For long history, use `limit` on `svn_log` rather than dumping thousands of revisions.
6. For binary files, prefer `svn_info` and `svn_blame` over `svn_cat` / `svn_diff`.
7. If a tool returns a non-zero exit and the message mentions authentication, tell the user — credentials may have expired. Do not attempt to enter credentials yourself.

## Common tasks

- "What did I change?" → `svn_status` then `svn_diff`.
- "Who last touched this file?" → `svn_blame` (then `svn_log` on that file for context).
- "Get me up to date" → confirm, then `svn_update`.
- "What's on the branch vs trunk?" → `svn_diff` with `old`/`new` set to the two URLs.
- "Where does this WC point?" → `svn_info`.

## Output handling

Tool output is prefixed with the exact `svn` command and a `(cwd=..., exit=...)` header so you can see what ran. Output is capped at ~200 KB; if you see a `[output truncated...]` marker, narrow the query (specific path, smaller `-r` range, or `--limit`).
