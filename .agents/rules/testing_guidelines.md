# Testing Guidelines & Quality Rules

## 1. Test Isolation & Scope
- Tests must be completely independent and deterministic. Running tests in any order (or in parallel via `pytest-xdist`) must produce identical results.
- Never write state to shared static class variables without resetting fixtures.
- Clean up any temporary files or mocked network interceptors upon test teardown using `yield` fixtures.

## 2. Test Markers
Group tests logically using custom Pytest markers:
- `@pytest.mark.unit`: Fast, memory-only unit tests (< 50ms).
- `@pytest.mark.integration`: Component boundary verification with mock servers.
- `@pytest.mark.resilience`: Network latency, packet drop, retry, and timeout tests.
- `@pytest.mark.security`: Cryptographic checks, token lifecycles, and tamper detection.
- `@pytest.mark.e2e`: End-to-end device-to-cloud sync pipeline tests.
- `@pytest.mark.bdd`: Gherkin-backed acceptance scenarios (`pytest-bdd`).

## 3. Mocking & Simulating Boundaries
- Do not make external internet requests during test runs.
- Use `unittest.mock`, `pytest-mock`, or our internal `ChaosEngine` / `MockCloudGateway` for all network simulation.
- Verify not only positive response codes (`200 OK`), but also internal retry telemetry, headers (`X-Request-ID`, `Idempotency-Key`), and structured log output.

## 4. Coverage Thresholds
- Maintain minimum test coverage of >= 90% across all modules in `src/`.
- Every edge case (malformed data, out-of-order chunks, expired tokens) must have explicit negative assertions.

