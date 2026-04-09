# Agent instructions

This file is the shared entry point for any AI coding assistant working in this repo
(Claude Code, Codex, Cursor, Aider, Gemini CLI, Copilot, etc.). Keep real instructions
here; tool-specific files (`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`)
should just reference this file so guidance stays in one place.

## What this project is

**Waveform** — an AI-powered event playlist designer for Spotify. Desktop Python app.
Users sketch a block schedule, set per-block genre weights, and Gemini AI streams songs
into a card feed for keep/skip/veto curation. Approved tracks land in Spotify as a
playlist with parametric cover art. See `README.md` for the full picture.

Key entry points:
- `waveform/` — application package
- `create_playlist.py` — legacy CLI / reference playlist generation flow
- `landing/index.html` — marketing site (GitHub Pages, single-file, no build step)
- `tests/` — pytest suite (`conftest.py` at repo root)

## Ground rules

- **Python 3.11+.** Dependencies in `requirements.txt` / `requirements-dev.txt`.
- **Tests:** `pytest` from the repo root. Don't mock Spotify or Gemini at the boundary
  when an integration-style test is more truthful.
- **Never commit** `.env`, `song_history.json`, `blocked_artists.txt`,
  `master_prompt.md`, or anything under `venv/`. The `.example` variants are the
  source of truth for shape.
- **Landing page** is a single static `landing/index.html`. No framework, no build
  step. Must work on GitHub Pages and degrade gracefully under `prefers-reduced-motion`.
- **Don't add features, refactors, or "cleanups" that weren't asked for.** Scope
  discipline matters more than polish here.
- **Surgical edits over wholesale rewrites** unless the task genuinely calls for one.

## Running things

```bash
python -m waveform         # run the app
pytest                     # run tests
```

## House style

- Match the existing code's style before reaching for a linter.
- Short, direct commit messages. Describe *why*, not *what*.
- Don't introduce emoji into source files, UI, or docs unless explicitly asked.
- No speculative abstractions, no flags for hypothetical futures, no defensive
  validation at internal boundaries.

## When in doubt

Read `README.md`, `CONTRIBUTING.md`, and the file you're about to edit. Then ask.
