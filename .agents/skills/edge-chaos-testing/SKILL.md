---
name: edge-chaos-testing
description: >-
  Runbook and patterns for simulating network disruptions, intermittent connectivity,
  socket drops, latency spikes, and verifying exponential backoff with jitter on edge devices.
---

# Edge Chaos Testing Runbook

Use this skill when designing or debugging network resilience and failure injection test cases.

## Key Principles
1. **Exponential Backoff Formula:**
   $$\text{Delay} = \text{random}(0, \min(\text{max\_delay}, \text{base\_delay} \times 2^{\text{attempt}}))$$
2. **Transient Error Codes:** Validate retries on HTTP 500, 502, 503, 504, and 429. Never retry on deterministic client errors (e.g., 400 Bad Request, 401 Unauthorized without token refresh, 404 Not Found).
3. **Idempotency Verification:** Ensure each retry attempt sends identical `Idempotency-Key` headers so the cloud gateway suppresses duplicate transactions.

## Execution Steps
1. Configure `ChaosEngine` with fault injection parameters (e.g., failure probability `0.6`, error codes `[503, 504]`).
2. Attach the chaos interceptor to the test client session.
3. Trigger an upload operation.
4. Assert:
   - Total attempts equals expected retry count before success (or raises `MaxRetriesExceededError`).
   - Elapsed delay adheres to exponential backoff bounds.
   - Cloud receiver records exactly one processed item despite multiple network attempts.
