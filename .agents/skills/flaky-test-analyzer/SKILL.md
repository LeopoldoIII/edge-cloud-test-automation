---
name: flaky-test-analyzer
description: >-
  Systematic guide for identifying, diagnosing, and resolving non-deterministic
  or flaky test failures in edge-to-cloud automated test suites.
---

# Flaky Test Diagnostics Runbook

Use this skill when investigating inconsistent test outcomes or race conditions in parallel test execution.

## Common Root Causes in Edge-to-Cloud Testing

1. **Unbounded Asynchronous Delays:**
   - *Symptom:* Test fails intermittently in CI/CD when CPU load is high.
   - *Fix:* Replace arbitrary `time.sleep()` calls with polling loops and timeout thresholds (`wait_until(condition, timeout=5.0)`).
2. **Shared State Leakage:**
   - *Symptom:* Test passes in isolation but fails when run as part of the full suite or under `pytest-xdist`.
   - *Fix:* Ensure all fixtures scope to `function` unless purely stateless. Reset singleton or class-level registries in fixture teardown.
3. **Pseudo-Random Seeds & Timing Jitter:**
   - *Symptom:* Exponential backoff assertions fail if jitter happens to produce an edge boundary.
   - *Fix:* Inject a deterministic pseudo-random generator or mock the jitter function (`random.uniform`) when asserting strict mathematical bounds.
4. **Unclosed Sockets / Leaked Coroutines:**
   - *Symptom:* `ResourceWarning: unclosed transport` or lingering background threads.
   - *Fix:* Explicitly close client sessions in `yield` fixture teardown blocks.
