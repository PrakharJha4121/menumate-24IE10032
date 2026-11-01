"""LangGraph state definition for MenuMate pipeline."""
import operator
from typing import Annotated, Any, Optional, TypedDict

from schema import Profile, Recommendation, RuleTrace, Tokens


def merge_tokens(a: Tokens, b: Tokens) -> Tokens:
    return Tokens(prompt=a.prompt + b.prompt, completion=a.completion + b.completion)


class MenuState(TypedDict):
    conversation_id: str
    history: list[dict]
    message: str
    language: str
    escalation_hit: bool
    escalation_source: str
    raw_extraction: dict
    profile: Profile
    clarify_needed: bool
    clarify_question: str
    eligible: list[dict]
    rule_trace: Annotated[list, operator.add]
    scored: list[dict]
    picks: list[dict]
    rank_hints: dict
    reply: str
    recommendations: list[Recommendation]
    validation_errors: list[str]
    first_attempt_ok: bool
    critic_ok: bool
    critic_source: str
    used_template: bool
    feedback: Annotated[list[dict], operator.add]
    loops_used: int
    route: str
    tokens: Annotated[Tokens, merge_tokens]
    llm_errors: Annotated[list, operator.add]
    t_start: float
    # finalize stores the Output object here
    _output: Optional[Any]

