"""LangGraph pipeline graph for MenuMate."""
import os
import time
from typing import Any

from langgraph.graph import END, StateGraph

from schema import Output, Profile, Recommendation, RuleTrace, Tokens
from src.critic import run_critic
from src.escalation import (
    ESCALATION_REPLY_EN,
    ESCALATION_REPLY_HI,
    check_escalation_llm,
    check_escalation_regex,
)
from src.extract import extract_profile
from src.filter import MENU, apply_hard_filters
from src.normalize import build_profile, detect_language
from src.rank import rank_and_select
from src.reply import build_clarify_reply, build_template_reply, call_writer_llm
from src.state import MenuState
from src.validate import validate

MAX_LOOPS = 2

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def safety_node(state: MenuState) -> dict:
    message = state["message"]
    language = detect_language(message)

    hit_regex = check_escalation_regex(message)
    source = "regex" if hit_regex else ""

    if not hit_regex:
        hit_llm = check_escalation_llm(message)
        if hit_llm:
            source = "llm"
    else:
        hit_llm = False

    escalation_hit = hit_regex or hit_llm

    return {
        "language": language,
        "escalation_hit": escalation_hit,
        "escalation_source": source,
    }


def profile_node(state: MenuState) -> dict:
    history = state["history"]
    message = state["message"]
    feedback = state.get("feedback", [])
    language = state["language"]

    extraction, tokens = extract_profile(history, message, feedback, language)

    profile, clarify_needed, clarify_question = build_profile(extraction, language)

    return {
        "raw_extraction": extraction,
        "profile": profile,
        "clarify_needed": clarify_needed,
        "clarify_question": clarify_question,
        "tokens": tokens,
    }


def normalize_node(state: MenuState) -> dict:
    # Language may have been set by safety_node; profile already built in profile_node
    # Just re-detect language from message as a pass-through (already done in safety_node)
    return {}


def clarify_gate_node(state: MenuState) -> dict:
    return {}


def menu_filter_node(state: MenuState) -> dict:
    profile = state["profile"]
    eligible, rule_trace = apply_hard_filters(profile)
    return {
        "eligible": eligible,
        "rule_trace": rule_trace,
    }


def rank_node(state: MenuState) -> dict:
    eligible = state["eligible"]
    profile = state["profile"]
    rank_hints = state.get("rank_hints", {})

    picks, scored, trace = rank_and_select(eligible, profile, rank_hints)
    return {
        "picks": picks,
        "scored": scored,
        "rule_trace": trace,
    }


def writer_node(state: MenuState) -> dict:
    picks = state["picks"]
    profile = state["profile"]
    feedback = state.get("feedback", [])
    language = state["language"]

    reply, recommendations, tokens = call_writer_llm(picks, profile, feedback, language)

    if not reply:
        # LLM failed — fall back to template now (grounding validator will handle)
        reply, recommendations = build_template_reply(picks, profile, language)
        return {
            "reply": reply,
            "recommendations": recommendations,
            "tokens": tokens,
            "used_template": True,
        }

    return {
        "reply": reply,
        "recommendations": recommendations,
        "tokens": tokens,
    }


def validator_node(state: MenuState) -> dict:
    recommendations = state.get("recommendations", [])
    picks = state["picks"]
    reply = state["reply"]

    ok, errors = validate(recommendations, picks, reply)
    return {
        "validation_errors": errors,
        "first_attempt_ok": ok and state.get("loops_used", 0) == 0,
    }


def critic_node(state: MenuState) -> dict:
    message = state["message"]
    profile = state["profile"]
    picks = state["picks"]
    eligible = state["eligible"]
    reply = state["reply"]

    ok, source, verdict, tokens = run_critic(message, profile, picks, eligible, reply)

    new_feedback = []
    if not ok and verdict.feedback:
        new_feedback = [{"failure_stage": verdict.failure_stage, "feedback": verdict.feedback}]

    # Update rank_hints from critic
    rank_hints = state.get("rank_hints", {})
    if verdict.feedback and verdict.failure_stage == "rank":
        # Critic suggests better cuisine/type — parse from feedback
        rank_hints = {**rank_hints, "critic_hint": verdict.feedback}

    return {
        "critic_ok": ok,
        "critic_source": source,
        "tokens": tokens,
        "feedback": new_feedback,
        "rank_hints": rank_hints,
    }


def template_node(state: MenuState) -> dict:
    picks = state["picks"]
    profile = state["profile"]
    language = state["language"]

    reply, recommendations = build_template_reply(picks, profile, language)
    return {
        "reply": reply,
        "recommendations": recommendations,
        "used_template": True,
    }


def bump_loop_node(state: MenuState) -> dict:
    return {"loops_used": state.get("loops_used", 0) + 1}


def finalize_node(state: MenuState) -> dict:
    """Build the Output object and store it in state["_output"]."""
    language = state["language"]
    escalation_hit = state.get("escalation_hit", False)
    clarify_needed = state.get("clarify_needed", False)

    # Determine route
    if escalation_hit:
        route = "escalate"
        reply = ESCALATION_REPLY_HI if language == "hi" else ESCALATION_REPLY_EN
        recommendations: list[Recommendation] = []
    elif clarify_needed:
        route = "clarify"
        reply = build_clarify_reply(state.get("clarify_question", ""), language)
        recommendations = []
    else:
        route = "recommend"
        reply = state.get("reply", "")
        recommendations = state.get("recommendations", [])

        # Final safety guard: ensure every recommendation item_id is in eligible
        eligible_ids = {item["id"] for item in state.get("eligible", [])}
        safe_recs = [r for r in recommendations if r.item_id in eligible_ids]
        if len(safe_recs) < len(recommendations):
            # Fall back to template if grounding broke
            picks = state.get("picks", [])
            profile = state["profile"]
            reply, safe_recs = build_template_reply(picks, profile, language)

        recommendations = safe_recs[:3]  # enforce at most 3

    model_name = os.environ.get("LLM_MODEL", "")
    tokens = state.get("tokens", Tokens())
    profile = state.get("profile") or Profile()
    profile.language = language
    profile.escalation = escalation_hit

    output = Output(
        conversation_id=state["conversation_id"],
        route=route,
        profile=profile,
        reply=reply,
        recommendations=recommendations,
        rule_trace=state.get("rule_trace", []),
        latency_ms=0,  # set by run.py
        tokens=tokens,
        model=model_name,
    )

    # Record first_attempt_ok into side meta log
    try:
        from pathlib import Path
        meta_path = Path("results/run_meta.jsonl")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "a", encoding="utf-8") as mf:
            mf.write(json.dumps({
                "conversation_id": state["conversation_id"],
                "first_attempt_ok": state.get("first_attempt_ok", True),
                "loops_used": state.get("loops_used", 0),
                "tokens": tokens.model_dump(),
            }) + "\n")
    except Exception:
        pass

    return {"_output": output}


# ---------------------------------------------------------------------------
# Routers (conditional edge functions)
# ---------------------------------------------------------------------------


def route_safety(state: MenuState) -> str:
    if state.get("escalation_hit"):
        return "escalate"
    return "continue"


def route_clarify(state: MenuState) -> str:
    if state.get("clarify_needed"):
        return "clarify"
    return "continue"


def route_validator(state: MenuState) -> str:
    errors = state.get("validation_errors", [])
    loops = state.get("loops_used", 0)
    if not errors:
        return "pass"
    if loops < MAX_LOOPS:
        return "retry_write"
    return "template"


def route_critic(state: MenuState) -> str:
    if state.get("critic_ok"):
        return "ok"
    loops = state.get("loops_used", 0)
    if loops >= MAX_LOOPS:
        return "template"
    verdict_stage = None
    # Read failure_stage from last feedback entry
    feedback = state.get("feedback", [])
    if feedback:
        verdict_stage = feedback[-1].get("failure_stage")
    if verdict_stage == "extract":
        return "retry_extract"
    elif verdict_stage == "rank":
        return "retry_rank"
    else:
        return "retry_write"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph():
    g = StateGraph(MenuState)

    # Register nodes
    g.add_node("safety_agent", safety_node)
    g.add_node("profile_agent", profile_node)
    g.add_node("normalize", normalize_node)
    g.add_node("clarify_gate", clarify_gate_node)
    g.add_node("menu_filter", menu_filter_node)
    g.add_node("rank_and_select", rank_node)
    g.add_node("writer_agent", writer_node)
    g.add_node("grounding_validator", validator_node)
    g.add_node("fit_critic", critic_node)
    g.add_node("template_reply", template_node)
    g.add_node("finalize", finalize_node)

    # Bump-loop nodes to increment loop counter before retrying
    g.add_node("bump_and_write", bump_loop_node)
    g.add_node("bump_and_rank", bump_loop_node)
    g.add_node("bump_and_extract", bump_loop_node)

    # Entry point
    g.set_entry_point("safety_agent")

    # Safety → escalate or continue
    g.add_conditional_edges(
        "safety_agent",
        route_safety,
        {"escalate": "finalize", "continue": "profile_agent"},
    )

    # Profile → normalize → clarify_gate
    g.add_edge("profile_agent", "normalize")
    g.add_edge("normalize", "clarify_gate")

    # Clarify gate → ask or filter
    g.add_conditional_edges(
        "clarify_gate",
        route_clarify,
        {"clarify": "finalize", "continue": "menu_filter"},
    )

    # Hard filter → rank → write → validate
    g.add_edge("menu_filter", "rank_and_select")
    g.add_edge("rank_and_select", "writer_agent")
    g.add_edge("writer_agent", "grounding_validator")

    # Validator routing
    g.add_conditional_edges(
        "grounding_validator",
        route_validator,
        {
            "pass": "fit_critic",
            "retry_write": "bump_and_write",
            "template": "template_reply",
        },
    )

    # Bump → retry nodes
    g.add_edge("bump_and_write", "writer_agent")
    g.add_edge("bump_and_rank", "rank_and_select")
    g.add_edge("bump_and_extract", "profile_agent")

    # Critic routing
    g.add_conditional_edges(
        "fit_critic",
        route_critic,
        {
            "ok": "finalize",
            "retry_write": "bump_and_write",
            "retry_rank": "bump_and_rank",
            "retry_extract": "bump_and_extract",
            "template": "template_reply",
        },
    )

    # Template → finalize
    g.add_edge("template_reply", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


GRAPH = build_graph()

