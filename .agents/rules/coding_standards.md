# Coding Standards & Architecture Rules

## 1. Code Style & Formatting
- **Language:** Strictly English for code, comments, variables, and documentation.
- **Formater:** Format code using `black` (line length 100) and sort imports using `isort`.
- **Linting:** Zero violations under `flake8`.

## 2. Type Hinting
- Every function and method must declare return types and parameter types (`typing` / built-in generics).
- Avoid `Any` wherever possible. Use `Protocol`, `TypeVar`, or concrete types.
- Ensure all modules pass `mypy --strict src`.

## 3. Error Handling & Logging
- Use custom, descriptive exceptions derived from `EdgeFrameworkError` for framework failures.
- Never catch raw `Exception` silently without structured logging.
- Emit structured JSON log events via `src.core.logger` with correlation IDs (`request_id`, `device_id`).

## 4. Documentation
- Use Google-style docstrings:
  ```python
  def calculate_backoff(attempt: int, base_delay: float, max_delay: float) -> float:
      """Calculates exponential backoff delay with full jitter.

      Args:
          attempt: The zero-indexed retry attempt count.
          base_delay: The initial delay in seconds.
          max_delay: The upper bound cap for delay in seconds.

      Returns:
          A float representing jittered delay in seconds.
      """
  ```
