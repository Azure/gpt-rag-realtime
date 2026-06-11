## Engineering Standards

### Clean Code and Modularity

This repository is the **voice / real-time** component of GPT-RAG and is an
early skeleton (no service code yet). Establish clean code best practices from
the start so the service stays modular and easy to evolve as it grows.

- Keep each module and file focused on a single, clear responsibility.
- As code lands, separate concerns into dedicated layers (transport / session
  handling, backend clients/connectors, telemetry, and any real-time audio
  logic) instead of accumulating everything in one entrypoint.
- Prefer small, cohesive `async` functions and classes. Respect async
  correctness — do not block the event loop with synchronous I/O, which is
  especially important for real-time/streaming workloads.
- Use clear, intent-revealing names so the code reads without excessive
  comments. Comment only non-obvious decisions.
- Reuse shared helpers and connectors before adding new ones. Avoid
  duplication and speculative abstractions; extract only when code is
  genuinely repeated or a file is mixing concerns.

### Align with the Other GPT-RAG Services

This service is deployed as an Azure Container App alongside the rest of the
accelerator. Follow the same conventions used by `gpt-rag-orchestrator`,
`gpt-rag-ui`, `gpt-rag-ingestion`, and `gpt-rag-mcp`:

- Read runtime settings from **Azure App Configuration** (label `gpt-rag`) and
  resolve secrets through **Key Vault** references. Never hardcode endpoints,
  deployment names, or feature flags in code.
- Prefer typed, explicit data contracts (type hints, dataclasses, or Pydantic
  models) at every service boundary.
- Surface errors clearly and consistently through a logger. Do not swallow
  exceptions or add silent fallbacks that hide a broken state. Never use
  `print` for diagnostics.
- Add tests alongside logic as soon as it becomes independently testable.
