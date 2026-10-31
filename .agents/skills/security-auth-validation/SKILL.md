---
name: security-auth-validation
description: >-
  Procedures for validating OAuth2/JWT token flows, proactive refresh mechanisms,
  unauthorized credential handling, and cryptographic integrity verification (AES-GCM / SHA-256).
---

# Security & Authentication Validation Runbook

Use this skill when developing or reviewing tests covering security controls, authentication handshakes, and cryptographic verification.

## Testing Checkpoints

### 1. OAuth2 Token Lifecycle
- **Acquisition:** Device exchanges client ID and client secret for an access token via `/oauth/token`.
- **Proactive Refresh:** Device refreshes token before the expiration window (e.g., within 30 seconds of TTL expiry) without dropping active requests.
- **Reactive Refresh (401 Challenge):** When an access token is revoked on the cloud, client receives HTTP 401, flushes cached token, requests a new token, and retries the request seamlessly.
- **Rejection of Revoked/Malformed Credentials:** Requests with invalid signatures, expired timestamps, or tampered JWT payloads must fail immediately with HTTP 401/403.

### 2. Cryptographic Integrity (AES-256-GCM & SHA-256)
- **At-Rest & In-Flight Protection:** Payloads encrypted with AES-256-GCM include an initialization vector (IV) and a 16-byte authentication tag.
- **Tamper Detection:** Modifying even a single bit of ciphertext or associated data must cause decryption failure (`InvalidTag`).
- **Checksum Verification:** Cloud gateway recomputes SHA-256 checksum and compares it against `X-Payload-SHA256` header in constant time.
