# Contributing to Waveform

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Getting started

### Prerequisites

- Python 3.10+
- A Spotify developer account ([developer.spotify.com/dashboard](https://developer.spotify.com/dashboard))
- A Google Gemini API key ([aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey))

### Development setup

```bash
# Clone and enter the repo
git clone https://github.com/thepixelabs/waveform.git
cd waveform

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install runtime + dev dependencies
make install

# Set up your environment
cp .env.example .env
# Fill in your API keys in .env
```

### Verify your setup

```bash
make check    # Run linter + formatter check + tests
```

## Development workflow

### Common commands

| Command | What it does |
|---------|-------------|
| `make install` | Install all dependencies (runtime + dev) |
| `make lint` | Run ruff linter |
| `make format` | Auto-format code with ruff |
| `make format-check` | Check formatting without changing files |
| `make test` | Run the test suite |
| `make check` | Run lint + format-check + tests (CI equivalent) |
| `make clean` | Remove caches and build artifacts |

### Branch workflow

1. **Fork** the repo and clone your fork
2. **Create a branch** from `main`:
   ```bash
   git checkout -b my-feature
   ```
3. **Make your changes** — keep commits focused and descriptive
4. **Run checks** before pushing:
   ```bash
   make check
   ```
5. **Push** and open a pull request against `main`

### Code style

- We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Run `make format` to auto-fix formatting before committing
- Keep functions focused — if a function does too many things, split it up
- Use descriptive variable names over comments where possible

## What to contribute

### Good first contributions

- Bug fixes with clear reproduction steps
- Improving error messages or terminal UI feedback
- Adding support for new block types
- Better cover art generation options
- Documentation improvements

### Bigger contributions

If you're planning something larger (new features, architectural changes), please **open an issue first** to discuss the approach. This avoids wasted effort if the direction doesn't align with the project.

### Areas we'd love help with

- Test coverage — the project is young and needs more tests
- Internationalization / locale support
- Alternative AI provider support (OpenAI, Claude, etc.)
- Playlist import/export formats

## Pull request guidelines

- **Keep PRs focused** — one feature or fix per PR
- **Describe what and why** in the PR description
- **Include test coverage** for new functionality where practical
- **Don't break existing functionality** — run `make check` before submitting
- **Update documentation** if your change affects user-facing behavior

## Project structure

The app is currently a single file (`create_playlist.py`). If your contribution involves significant new functionality, discuss in an issue whether it warrants splitting into modules.

```
waveform/
├── create_playlist.py          # Main application
├── tests/                      # Test suite
│   ├── __init__.py
│   └── test_create_playlist.py
├── master_prompt.md.example    # AI prompt template
├── blocked_artists.txt.example # Blocked artists template
├── .env.example                # Environment template
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Dev/test dependencies
├── Makefile                    # Dev automation
└── CONTRIBUTING.md             # This file
```

## Reporting bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the [Elastic License 2.0 (ELv2)](LICENSE).

## Questions?

Open an issue — we're happy to help!
