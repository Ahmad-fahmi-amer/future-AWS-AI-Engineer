# Tests, Final Deployment, Submission Evidence, Cleanup

## Test commands given by project instructions

```bash
python tests/test_agent.py task2  # agents, routing, shared state
python tests/test_agent.py task3  # guardrails, runtime after prerequisites
python tests/test_agent.py task4  # AgentCore Memory
python tests/test_agent.py task5  # knowledge bases / parallel retrieval
python tests/test_agent.py task6  # CloudWatch and X-Ray
```

Task 3 instructions say **do not deploy the whole system yet**. Phase 3 creates Knowledge Bases; Phase 4 enables Observability, then execute complete deployment:

```bash
python src/agent_orchestrator.py deploy
python src/agent_orchestrator.py test
python tests/test_agent.py all
```

Also available for local workflow exploration:

```bash
python src/demo.py
python src/agent_orchestrator.py chat
```

**Source update:** The updated starter now provides the previously missing CLI, observability and cleanup helpers, and matches the official test command names. Whether the tests pass or AWS resources work is still **not verified**; no live tests were run when this archive was revised.

## Three required manual scenarios

| Scenario | Expected agent route |
|---|---|
| `I want to return my order ORD-27176` as `CUST-001` | Orchestrator → Inventory → Refund → Communication |
| `What is the return policy for premium customers?` | Orchestrator → Policy (three KB retrievers concurrently) → Communication |
| `How much are 5 items at $29.99 with 10% off?` | Orchestrator → Communication (skip Inventory, Policy, Refund) |

Additional safety validation in Task 3: arithmetic must be allowed, while price negotiation, competitor promotion and legal-threat scenarios must be denied, consistent with guardrail definitions.

## Explicit submission evidence

- Completed `src/agent_orchestrator.py` containing required TODO implementations (Tasks 2,3,4,6).
- Three created and synced Amazon Bedrock Knowledge Bases (Returns, Shipping, Warranty).
- Populated `.env`: KB IDs, AgentCore Runtime ARN, Guardrail ID and a **numbered** version.
- **Screenshot of `python tests/test_agent.py all` showing all tests passed and a score of 120.**
- **Screenshot of X-Ray Service Map**, taken after a live request and showing a **connected** Orchestrator → Worker trace graph, including `PolicyAgent` and `KnowledgeBase` nodes per rubric.

The four-item opening deliverables list omits the all-tests/120 screenshot, but Task 6 final instructions explicitly require it; do not omit.

### X-Ray evidence method

1. Run `python src/agent_orchestrator.py test`; task instructions state each scenario prints an X-Ray trace ID.
2. In AWS Console navigate **CloudWatch → X-Ray traces → Service map** (or X-Ray → Service map).
3. Select **Last 5 minutes** and capture **the entire connected graph**. Instructions note a 30–60 second delay before traces appear.
4. Do not substitute architecture drawings for execution screenshots.

### No unsupported claims

- No uploaded code in this package is a finished implementation; starter contains TODOs.
- AWS resource creation, test outcomes, X-Ray graphs, and score **120** are requirements, **not verified accomplishments**.
- Exact website submission/upload workflow is **not described** in the user-supplied instructions beyond named deliverables and screenshots. Do not invent portal fields or a specific ZIP submission format.

## Resource cleanup (only after submitting evidence)

```bash
python infrastructure/cleanup.py          # dry run, lists planned deletions
python infrastructure/cleanup.py --yes    # performs deletion
```

**Updated starter:** `infrastructure/cleanup.py` is **present** in the newest repository. Its default mode is a dry run; `--yes` performs destructive cleanup. Do not run cleanup until after screenshots and submission, and only in the intended AWS account/region. The course text notes resources could be needed if resubmission is required.
