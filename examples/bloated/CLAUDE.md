# Acme API — agent instructions

## Workflow

- Always run the full test suite before committing changes.
- Always run the full test suite before you commit any changes.
- Never run the full test suite before committing.

## Deploy

- Run `scripts/migrate.sh` before every deploy.
- Deploy with `./scripts/deploy.sh` only after CI is green.

## Style

<!-- why: the legacy parser crashes on tabs -->
- Use spaces for indentation.

- Use spaces for indentation in Python files.
- Use spaces, not tabs, for indentation in Python files.

- Prefer tabs in Makefiles.
