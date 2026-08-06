# Run Coach

An MCP server that pulls your Strava data and gives you a run recommendation from Claude, rendered as a dashboard.

![image](./img/Screenshot%202026-08-06%20at%2010.49.02 AM.png)

## What it does

- Fetches recent activities and all-time stats from the Strava API
- Shows them in a Prefab UI dashboard (rides, runs, distance, suffering index)
- Has a button that sends your last N days of runs to Claude and gets back a plain-English recommendation for today's run

## Stack

- [FastMCP](https://gofastmcp.com) — the MCP server itself, with `FastMCPApp` for the UI-facing tools
- [Prefab](https://prefab.prefect.io) — the dashboard UI, written in Python instead of JSX
- [Anthropic API](https://docs.claude.com) — generates the run recommendation
- `httpx` — talks to Strava
- `uv` — dependency management and running the thing

## Setup

### 1. Install dependencies

```bash
uv add fastmcp anthropic httpx
```

### 2. Strava API access

You need a Strava API app (create one at strava.com/settings/api) and a one-time OAuth flow to get a refresh token. Scope needs to include `activity:read_all` — the default `read` scope isn't enough.

Run the setup script (not part of the server itself) to get your first `refresh_token`, then it lives in `strava_tokens.json`.

### 3. Environment variables

Create a `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_TOKEN_PATH=./strava_tokens.json
```

### 4. Run it

```bash
uv run --env-file .env --with fastmcp fastmcp dev apps mcpserver.py --reload
```

## Project structure

```
mcpserver.py       # the server: tools, UI, everything
strava_auth.py      # token refresh logic
strava_tokens.json  # your access/refresh token (gitignored)
.env                 # secrets (gitignored)
```

## How the recommendation flow works

1. Dashboard loads → fetches Strava data server-side, renders stats
2. Click "Get Recommendation" → calls `get_run_recommendation`, a private tool the UI can hit but the model can't call directly in chat
3. That tool re-fetches recent runs, trims to the fields that matter (distance, pace, HR, suffer score), sends them to Claude with a coaching system prompt
4. Response comes back, gets dropped into the page via state

## Considerations

- Strava rate limits are tight (100 req/15min, 1000/day)
- `max_tokens` needs headroom if thinking is ever turned on — thinking and output share the budget