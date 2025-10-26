# MarketLens — Real-Time Multi-Agent Market Intelligence Console

>  **MarketLens** orchestrates analyst, research, trading, and risk-management agents with Gemini-powered reasoning, FastAPI streaming backends, and a Vite/React command center.  

---

## Table of Contents
1. [Overview](#overview)
2. [Feature Highlights](#feature-highlights)
3. [System Architecture](#system-architecture)
4. [Repository Layout](#repository-layout)
5. [Prerequisites](#prerequisites)
6. [Environment Variables](#environment-variables)
7. [Quick Start](#quick-start)
8. [Operating the Console](#operating-the-console)
9. [Agent & Tooling Pipeline](#agent--tooling-pipeline)
10. [Frontend Experience](#frontend-experience)
11. [API Surface](#api-surface)
12. [Data, Storage & Assets](#data-storage--assets)
13. [Observability & Logs](#observability--logs)
14. [Testing & Tooling](#testing--tooling)
15. [Troubleshooting](#troubleshooting)
16. [Contribution & Roadmap](#contribution--roadmap)
17. [Chinese Quick Guide](#中文快速指引)
18. [License](#license)

---

## Overview

MarketLens is a production-ready, multi-agent research stack designed for real-time equity analysis:

- **Backbone**: FastAPI serves REST + WebSocket interfaces, streams tokens/logs/progress, and persists long-lived sessions.
- **Agents**: LangChain tool-calling agent coordinates Analyst → Researcher → Trader → Risk Manager (plus file I/O utilities).
- **Data Fabric**: Analyst taps real-time news (Finnhub/FMP/AlphaVantage/RSS), fundamentals, Yahoo Finance OHLC, and X/Twitter sentiment via Playwright.
- **Decision Stack**: Researcher runs multi-round bull/bear debates, Trader produces execution cards plus optional Kronos forecasts, and Risk Manager stress-tests every output.
- **Frontend**: React/Vite dashboard handles auth, session management, streaming chat, progress & “thinking” panels, Kronos charts, and configuration toggles.

---

## Feature Highlights

- **End-to-end research workflow** – One prompt triggers data gathering, debate, trading plan, and risk audit with streamed intermediate milestones.
- **Configurable analysis dimensions** – Toggle news/fundamentals/market/sentiment per session; state persists per auth token.
- **Real-time observability** – WebSocket pushes tokens, tool progress, log lines, and redacted chain-of-thought snippets to the UI.
- **Rich data ingestion** – Multi-source news aggregator with caching, fundamentals & insider flow, Yahoo price history + CSV export, X/Twitter sentiment scraping.
- **Actionable execution layer** – Trader agent consumes researcher packets, calls Kronos time-series predictor, emits structured decision cards and chart placeholders.
- **Risk triage** – Optimistic/Neutral/Pessimistic evaluators feed a RiskAggregator to produce JSON reports for human review and downstream automation.
- **Persistent memory** – Conversations, tool decisions, and progress events are stored under `manager/memory_sessions` and resumable across logins.
- **Modern frontend** – Vite + React + SWC build, custom WebSocket hook, ECharts-powered Kronos visualization, markdown rendering with embedded widgets.

---

## System Architecture

```
┌─────────────┐      ┌────────────────────┐      ┌─────────────────────┐
│ React/Vite  │◀────▶│ FastAPI REST (auth │◀────▶│ Memory & User State │
│ Command UI  │ WS   │ + sessions + config│      │ (persistent JSON)   │
└─────▲───────┘      └─────────▲──────────┘      └─────────▲──────────┘
      │                        │                           │
      │ WebSocket tokens/logs  │ invokes                   │
      │                        │                           │
      │                ┌───────┴─────────┐                 │
      │                │ LangChain Main  │────────┐        │
      │ chat/events    │ Agent (Gemini)  │        │        │
      │                └───────┬─────────┘        │        │
      │                        │ tool calls       │        │
      │           ┌────────────┼────────────┐     │        │
      │           │ Analyst / News / Yahoo │ …    │        │
      │           ├────────────┼────────────┤     │        │
      │           │ Researcher Debate Stack│──────┘        │
      │           ├────────────┼────────────┤              │
      │           │ Trader + Kronos        │              │
      │           └────────────┼────────────┘              │
      │                        │                           │
      │                 Risk Manager                       │
      │                        │                           │
      ▼                        ▼                           ▼
Streaming UI          `database/YYYY-MM-DD/<ticker>`   `/assets` static mount
```

---

## Repository Layout

| Path | Description |
| --- | --- |
| `manager/server/app.py` | FastAPI app exposing REST, WebSocket chat, auth, and asset serving. |
| `manager/agent_stream_gradio.py` | LangChain main agent + tool definitions (Analyst/Researcher/Trader/Risk). |
| `manager/memory_manager.py` | Session store, structured history, progress logging. |
| `manager/log_stream.py` & `manager/LOG_SYSTEM_README.md` | Real-time log capture pipeline. |
| `analysts/` | Analyst agent plus data connectors (`news`, `fundamentals`, `yahoo`, `X_search`). |
| `researchers/` | Bullish/Bearish debate tools and moderator synthesizer. |
| `Trader/` | Trader agent, Kronos forecasting stack, sample scripts. |
| `risk_management/` | Multi-perspective evaluators, aggregator, and orchestration utilities. |
| `frontend/` | Vite + React client (sessions, chat, charts, config toggles). |
| `database/` | Timestamped artifacts (market CSV, Kronos outputs, risk reports, caches). |
| `manager/memory_sessions/` | Persistent chat histories & decisions (created at runtime). |
| `scripts/` | Dev utilities such as Kronos asset validator. |

---

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+ (Vite dev server) & npm
- **Playwright Chromium** (for `analysts/lib/X_search`)
- **System deps**: `ffmpeg` (Gradio audio), `libgtk`/`mesa` (Playwright on Linux) as needed
- **API access**:
  - Google AI Studio (Gemini) — `GOOGLE_API_KEY`
  - Optional OpenAI key if you switch models
  - Market data keys: `FINNHUB_KEY`, `FMP_KEY`, `ALPHAVANTAGE_KEY`
  - X/Twitter cookies/state (`analysts/lib/X_search/cookies/…`) for sentiment scraping

Install Playwright browsers once per machine:

```bash
playwright install chromium
```

---

## Environment Variables

Create `.env` in the repo root (already gitignored). Required keys:

| Variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini 2.5 Pro/Flash for agents and tools. |
| `OPENAI_API_KEY` | Optional alternative LLM backend. |
| `FINNHUB_KEY`, `FMP_KEY`, `ALPHAVANTAGE_KEY` | News, fundamentals, insider feeds. |
| `MARKET_LENS_ADMIN_EMAIL`, `MARKET_LENS_ADMIN_PASSWORD` | Default credential for member login. |
| `MARKET_LENS_USERS` | (Optional) JSON map of `{ "email": "password" }` to preload multiple accounts. |
| `GOOGLE_API_KEY` (duplicate) | Ensure exported before running backend processes. |

Frontend `.env` (inside `frontend/`):

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_BASE` | `http://localhost:8000` | REST base URL. |
| `VITE_WS_BASE` | `ws://localhost:8000` | WebSocket base (auto-derives from API). |

> Keep credentials out of commits. Use `direnv`/`dotenv` for local overrides.

---

## Quick Start

1. **Install backend dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium  # sentiment scraper
   ```

2. **Start FastAPI backend**
   ```bash
   export GOOGLE_API_KEY=your_key   # plus other vars or use .env
   uvicorn manager.server.app:app --reload --port 8000
   ```

3. **Install & run frontend**
   ```bash
   cd frontend
   npm install
   npm run dev     # http://localhost:5173 (proxying API/WebSocket)
   ```

4. **(Optional) Legacy Gradio interface**
   ```bash
   python manager/agent_stream_gradio.py
   ```

The React client proxies API calls to `http://localhost:8000` and automatically streams chat from `ws://localhost:8000/ws/chat/<session_id>?token=…`.

---

## Operating the Console

1. **Login / Guest Mode**
   - Use member credentials (`MARKET_LENS_ADMIN_*`) or click *Guest Access* (ephemeral session).
2. **Sessions**
   - Sidebar lists conversations persisted under `manager/memory_sessions`.
   - Create, rename, delete, or activate sessions. Server enforces per-user ownership.
3. **Analysis Config**
   - Toggle News / Fundamentals / Market / Sentiment per token.
   - Config is stored in `USER_STATE` and injected into the main agent prompt.
4. **Streaming Chat**
   - Composer supports Shift+Enter for multi-line prompts.
   - WebSocket events:
     - `token` – incremental answer tokens.
     - `progress` – tool lifecycle updates (start/end/error).
     - `thinking_status` / `thinking_content` – redacted reasoning glimpses.
     - `log` – raw log lines (hidden by default in UI).
     - `final` – full message history update.
5. **Artifacts**
   - Analyst caches data under `database/YYYY-MM-DD/<TICKER>/<intent>/data.json`.
   - Market CSV saved to `database/YYYY-MM-DD/<TICKER>/market_csv/`.
   - Trader + Kronos outputs generate JSON + CSV + chart metadata consumed by `<kronos-chart />` placeholders.
   - Risk manager stores `risk_<TICKER>.json` per request.
   - UI auto-renders Kronos charts when the agent emits `<kronos-chart symbol="NVDA" metadata="/assets/...">`.

---

## Agent & Tooling Pipeline

| Stage | Module | Responsibilities |
| --- | --- | --- |
| **Analyst** | `analysts/analyst.py` + `analysts/lib/*` | Async tools for news, fundamentals, Yahoo quotes, sentiment scraping. Daily caching & CSV generation. |
| **Researcher** | `researchers/manager.py` | Validates analyst payload → multi-round bull/bear debate via `bullish.py`, `bearish.py`, `debate.py`. Returns structured final decision cards. |
| **Trader** | `Trader/trader.py` | LangChain tool that consumes researcher JSON, normalizes into ticker `symbols`, optionally runs Kronos predictions, and emits execution guidance (direction, triggers, stops). |
| **Risk Manager** | `risk_management/orchestrator.py` | Optimistic/Neutral/Pessimistic evaluators executed in parallel, aggregated into confidence, position size, hedging, and follow-up actions. Outputs JSON saved to disk + summary string returned to manager. |
| **Utility Tools** | `read_file`, `write_file` | Agents can reuse artifacts or persist new notes for future turns. Stored under `manager/memory_sessions`. |

### Analyst Data Sources
- **News** (`analysts/lib/news.py`): Finnhub, FMP, AlphaVantage, with RSS fallback and deduplication.
- **Fundamentals** (`analysts/lib/fundamentals.py`): Company profile, metrics, insider trades via FMP/Finnhub.
- **Market** (`analysts/lib/yahoo/yahoo.py`): OHLC, volume, intraday context, CSV export.
- **Sentiment** (`analysts/lib/X_search`): Playwright-based X/Twitter scraping with cookie/state reuse.

### Kronos Forecasting
- Implemented under `Trader/Kronos`.
- `run_kronos_prediction` loads CSV, normalizes schema, feeds Kronos tokenizer/model to forecast `prediction_length` (default 120).
- Metadata saved alongside outputs and rendered via `<kronos-chart />` React component (`frontend/src/components/KronosChart.tsx`) using ECharts + PapaParse.

---

## Frontend Experience

- **Tech stack**: React 18 + TypeScript + Vite + SWC + CSS modules.
- **Hooks**: `useChatWebSocket` manages connection lifecycle, status, and message parsing.
- **Panels**:
  - **Chat** with markdown rendering (`renderMarkdown`) and inline Kronos charts.
  - **Progress timeline** summarizing tool runs (Analyst/Researcher/Trader/Risk).
  - **Thinking panel** showing sanitized reasoning blocks per tool.
  - **Streaming reply** view while final response composes.
- **Sidebar**:
  - User avatar/role.
  - Session list with rename/delete.
  - Analysis configuration toggles with reset.
- **Assets**: Requests to `/assets/...` are served from `database/`, enabling secure download of CSV/JSON results.

Build commands:

```bash
npm run dev         # local dev
npm run build       # production assets
npm run preview     # preview built bundle
```

---

## API Surface

| Method | Path | Description | Auth |
| --- | --- | --- | --- |
| `POST` | `/api/login` | Email/password or guest login. Returns bearer token + active session. | No |
| `POST` | `/api/logout` | Invalidate token. | Yes |
| `GET` | `/api/analysis-config` | Fetch current toggles. | Yes |
| `PUT` | `/api/analysis-config` | Update subset of toggles. | Yes |
| `POST` | `/api/analysis-config/reset` | Restore defaults (news/fundamentals/market/sentiment). | Yes |
| `GET` | `/api/sessions` | List owned sessions with metadata + active state. | Yes |
| `POST` | `/api/sessions` | Create conversation (optional name). | Yes |
| `PUT` | `/api/sessions/{id}` | Rename session. | Yes |
| `DELETE` | `/api/sessions/{id}` | Delete session + history. | Yes |
| `GET` | `/api/sessions/{id}/messages` | Retrieve formatted chat history. | Yes |
| `POST` | `/api/sessions/{id}/activate` | Mark session as active for UI. | Yes |
| `GET` | `/api/sessions/{id}/progress` | Fetch persisted progress timeline. | Yes |
| `WS` | `/ws/chat/{id}?token=…` | Bi-directional chat stream (user→agent, token/progress/log/thinking→client). | Yes |
| `GET` | `/assets/**` | Serve generated CSV/JSON artifacts from `database/`. | Public |

Payload schemas live in `manager/server/app.py` (`LoginRequest`, `AnalysisConfigResponse`, `SessionResponse`, etc.).

---

## Data, Storage & Assets

- **`database/`**
  - `YYYY-MM-DD/<TICKER>/news|fundamentals|market|sentiment/data.json` – analyst cache.
  - `market_csv/*.csv` – Yahoo OHLC exports used by Kronos + downloads.
  - `Kronos_output/` – prediction CSV/plots/metadata (history + forecast).
  - `risk_<TICKER>.json` – aggregated risk report per symbol.
- **`manager/memory_sessions/`**
  - `meta.json` – session IDs, names, owners.
  - `<session>.json` – structured history `{history, decisions, progress}` for UI hydration.
- **Static serving**
  - FastAPI mounts `database/` at `/assets`, enabling the frontend to request files via `http://localhost:8000/assets/...`.

Cleanup tips:
- Stale caches can be removed by deleting dated folders under `database/`.
- `manager/memory_sessions` can be cleared for a fresh slate (do not delete while server runs).

---

## Observability & Logs

- `LogStreamManager` attaches a session-specific queue + logging handler + stdout capture.
- `_forward_logs` in `manager/server/app.py` converts log lines into WebSocket `progress`/`thinking` events and persists them via `MemorySessionManager.append_progress`.
- Queue max size (1000) drops overflow entries to protect long-running jobs.
- Frontend intentionally hides raw `log` events but keeps `progress` timeline aligned with tool templates defined in `PROGRESS_TEMPLATES`.
- For deep dives, consult `manager/LOG_SYSTEM_README.md`.

---

## Testing & Tooling

| Command | Purpose |
| --- | --- |
| `ruff check .` | Lint Python sources (install via `pip install ruff`). |
| `pytest analysts/test/test_analyst.py` | Exercise sentiment tool wrapper & Analyst acceptance helper. |
| `python scripts/test_kronos_assets.py` | Validate Kronos model/tokenizer assets are reachable. |
| `npm run lint` (add as needed) | Integrate ESLint/TypeScript checks (not yet included). |

CI suggestions:
- Add Playwright smoke tests for the WebSocket hook.
- Schedule cron job to refresh X cookies / verify data sources.

---

## Troubleshooting

- **WebSocket immediately closes** → Verify bearer token passed to `/ws/chat/{session_id}`; ensure session ownership matches token.
- **Sentiment scraping fails** → Run `playwright install chromium`, update cookies under `analysts/lib/X_search/cookies/`, or disable `sentiment` toggle.
- **Rate limits / empty news feed** → Provide valid Finnhub/FMP/AlphaVantage keys and monitor API quotas. RSS fallback still provides baseline coverage.
- **Kronos errors** → Confirm CSV contains `open/high/low/close/volume/amount` columns. Use `Trader/example.py` with sample data to validate.
- **No charts in chat** → Ensure agent output contains `<kronos-chart ... />` tag (Trader returns it automatically when Kronos metadata exists) and backend serves `/assets`.
- **Auth issues** → Set `MARKET_LENS_USERS` JSON or default `MARKET_LENS_ADMIN_*`. Guest login skips password but has limited persistence.

---

## Contribution & Roadmap

Short-term ideas:
1. Add CI workflow (lint + pytest + frontend build).
2. Enable multi-symbol batch analysis (extend `StockAnalysisInput`).
3. Persist risk reports to a database (SQLite/Postgres) for querying.
4. Add notification layer (email/Slack) when high-confidence trades or risk breaches occur.
5. Expand frontend with log search/download and CSV viewers.

To contribute:
- Fork or branch, keep changes isolated, run lint/tests, and document UI/UX updates with screenshots/GIFs when relevant.
- Never commit API keys or cookies; rely on `.env` and secrets management.

---

## License

Specify your preferred license (e.g., MIT, Apache-2.0, or proprietary) before making the repository public. Add a `LICENSE` file and update this section accordingly.
