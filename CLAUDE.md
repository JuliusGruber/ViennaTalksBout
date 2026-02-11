# CLAUDE.md

## Testing

When asked to "run tests" or "run the tests", always run **all** tests including integration tests. Do not exclude any test markers.

```bash
python -m pytest tests/ -v --tb=short --cov=viennatalksbout --cov-report=term-missing
```

Integration tests are marked with `@pytest.mark.integration` and make real HTTP calls to external services (e.g. wien.rocks). They require network access.

To run only unit tests (excluding integration): `python -m pytest tests/ -m "not integration"`
To run only integration tests: `python -m pytest tests/ -m "integration"`
