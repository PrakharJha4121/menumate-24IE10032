"""MenuMate pipeline entry point."""
import time

from schema import Output, Profile, Tokens
from src.escalation import (
    ESCALATION_REPLY_EN,
    ESCALATION_REPLY_HI,
    check_escalation_regex,
)
from src.graph import GRAPH


def respond(conversation_id: str, history: list[dict], message: str) -> Output:
    """Return the assistant's output for the customer's latest message.

    history: earlier turns, each {"role": "user" | "assistant", "text": str}
    message: the customer's latest message
    """
    state = {
        "conversation_id": conversation_id,
        "history": history,
        "message": message,
        "language": "en",
        "escalation_hit": False,
        "escalation_source": "",
        "raw_extraction": {},
        "profile": Profile(),
        "clarify_needed": False,
        "clarify_question": "",
        "eligible": [],
        "rule_trace": [],
        "scored": [],
        "picks": [],
        "rank_hints": {},
        "reply": "",
        "recommendations": [],
        "validation_errors": [],
        "first_attempt_ok": False,
        "critic_ok": False,
        "critic_source": "",
        "used_template": False,
        "feedback": [],
        "loops_used": 0,
        "route": "recommend",
        "tokens": Tokens(),
        "llm_errors": [],
        "t_start": time.time(),
        "_output": None,
    }
    result = GRAPH.invoke(state)
    return result["_output"]
