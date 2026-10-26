# CLAUDE.md: Wind Forecast Buffer Tool

Persistent brief for this project. Source of truth for the task: `docs/ASSIGNMENT.md`. Read it when scope is unclear.

## 1. Product goal
- Web app for the day-ahead power buying team of a UK utility.
- (a) Show the latest wind forecast that was actually available at decision time, per hourly slot (WINDFOR is hourly; see D-003).
- (b) Quantify forecast error (vs actual wind) so the team can size a procurement buffer.

## 2. Hard constraints
- Frontend: React (TypeScript). Backend: Python with FastAPI. Docker for local/dev runs.
- Deployed on Vercel (public URL goes in the README).
- Data ONLY from Elexon BMRS: `FUELHH` (filter `fuelType=WIND`) for actuals, `WINDFOR` for forecasts. No other data sources.
- Scope: purchase decisions made in January 2026 (see section 4).
- Total budget: 16 hours. Prefer a small, correct, well-explained v1 over breadth.
- Deliverables beyond code: public repo with an anonymous name, README (file/dir guide, how to start, Vercel link, explicit mention of AI tool use), and a <=10 min video (5 min client pitch + 5 min tech-lead walkthrough).

## 3. Core domain rule (most important)
For each target slot T (`startTime`; hourly, per D-003), the "forecast available at decision time" is the forecast row with the LATEST `publishTime` that is `<= decision cutoff for T`.
- NEVER use a forecast with `publishTime > cutoff`. That is lookahead bias and invalidates every error metric.
- If no forecast exists at or before the cutoff, the slot has no forecast: report it as missing. Do not fall back to a later one.
- Ties on `publishTime` for the same slot: pick deterministically and document it in `docs/DECISIONS.md`.
- Implemented as a pure function, with unit tests that must cover:
  - a forecast published after the cutoff is ignored, even if it is the only newer one
  - a forecast published exactly at the cutoff is included (`<=`)
  - the latest of several eligible forecasts wins
  - no eligible forecast gives a missing result
  - DST changes (Europe/London clock changes) do not shift the cutoff incorrectly
- The decision cutoff rule (D-1 clock time, in which timezone) is configurable. Do not hardcode a guess: pick a default, justify it, and record it in `docs/DECISIONS.md`.

## 4. Scope ambiguity
"Decisions made in January 2026" is ambiguous. Default interpretation: decisions are made on D-1, so delivery days run from 2 Jan 2026 to 1 Feb 2026 inclusive.
- Make the delivery date range configurable (config/env, and a UI/API parameter within sensible bounds).
- Record the interpretation and the alternative (delivery days 1 to 31 Jan) in `docs/DECISIONS.md`.
- Fetch window must be wide enough to include forecasts published before the first cutoff.

## 5. Conventions
- All timestamps stored and computed in UTC. Display in Europe/London only at the UI edge.
- Power in MW.
- Error = forecast - actual. Positive = over-forecast = less wind than expected, so the utility is short and must buy more. Negative = under-forecast = surplus.
- Report at least: bias (mean error), MAE, RMSE, and error percentiles. The buffer suggestion must be framed around the positive-error tail, and must state its method and its limits.
- Use the same sign convention in code, API, charts, and docs. Label axes and units.

## 6. Engineering rules
- Typed code: pydantic models in the backend, strict TypeScript in the frontend. No `Any` / `any` without a comment.
- Domain logic (selection, alignment, metrics) = pure functions with no I/O. HTTP, caching, and parsing sit at the edges.
- Tests: pytest (backend), vitest (frontend). Test domain logic first. Use small fixtures, not live API calls.
- Lint/format: ruff (Python), eslint (TS). CI in `.github/workflows/` runs lint + tests.
- Small, focused commits with clear messages. Never commit to a broken state.
- No secrets in the repo. Use env vars and `.env.example`. Check whether the BMRS endpoints need a key before assuming either way.
- No guessed API parameters. Read the Elexon API docs for exact endpoint paths, parameter names, date formats, and limits, and write what you verified into `docs/`. If unsure, say so and check.
- Handle API pagination, rate limits, empty responses, and duplicate rows explicitly.
- Cache fetched data under `data/` (raw and processed) so the deployed app does not depend on live API availability.
- Decisions and trade-offs go in `docs/DECISIONS.md` as they are made.

## 7. Repo layout plan
```
backend/              FastAPI app, domain/ (pure fns), clients/, schemas/, tests/
frontend/             React + TS app, components/, api/, tests (vitest)
data/                 cached raw + processed BMRS data (small, committed if size allows)
docs/                 ASSIGNMENT.md, DECISIONS.md, API notes, analysis notes
scripts/              data fetch/refresh and one-off tooling
docker-compose.yml    local dev: backend + frontend
.github/workflows/    CI: ruff, pytest, eslint, vitest
README.md             file guide, how to start, Vercel link, AI usage disclosure
CLAUDE.md             this file
```

## 8. Working agreement
- Start with `docs/DECISIONS.md` and the data fetch + selection logic (with tests), then metrics, then API, then UI, then deploy.
- Do not add features outside the two goals in section 1.
- When requirements are ambiguous, take the simplest sensible default, make it configurable, and document it.
