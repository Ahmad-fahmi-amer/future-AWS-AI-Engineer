# ── Imports ───────────────────────────────────────────────────────────────────
# These imports are provided. Do not remove them.
import sys
import nest_asyncio2

# Python 3.14 compatibility shim for Strands Browser
sys.modules["nest_asyncio"] = nest_asyncio2
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamable_http_client

import argparse
import asyncio
import boto3
import json
import logging
import os
import uuid

from typing import Dict

from strands.hooks import (
    HookProvider,
    AfterInvocationEvent,
    HookRegistry,
    MessageAddedEvent,
)

from bedrock_agentcore.tools.code_interpreter_client import code_session
from strands_tools.browser import AgentCoreBrowser


# ── System Prompt ─────────────────────────────────────────────────────────────

system_prompt = """
You are a customer support AI agent for an e-commerce platform.

Your job is to help customers with:
- Order tracking and customer order information
- Refunds and returns
- Product information and support policies
- Loyalty program questions and discount calculations
- Current web information when live browsing is required

Tool usage rules:

1. Use the AgentCore Gateway order tools when the customer asks about
   orders, tracking information, or customer order history.

2. Use the AgentCore Gateway refund tools when the customer asks to
   initiate a refund, check refund status, or obtain a return label.

3. Use search_knowledge_base for questions about product specifications,
   return policies, warranty information, loyalty program details,
   and order status definitions.
   Do not invent policy or product information when it can be retrieved
   from the knowledge base.

4. Use calculate_loyalty_discount whenever an exact loyalty discount,
   points redemption, final order total, or points calculation is required.
   Do not perform these calculations yourself when the tool is available.

5. Use the browser tool when the request requires current information
   from a live website.

6. Customer Context may be supplied from long-term memory.
   Use relevant remembered facts and preferences naturally when responding.
   Do not claim to remember information that is not present in the supplied
   context.

General behavior:
- Be concise, accurate, and helpful.
- Never fabricate tool results.
- If required information is missing, ask the customer for it.
- Treat tool outputs and retrieved knowledge as the source of truth for
  backend data and support policies.
- Do not claim that an action succeeded unless the corresponding tool
  confirms success.
- When a tool fails, explain the limitation clearly rather than inventing
  a successful result.
"""


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CSAI_Agent")


# ── TODO 1 — App Initialisation ───────────────────────────────────────────────
# Create a BedrockAgentCoreApp instance.
# This registers the ASGI server for AgentCore deployment.
# There must be exactly one instance per deployment.

app = BedrockAgentCoreApp()


# Suppress interactive tool-consent prompts (required in headless deployments).
os.environ["BYPASS_TOOL_CONSENT"] = "true"


# ── TODO 2 — AWS Configuration ────────────────────────────────────────────────

GATEWAY_URL = (
    "https://customersupportgateway-hybreddxpx.gateway."
    "bedrock-agentcore.us-east-1.amazonaws.com/mcp"
)

KB_ID = "X97GYA9NSI"
REGION = "us-east-1"
MEMORY_ID = "CustomerSupportMemory-y0GiBUFSC2"


# ── TODO 3 — Model + Clients ──────────────────────────────────────────────────

model_id = "global.amazon.nova-2-lite-v1:0"

model = BedrockModel(
    model_id=model_id,
)

memory_client = MemoryClient(
    region_name=REGION,
)

_bedrock_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=REGION,
)


# ── TODO 4 — Memory Namespace Helper ──────────────────────────────────────────

def get_namespaces(
    mem_client: MemoryClient,
    memory_id: str,
) -> Dict:
    """Return a dict mapping strategy type → namespace template string."""

    strategies = mem_client.get_memory_strategies(memory_id)

    return {
        strategy["type"]: strategy["namespaces"][0]
        for strategy in strategies
    }


# ── TODO 5 — Memory Hook ──────────────────────────────────────────────────────

class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id

        # Load namespace templates configured in AgentCore Memory.
        self.namespaces = get_namespaces(
            self.memory_client,
            self.memory_id,
        )

    def retrieve_customer_context(
        self,
        event: MessageAddedEvent,
    ):
        """
        Retrieve relevant memories and prepend them
        to the user message.
        """

        messages = event.agent.messages

        if not messages:
            return

        last_message = messages[-1]

        # Only process user messages.
        if last_message.get("role") != "user":
            return

        content = last_message.get("content", [])

        # Only process plain-text user messages.
        # Tool results must not trigger memory retrieval.
        if not content or not isinstance(content, list):
            return

        text_blocks = [
            block.get("text")
            for block in content
            if isinstance(block, dict) and block.get("text")
        ]

        if not text_blocks:
            return

        user_query = "\n".join(text_blocks)

        memory_context = []

        # Search each configured long-term memory strategy.
        for strategy_type, namespace_template in self.namespaces.items():
            namespace = namespace_template.format(
                actorId=self.actor_id
            )

            memories = self.memory_client.retrieve_memories(
                self.memory_id,
                namespace,
                user_query,
                top_k=5,
            )

            for memory in memories:
                memory_text = (
                    memory
                    .get("content", {})
                    .get("text")
                )

                if memory_text:
                    memory_context.append(
                        f"[{strategy_type}] {memory_text}"
                    )

        # Prepend retrieved context to the current user message.
        if memory_context:
            context_text = "\n".join(memory_context)

            augmented_message = (
                f"Customer Context:\n"
                f"{context_text}\n\n"
                f"{user_query}"
            )

            last_message["content"] = [
                {
                    "text": augmented_message,
                }
            ]

    def save_support_interaction(
        self,
        event: AfterInvocationEvent,
    ):
        """
        Save the completed turn to memory
        after the agent responds.
        """

        messages = event.agent.messages

        customer_query = None
        agent_response = None

        # Walk backwards to find the latest assistant response
        # and latest plain-text user query.
        for message in reversed(messages):
            role = message.get("role")
            content = message.get("content", [])

            if not isinstance(content, list):
                continue

            text_blocks = [
                block.get("text")
                for block in content
                if isinstance(block, dict) and block.get("text")
            ]

            if not text_blocks:
                continue

            text = "\n".join(text_blocks)

            if role == "assistant" and agent_response is None:
                agent_response = text

            elif role == "user" and customer_query is None:
                customer_query = text

            if customer_query and agent_response:
                break

        if not customer_query or not agent_response:
            return

        self.memory_client.create_event(
            self.memory_id,
            self.actor_id,
            self.session_id,
            messages=[
                (customer_query, "USER"),
                (agent_response, "ASSISTANT"),
            ],
        )

    def register_hooks(
        self,
        registry: HookRegistry,
    ) -> None:
        """Register both memory callbacks."""

        registry.add_callback(
            MessageAddedEvent,
            self.retrieve_customer_context,
        )

        registry.add_callback(
            AfterInvocationEvent,
            self.save_support_interaction,
        )


# ── TODO 6 — Knowledge Base Tool ──────────────────────────────────────────────

@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.

    Use this for product specifications, return policies, warranty
    information, loyalty program details, and order status definitions.

    Args:
        query: The question or topic to search for

    Returns:
        Relevant information retrieved from the knowledge base
    """

    # Guard against a missing Knowledge Base configuration.
    if not KB_ID:
        return "Knowledge base not configured."

    # Retrieve relevant chunks from Amazon Bedrock Knowledge Base.
    response = _bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={
            "text": query,
        },
    )

    retrieval_results = response.get(
        "retrievalResults",
        [],
    )

    # No relevant chunks were retrieved.
    if not retrieval_results:
        return (
            "No relevant information found "
            "in the knowledge base."
        )

    # Extract text from each retrieved chunk.
    chunks = []

    for result in retrieval_results:
        text = (
            result
            .get("content", {})
            .get("text")
        )

        if text:
            chunks.append(text)

    if not chunks:
        return (
            "No relevant information found "
            "in the knowledge base."
        )

    # Separate retrieved chunks clearly for the model.
    return "\n---\n".join(chunks)


# ── TODO 7 — Loyalty Discount Tool (Code Interpreter) ────────────────────────

@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter.

    Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:
            Customer's current points balance

        tier:
            Customer tier — Silver, Gold, or Platinum

        order_total:
            Order total in USD

        product_category:
            standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """

    code = f"""
import json
import math

loyalty_points = {loyalty_points}
tier = {tier!r}
order_total = {order_total}
product_category = {product_category!r}

earn_rates = {{
    "standard": 1,
    "device": 2,
    "fresh": 5
}}

tier_rates = {{
    "Silver": 0.00,
    "Gold": 0.10,
    "Platinum": 0.15
}}

# Each point is worth $0.01.
# Redemption must be in increments of 500 points.
# Points may cover at most 50% of the order total.
max_redeemable_points = int(
    (order_total * 0.50) / 0.01
)

points_redeemed = min(
    loyalty_points,
    max_redeemable_points
)

points_redeemed = (
    points_redeemed // 500
) * 500

points_discount = (
    points_redeemed * 0.01
)

subtotal_after_points = max(
    order_total - points_discount,
    0.0
)

tier_rate = tier_rates.get(
    tier,
    0.00
)

tier_discount = (
    subtotal_after_points * tier_rate
)

final_total = max(
    subtotal_after_points - tier_discount,
    0.0
)

total_savings = (
    order_total - final_total
)

earn_rate = earn_rates.get(
    product_category,
    1
)

points_earned = math.floor(
    final_total * earn_rate
)

remaining_points = (
    loyalty_points
    - points_redeemed
    + points_earned
)

result = {{
    "points_redeemed": int(points_redeemed),
    "points_discount": float(round(points_discount, 2)),
    "tier_discount_pct": float(tier_rate),
    "tier_discount": float(round(tier_discount, 2)),
    "final_total": float(round(final_total, 2)),
    "total_savings": float(round(total_savings, 2)),
    "points_earned": int(points_earned),
    "remaining_points": int(remaining_points)
}}

print(json.dumps(result))
"""

    try:
        with code_session(REGION) as session:
            response = session.invoke(
                "executeCode",
                {
                    "code": code,
                    "language": "python",
                    "clearContext": True,
                },
            )

            stream = response.get("stream")

            if stream is None:
                raise RuntimeError(
                    "Code Interpreter returned no result stream."
                )

            for event in stream:
                result = event.get(
                    "result",
                    {},
                )

                if result.get("isError"):
                    raise RuntimeError(
                        result
                        .get("structuredContent", {})
                        .get(
                            "stderr",
                            (
                                "Code Interpreter "
                                "execution failed."
                            ),
                        )
                    )

                content = result.get(
                    "content",
                    [],
                )

                for block in content:
                    if (
                        block.get("type") == "text"
                        and block.get("text")
                    ):
                        return block["text"]

            raise RuntimeError(
                "Code Interpreter returned no text result."
            )

    except Exception as e:
        # Fallback: apply only the tier discount.
        tier_rates = {
            "Silver": 0.00,
            "Gold": 0.10,
            "Platinum": 0.15,
        }

        tier_rate = tier_rates.get(
            tier,
            0.00,
        )

        tier_discount = (
            order_total * tier_rate
        )

        final_total = (
            order_total - tier_discount
        )

        return json.dumps({
            "fallback": True,
            "reason": str(e),
            "tier_discount": round(
                tier_discount,
                2,
            ),
            "final_total": round(
                final_total,
                2,
            ),
        })


# ── TODO 8 — Agent Entrypoint ─────────────────────────────────────────────────

@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required)
          The customer's message

      customer_id (str, optional)
          Unique customer identifier

      session_id  (str, optional)
          Session identifier; generated if absent
    """

    agent_core_browser = None

    try:
        # 1. Extract request data.
        user_input = payload.get(
            "prompt",
            "",
        )

        actor_id = payload.get(
            "customer_id",
            "anonymous",
        )

        session_id = (
            payload.get("session_id")
            or str(uuid.uuid4())
        )

        if not user_input:
            return "A prompt is required."

        # 2. Create long-term memory hook.
        memory_hook = MemoryHook(
            actor_id=actor_id,
            session_id=session_id,
            memory_client=memory_client,
            memory_id=MEMORY_ID,
        )

        # 3. Create AgentCore Browser.
        agent_core_browser = AgentCoreBrowser(
            region=REGION,
        )

        # 4. Start with local tools.
        tools = [
            search_knowledge_base,
            calculate_loyalty_discount,
            agent_core_browser.browser,
        ]

        # 5. Connect to AgentCore Gateway.
        mcp_client = MCPClient(
            lambda: streamable_http_client(
                GATEWAY_URL
            )
        )

        with mcp_client:
            try:
                gateway_tools = mcp_client.list_tools_sync()
                tools.extend(gateway_tools)

                logger.info(
                    "Gateway connected successfully. Loaded %d tools.",
                    len(gateway_tools),
                )

            except TimeoutError:
                logger.exception("Gateway tool loading timed out")
                return (
                    "The order and refund services are temporarily unavailable "
                    "because the Gateway connection timed out. Please try again later."
                )

            except ConnectionError:
                logger.exception("Gateway connection failed")
                return (
                    "The order and refund services are temporarily unavailable. "
                    "Please try again later."
                )

            except Exception:
                logger.exception("Gateway tool loading failed")
                return (
                    "The order and refund services are temporarily unavailable. "
                    "Please try again later."
                )

            # 6. Create the Strands Agent.
            agent = Agent(
                model=model,
                tools=tools,
                hooks=[memory_hook],
                system_prompt=system_prompt,
            )

            # 7. Invoke the agent.
            response = await agent.invoke_async(
                user_input
            )

        # 8. Extract assistant response.
        if (
            response
            and response.message
            and response.message.get("content")
        ):
            first_content = (
                response.message["content"][0]
            )

            if isinstance(
                first_content,
                dict,
            ):
                return first_content.get(
                    "text",
                    str(first_content),
                )

            return str(first_content)

        return "The agent returned no response."

    except Exception:
        # Log internal details, but do not expose them to the user.
        logger.exception("Agent invocation failed")
        return (
            "Unable to process the request due to an internal error. "
            "Please try again later."
        )
    
def main():
    """Run one invocation from the command line for local testing."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "payload",
        type=str,
    )

    args = parser.parse_args()

    response = asyncio.run(
        invoke(
            json.loads(args.payload)
        )
    )

    print(response)


if __name__ == "__main__":
    # main()
    app.run()