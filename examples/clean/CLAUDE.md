# Acme API — agent instructions

<!-- why: the full suite is the only gate that catches cross-service regressions -->
- Always run the full test suite before committing.

<!-- why: deploy.sh is the only script that also migrates the database -->
- Deploy with `./scripts/deploy.sh` only after CI is green.
