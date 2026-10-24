# Official Project Brief — Overview and Deliverables

## Introduction

You are an **Enterprise AI Solutions Architect** at **NovaMart**, a fictional e-commerce company. The customer-support team handles thousands of daily inquiries (order status, returns/refunds, policy questions). Existing manual order lookups, policy checks, and customer response drafting are slow, inconsistent, and error-prone.

## Challenge

Build an AI layer that understands customer requests, gathers information from multiple sources, applies company policy, routes requests to specialist agents, composes a professional customer-facing response, enforces enterprise guardrails, and exposes decisions for operational tracing.

## Required product

A production-grade **multi-agent customer-support system** using **Amazon Bedrock AgentCore** and **Strands Agents SDK**, following an **Orchestrator → Workers** hierarchy:

1. **Orchestrator Agent:** intent routing and shared WorkflowState coordination.
2. **Inventory Agent:** order and customer facts from DynamoDB.
3. **Policy Agent:** parallel multi-agent RAG across 3 policy Knowledge Bases.
4. **Refund Agent:** return/refund eligibility decision and processing based on customer tier and policy.
5. **Communication Agent:** final customer-facing message.

Additional platform elements: AgentCore Runtime, Bedrock Guardrails, session memory, CloudWatch/X-Ray observability, shared DynamoDB WorkflowState with optimistic locking.

## Deliverables explicitly specified in user-provided project text

1. Completed **`src/agent_orchestrator.py`** with TODOs for **Tasks 2, 3, 4, 6**.
2. **Three Bedrock Knowledge Bases** in AWS Console, each with synchronized data sources (**Task 5**).
3. **Populated `.env`** containing Knowledge Base IDs, deployed AgentCore Runtime ARN, and Guardrail configuration.
4. **Screenshot of X-Ray Service Map** demonstrating an end-to-end Orchestrator → Workers trace.
5. **Screenshot of successful full test results showing all tests passed and score 120**, as explicitly required in the final-phase instructions (the opening deliverables list mentions only the four items above).

**Scope distinction:** Instructions in the 'Suggestions to Make Your Project Stand Out' section of the rubric are **optional** and are not mandatory grading requirements. See `07_EVALUATION_RUBRIC.md`.

**Unverified:** This package contains no live AWS account state, populated `.env`, test evidence, runtime ARN or real screenshots of execution. The provided images are design diagrams, not the required X-Ray/testing evidence.
