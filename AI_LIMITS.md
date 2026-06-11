# AI limits policy

This file documents the human-readable limits policy. The backend reads
`api/config/ai_limits.yml`; do not make the backend parse this Markdown file.

## Cerebras

Source: official Cerebras inference docs checked on 2026-06-10.

Free Trial values currently configured:

| Model | Requests/min | Tokens/min | Tokens/hour | Tokens/day |
| --- | ---: | ---: | ---: | ---: |
| `zai-glm-4.7` | 5 | 30,000 | 1,000,000 | 1,000,000 |
| `gpt-oss-120b` | 5 | 30,000 | 1,000,000 | 1,000,000 |

The backend also records Cerebras response headers such as
`x-ratelimit-limit-tokens-minute`, `x-ratelimit-remaining-tokens-minute`, and
`x-ratelimit-reset-tokens-minute`. Those headers are treated as live telemetry
because account/org limits can differ from the public docs.

## NVIDIA

The NVIDIA free model catalog is discovered once per week by the backend and
stored in `ConfiguracionSistema` under `nvidia_free_models`. Rate limits are not
assumed globally because they can depend on the account/key.

## Gemini and Groq

Gemini and Groq limits are account/model/tier dependent. The backend keeps the
providers in the shared limits config so future hard limits can be added without
changing call sites.
