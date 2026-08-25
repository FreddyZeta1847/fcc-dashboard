# Progress Log

Public, sanitized record of design work. Names the *kind* of decision made, never the decision
itself — see `CLAUDE.md` for the sanitization rule.

- 2026-08-24 — DATE-TIME--architecture: timestamp handling architecture decision
- 2026-08-24 — DATE-TIME--technologies: timestamp storage/parsing technology choices
- 2026-08-24 — DATE-TIME--caching: caching approach for time-based data
- 2026-08-24 — DATE-TIME--security: security boundaries for time/date inputs
- 2026-08-24 — DATE-TIME--resilience: resilience handling for malformed/edge-case timestamps
- 2026-08-24 — PRICING-ENGINE--architecture: cost-calculation architecture decision
- 2026-08-24 — PRICING-ENGINE--technologies: pricing-data technology choices
- 2026-08-24 — PRICING-ENGINE--caching: caching approach for pricing data
- 2026-08-24 — PRICING-ENGINE--security: security approach for external pricing data
- 2026-08-24 — PRICING-ENGINE--resilience: resilience handling for pricing-data failures
- 2026-08-24 — PRICING-ENGINE--price-refresh: price-refresh workflow decision
- 2026-08-24 — cross-review: cross-feature consistency fix (PRICING-ENGINE / DATE-TIME)
- 2026-08-25 — BACKEND--architecture: data-persistence architecture decision
- 2026-08-25 — BACKEND--technologies: backend technology choices
- 2026-08-25 — BACKEND--caching: caching approach for backend data
- 2026-08-25 — BACKEND--security: security approach for the backend API
- 2026-08-25 — BACKEND--resilience: resilience handling for backend failure modes
- 2026-08-25 — BACKEND--collector: log-collection component decision
- 2026-08-25 — BACKEND--api: API surface decision
- 2026-08-25 — BACKEND--process-control: external-process control decision
- 2026-08-25 — cross-review: cross-feature consistency fixes (BACKEND / DATE-TIME / PRICING-ENGINE)
- 2026-08-25 — FRONTEND--architecture: UI structure architecture decision
- 2026-08-25 — FRONTEND--technologies: frontend technology choices
- 2026-08-25 — FRONTEND--caching: caching approach for frontend data
- 2026-08-25 — FRONTEND--security: security approach for the frontend UI
- 2026-08-25 — FRONTEND--resilience: resilience handling for frontend failure states
- 2026-08-25 — FRONTEND--overview: overview page component decision
- 2026-08-25 — FRONTEND--usage: usage page component decision
- 2026-08-25 — FRONTEND--settings: settings page component decision
- 2026-08-25 — FRONTEND--database: database page component decision
- 2026-08-25 — cross-review: cross-feature consistency fixes (FRONTEND / DATE-TIME / PRICING-ENGINE / BACKEND)
- 2026-08-25 — project breakdown: all 4 planned features now fully documented
- 2026-08-25 — PHASE-0-SCAFFOLDING: implementation phase complete
- 2026-08-25 — PHASE-1-CORE-UTILITIES: implementation phase complete
- 2026-08-25 — DATE-TIME--technologies: dependency-list revision (timezone tooling gap found in review)
- 2026-08-25 — PHASE-2-PERSISTENCE-COLLECTOR: implementation phase complete
- 2026-08-25 — BACKEND--architecture: persistence schema revision (resilience gap found in review)
- 2026-08-25 — BACKEND--resilience: failure-detection rule revision (same review)
- 2026-08-25 — PHASE-3-API: implementation phase complete
- 2026-08-25 — BACKEND--api: pricing-endpoint validation revision (config-robustness gap found in review)
- 2026-08-25 — PHASE-4-PROCESS-CONTROL: implementation phase complete
- 2026-08-25 — BACKEND--process-control: process-identity verification revision (safety gap found in final review)
- 2026-08-25 — BACKEND--architecture: process-tracking schema revision (same review)
