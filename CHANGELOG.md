# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-24

### Added

- Initial public release.
- Resilient tiered LLM client with validation-as-pass-condition and explicit
  `LLMError` on exhaustion.
- Multi-agent identity & scope model with alias normalization and a write-time
  scope guardrail.
- Append-only black-box journal with single-active-session policy.
- Freshness sentinel (`FRESH` / `STALE` / `MISSING`).
- Pluggable recall: zero-dependency `LexicalBackend` default plus a Hermes/
  LanceDB reference adapter.
