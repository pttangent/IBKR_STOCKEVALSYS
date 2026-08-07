# Evidence policy

## Labels

- `fact`: directly reported by a primary or trusted source.
- `company_claim`: management/company statement not independently verified.
- `street_estimate`: consensus or third-party forecast.
- `model_derived`: deterministic calculation from sourced inputs.
- `inference`: analyst interpretation.
- `assumption`: explicit scenario or modeling assumption.
- `needs_source`: material field missing or unverified.

## Freshness

Always show market-data timestamp and filing period. Flag prices or quotes without timestamps, stale/delayed quotes, post-earnings estimates that have not been refreshed, and macro/commodity inputs that predate a material event.

## Conflicts

Prefer primary filings for historicals, the latest approved estimate source for forward data, and the user-provided model only as `user_assumption` or `model_derived`. Do not average conflicting facts; show the conflict and its impact.

## Confidence

`high` means recent primary or multiple trusted sources; `medium` means credible but partial/indirect; `low` means stale, thin, or assumption-heavy. Evidence confidence is separate from underwriting status.
