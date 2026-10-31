# Edge-to-Cloud Test Automation Framework: Agent Guidelines

Welcome to the **Edge-to-Cloud Test Automation Framework** workspace. This repository contains an enterprise-grade Python test automation framework designed for mission-critical, failure-prone, and intermittently connected edge-to-cloud environments.

## Core Directives

1. **Language Requirement:** All code, comments, docstrings, commit messages, and documentation must be written in **100% English**.
2. **Neutral & Vendor-Agnostic:** Keep the project completely generic and enterprise-focused. Strictly avoid referencing any specific recruiting agency, vendor, or proprietary entity.
3. **Strict Python Standards:**
   - Target Python 3.10+.
   - Enforce type annotations on all public functions, classes, and methods (`mypy` strict compliance).
   - Follow Google-style Python docstrings for all classes, methods, and modules.
4. **Resilience & Non-Flakiness:**
   - Tests must run deterministically inside containerized CI/CD environments.
   - Never rely on uncontrollable external network connections. Use simulated network faults, side-effects, and deterministic boundaries.
5. **Security & Cryptography:**
   - Always validate data integrity using cryptographic checksums (SHA-256) and authenticated encryption (AES-256-GCM).
   - Never hardcode API keys, client secrets, or private tokens; use environment configuration fixtures.

## Workspace Customizations

- `.agents/rules/coding_standards.md`: Code formatting, static typing, and exception handling principles.
- `.agents/rules/testing_guidelines.md`: Test naming conventions, fixture isolation, and assertion practices.
- `.agents/skills/`: Procedural runbooks for chaos simulation, synthetic dataset generation, security validation, and test flake debugging.

