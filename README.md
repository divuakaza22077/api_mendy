# API-Mend implementation

Repository: https://github.com/divuakaza22077/api_mendy

## Architecture

**Python Brain, Rust Muscles.**

- Python owns FastAPI orchestration, Pydantic contracts, GitHub REST, deterministic scenario flow, and future LLM calls.
- Rust-backed `ast-grep-py` owns static call-site matching.
- `ruff` validates Python target files through subprocess.
- `oxlint` validates JavaScript/TypeScript target files through subprocess when installed.
- No custom pure-Python AST parser is used.

## Install backend tools

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
npm install
```

Python 3.12 is the intended production runtime. The current workstation must be checked before deployment.

Set `GITHUB_TOKEN` in the shell or a local `.env` file copied from `.env.example`. Never commit the token. The implementation uses it only from the Python backend for `/github/access`, repository scanning, and explicit non-dry-run shipping.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

## Verify

```powershell
pytest -q
ruff check backend tests
```

GitHub Actions runs the same Python checks plus `npm ci` and Oxlint verification on every push and pull request.
