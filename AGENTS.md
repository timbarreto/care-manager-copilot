# Repository Guidelines

## Project Structure & Module Organization
Python sources live at the repo root: `app.py` exposes the Flask API surface and routing, while `fhir_service.py` owns FHIR retrieval plus Azure OpenAI summarization. Front-end assets stay under `static/` (entry point `static/index.html`). Dev container assets are inside `.devcontainer/`, and shared config templates live at `.env.template`. Keep new experiments in clearly named modules beside the existing Python files, and place integration fixtures or mock data under a dedicated `tests/` folder to mirror import paths.

## Build, Test, and Development Commands
Run `pip install -r requirements.txt` after updating dependencies to keep the container image and local virtualenv aligned. Start the API with `python app.py` (defaults to `http://localhost:8000`). Use `pytest` for unit or integration suites, `black .` for formatting, and `pylint app.py fhir_service.py` (extend the list as modules grow) to enforce lint gates before sending a PR.

## Coding Style & Naming Conventions
Follow Python 3.11 conventions with 4‑space indentation, single quotes for short literals, and descriptive snake_case identifiers (`member_id`, `fetch_patient_bundle`). Prefer top-level docstrings plus inline comments only when logic is non-obvious. Keep functions small, return dictionaries with explicit keys, and gate network calls behind helper methods (see `get_fhir_service`). Type hints are encouraged for public methods and complex return values.

## Testing Guidelines
Use `pytest` test modules named `test_<feature>.py` and mirror the package layout so imports stay relative. Mock Azure credentials and HTTP calls with fixtures to avoid live dependencies; assert both success payloads and structured error responses. Aim for meaningful coverage of service boundaries (bundle fetch, summarization prompt shaping, API validation) rather than blanket percentage targets. Run `pytest -q` locally and attach logs when failures happen in CI.

## Commit & Pull Request Guidelines
Recent history shows short, imperative commit messages (e.g., “draft container”). Follow that style: `<scope>: <action>` keeps changelogs skimmable. Each PR should describe motivation, summarize functional changes, list test commands executed (`pytest`, `black`), and link Azure Boards issues or GitHub tickets. Include screenshots or curl transcripts when altering HTTP responses or UI assets, and call out required environment variable updates.

## Security & Configuration Tips
Never commit populated `.env` files; copy `.env.template` and document new keys there. Use `az login` or Managed Identity locally, and prefer `DefaultAzureCredential` wiring for new services. Treat patient IDs as synthetic demo data only—no PHI in fixtures or logs. Rotate Azure OpenAI keys and confirm `FHIR_URL` scopes before sharing a dev build.
