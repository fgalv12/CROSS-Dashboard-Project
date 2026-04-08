"""
FAQ Agent — OpenAI Agent SDK wrapper for CROSS Dashboard.
Uses file search against a vector store of CROSS FAQ documents
with jailbreak guardrails.
"""

import asyncio
import os
from agents import (
    Agent,
    FileSearchTool,
    ModelSettings,
    Runner,
    RunConfig,
    TResponseInputItem,
    trace,
)
from agents import OpenAIProvider
from openai import AsyncOpenAI
from openai.types.shared.reasoning import Reasoning
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Vector store file search tool
# ---------------------------------------------------------------------------

file_search = FileSearchTool(
    vector_store_ids=["vs_69c68bc2bdb0819195787f23b7a1a428"]
)


# ---------------------------------------------------------------------------
# Lazy OpenAI client (created after API key is set in env)
# ---------------------------------------------------------------------------

def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# ---------------------------------------------------------------------------
# Guardrails configuration (jailbreak detection only)
# ---------------------------------------------------------------------------

JAILBREAK_GUARDRAILS_CONFIG = {
    "guardrails": [
        {
            "name": "Jailbreak",
            "config": {"model": "gpt-5.4-nano", "confidence_threshold": 0.7},
        }
    ]
}


def _guardrails_has_tripwire(results):
    return any(
        hasattr(r, "tripwire_triggered") and r.tripwire_triggered is True
        for r in (results or [])
    )


def _get_guardrail_safe_text(results, fallback_text):
    for r in (results or []):
        info = getattr(r, "info", None) or {}
        if isinstance(info, dict) and "checked_text" in info:
            return info.get("checked_text") or fallback_text
    pii = next(
        (
            (getattr(r, "info", None) or {})
            for r in (results or [])
            if isinstance(getattr(r, "info", None) or {}, dict)
            and "anonymized_text" in (getattr(r, "info", None) or {})
        ),
        None,
    )
    if isinstance(pii, dict) and "anonymized_text" in pii:
        return pii.get("anonymized_text") or fallback_text
    return fallback_text


# ---------------------------------------------------------------------------
# FAQ Agent definition
# ---------------------------------------------------------------------------

faq_agent = Agent(
    name="FAQ",
    instructions=(
        "You are a helpful assistant who answers user questions about the "
        "CROSS Dashboard (Crisis Response & Operational Statewide Status). "
        "You must answer only using information from the provided documents "
        "in the database you have access to. Do not use outside knowledge or "
        "make assumptions beyond what is found in those documents. If you "
        "cannot find an answer in the documents, say so clearly."
    ),
    model="gpt-5.4-nano",
    tools=[file_search],
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(effort="low"),
    ),
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

GUARDRAIL_BLOCKED_MESSAGE = (
    "I'm sorry, I can't process that request. "
    "Please rephrase your question about the CROSS Dashboard."
)


async def _run_faq_async(
    user_input: str,
    conversation_history: list[TResponseInputItem],
) -> tuple[str, list[TResponseInputItem]]:
    """Run the FAQ agent and return (answer_text, updated_history)."""

    with trace("FAQ Agent - CROSS"):
        # Build input message
        input_message: TResponseInputItem = {
            "role": "user",
            "content": [{"type": "input_text", "text": user_input}],
        }
        conversation_history.append(input_message)

        client = _get_client()

        # Run guardrails on input
        try:
            from guardrails.runtime import (
                instantiate_guardrails,
                load_config_bundle,
                run_guardrails,
            )

            ctx = SimpleNamespace(guardrail_llm=client)
            results = await run_guardrails(
                ctx,
                user_input,
                "text/plain",
                instantiate_guardrails(
                    load_config_bundle(JAILBREAK_GUARDRAILS_CONFIG)
                ),
                suppress_tripwire=True,
                raise_guardrail_errors=True,
            )
            if _guardrails_has_tripwire(results):
                return GUARDRAIL_BLOCKED_MESSAGE, conversation_history
        except ImportError:
            # Guardrails package not installed — skip guardrail check
            pass
        except Exception:
            # Guardrail evaluation failed — proceed without blocking
            pass

        # Run the FAQ agent
        result = await Runner.run(
            faq_agent,
            input=[*conversation_history],
            run_config=RunConfig(
                model_provider=OpenAIProvider(
                    openai_client=client,
                ),
                trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_69c5894620e48190a44ed4cd506b0eb1044980a18decaa4a",
                },
            ),
        )

        # Update conversation history with agent response
        conversation_history.extend(
            [item.to_input_item() for item in result.new_items]
        )

        # Extract text response
        output = result.final_output
        if hasattr(output, "json"):
            answer = output.json()
        elif isinstance(output, str):
            answer = output
        else:
            answer = str(output)

        return answer, conversation_history


def run_faq(
    user_input: str,
    conversation_history: list[TResponseInputItem] | None = None,
) -> tuple[str, list[TResponseInputItem]]:
    """Synchronous wrapper for the FAQ agent.

    Args:
        user_input: The user's question.
        conversation_history: Prior conversation turns (mutated in place).

    Returns:
        (answer_text, updated_conversation_history)
    """
    if conversation_history is None:
        conversation_history = []

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an already-running loop (e.g. Streamlit)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                answer, history = pool.submit(
                    asyncio.run,
                    _run_faq_async(user_input, conversation_history),
                ).result()
        else:
            answer, history = loop.run_until_complete(
                _run_faq_async(user_input, conversation_history)
            )
    except RuntimeError:
        answer, history = asyncio.run(
            _run_faq_async(user_input, conversation_history)
        )

    return answer, history
