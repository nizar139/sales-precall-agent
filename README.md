# Sales Pre-Call Agent

An AI agent that generates tailored pre-call research briefs for sales reps using the HG Insights MCP. Built as a work sample for the HG Insights AI Product Internship.

## What It Does

A rep describes their call in plain English — company, what they're selling, any context — and the agent pulls live data from HG Insights, analyzes it through the lens of what's being sold, and returns a scannable brief in under 40 seconds.

The brief includes a fit verdict, a single recommended angle, prioritized contacts with sequencing logic, relevant tech stack gaps, buying signals, watch-outs, and a cold call opening the rep can say word-for-word.

A side chat lets reps ask follow-up questions ("what do their Splunk reviews look like?", "find me similar companies") with full research context already loaded.

## Architecture

```
Streamlit frontend  →  FastAPI backend  →  HG Insights MCP  →  OpenRouter (Claude Sonnet)
```

- **Frontend** (`app.py`) — Streamlit, two-column layout, SSE streaming for live tool logs
- **Backend** (`main.py` + `client.py`) — FastAPI, single `MCPClient` managing MCP session and LLM calls
- **MCP** — HG Insights Phoenix MCP over streamable HTTP
- **LLM** — Claude Sonnet via OpenRouter

## Features

- Streams tool call logs to the UI in real time as the agent works
- In-memory tool cache (1hr TTL) — repeated calls for the same company are instant
- Export brief as `.md`
- Shared API key auth on both frontend and backend
- Side chat with full research context seeded automatically

## Setup

**Requirements**
```
fastapi
uvicorn
httpx
streamlit
openai
mcp
python-dotenv
```

**Environment variables** (backend `.env`):
```
OPENROUTER_API_KEY=
PHOENIX_API_KEY=
INTERNAL_API_KEY=
```

**Run locally**
```bash
# Backend
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
streamlit run app.py
```

On first load, if `INTERNAL_API_KEY` is not found in the environment, the frontend prompts for it.

## Deployment

- **Backend** → Railway (Docker). Add the three env vars in the Railway dashboard.
- **Frontend** → Streamlit Cloud. Add `BACKEND_URL` in app Secrets, the user adds their `INTERNAL_API_KEY` when loading the webpage

`requirements.txt` and `Dockerfile` required — see repo root.

## Known Limitations

**Session isolation** — the backend uses a single global `MCPClient`. If user A researches a company and user B researches a different one, user A's side chat will see user B's context. Fix: per-session client instances keyed by a session ID header. Skipped for time.

**No persistent sessions** — refreshing the Streamlit page clears the brief and chat history. Fix: store session state server-side (Redis) and restore on reconnect.

**Token usage** — HG Insights tool responses can be large JSON payloads. Currently mitigated by limiting result counts at the query level. Proper fix: trim tool outputs to only the fields the LLM needs before they enter the context window.

**Minimal auth** — shared secret via `INTERNAL_API_KEY` header. Sufficient for a demo, not for production.

**In-memory cache** — resets on server restart, no invalidation beyond TTL. Fix: Redis with proper key management.

## What I'd Improve With More Time

- Per-session client isolation to support concurrent users properly
- Tool output trimming to reduce token usage and cost (strip unused fields from technographic/contact payloads before they hit the LLM)
- Streaming the LLM response token-by-token instead of waiting for the full brief
- Session persistence across page refreshes
- A "similar companies" research flow that runs the brief for multiple lookalike accounts in parallel