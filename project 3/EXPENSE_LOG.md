# Expense log — NovaMart

User-approved estimate: **$3–$8**, review stop at estimated **$10**, overall training budget **$25**. This is an operational limit, not an enforced AWS billing cap. No unlimited inference, provisioned throughput or OpenSearch was created.

| Operation | Actual scope | Result |
|---|---|---|
| Read-only identity, inventory, quota/IAM/schema checks | novamart-dev/us-east-1; no secrets printed | completed |
| Foundation and policy data | 3 on-demand tables, 6 policy files, S3 Vectors bucket + 3 indexes, scoped roles/log group | deployed |
| KB creation/embedding sync | 3 self-managed Titan v2 KBs, one data source each | COMPLETE |
| Runtime | one CodeZip/PUBLIC/HTTP runtime via CLI/CDK; retries followed concrete permission fixes | READY; current version 3 |
| Guardrail and Memory | version 1 guardrail; one seven-day summary memory | READY/ACTIVE |
| Actual application tests | local AWS scenarios; 5-runtime-turn integration; targeted policy regression; bounded safety/isolation/idempotency probes; official evaluations | verified; no unbounded retry loop |
| Telemetry | CloudWatch INFO and Transaction Search at 100% indexing; real trace reads | verified |
| Cleanup | exact project inventory dry-run only | no working resources deleted |

## Latest available usage snapshot

Snapshot time (UTC): 2026-10-21T21:42:42.616498+00:00

Observed Bedrock model metrics over the preceding six hours:

- us.anthropic.claude-haiku-4-5-20251001-v1:0: input=50934, output=5017, invocations=32
- us.anthropic.claude-sonnet-4-5-20250929-v1:0: input=69462, output=10359, invocations=64

Conservative arithmetic for observed inference: **$0.6371**. This uses deliberately conservative budget assumptions of $2/$10 per million Haiku input/output tokens and $4/$20 Sonnet tokens, not claimed AWS list prices or an invoice. It excludes guardrails, memory, embedding, runtime, storage and telemetry and can lag the latest requests.

Cost Explorer still reported an estimated month total of **$0.0004** at collection. Billing delay means this is not the actual complete project cost or remaining Udacity credit. No claim of exact total spend is made. See `starter/evidence/cost-usage-snapshot.json` for the real API-derived counters and limitations.

Current bounded test volume remains within the approved planning envelope; no additional paid tests are needed for screenshots. Remaining screenshot and archive work is local/Console work. Resources were retained for evidence/review. Storage, memory and logs can continue accruing charges; use the scoped cleanup runbook after submission. Shared bootstrap and Transaction Search settings are retained unless separately reviewed for cleanup.

- 2026-10-22 10:41 UTC: one user-authorized deployed policy invocation to refresh expired screenshot window. Exactly one attempt, no automatic invocation retries; additional operations were read-only STS/runtime/observability queries. No redeployment or extra official evaluation. Incremental billed cost not yet measured; do not treat prior estimates as a live Udacity balance.
