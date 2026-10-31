---
name: synthetic-payload-generator
description: >-
  Procedures for synthesizing realistic edge sensor payloads, binary telemetry chunks,
  and crafting corrupted, partial, oversized, or out-of-order datasets for stress testing.
---

# Synthetic Payload Generator Runbook

Use this skill when constructing fixtures and test datasets for edge-to-cloud ingestion pipelines.

## Dataset Categories
1. **Valid Edge Telemetry:** JSON payloads compliant with Pydantic schemas (device timestamps, telemetry metrics, battery/network levels).
2. **Corrupted Payloads:** Payloads where the raw content has been flipped or truncated but headers retain the original SHA-256 checksum to test validation gates.
3. **Chunked Binary Streams:** Multi-part file uploads (e.g., sensor raw files, medical imaging metadata) broken into sequence-numbered chunks.
4. **Out-of-Order Chunks:** Chunks emitted with shuffled sequence indices (e.g., `[3, 1, 4, 2]`) to test server-side reassembly queues.
5. **Oversized Payloads:** Data buffers exceeding allowed gateway payload size (e.g., > 10MB) to verify immediate 413 Payload Too Large rejection without memory exhaustion.

## Usage in Tests
Import from `src.generators.payload_factory` or `src.generators.edge_file_generator`:
```python
from src.generators.payload_factory import create_telemetry_batch
from src.generators.edge_file_generator import generate_corrupted_chunk_stream

# Generates 10 out-of-order chunks
chunks = generate_corrupted_chunk_stream(total_chunks=10, out_of_order=True)
```
