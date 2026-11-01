"""Output schema for MenuMate. Do not rename these fields: reviewers grade them automatically.

You may ADD fields to Profile (extra fields are kept), but keep every field below with the same name and meaning.
Graded profile fields: diet, allergies, party_size, budget_inr, max_wait_min, spice_tolerance, language.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Allergen = Literal["peanut", "tree_nut", "dairy", "gluten", "egg", "soy", "sesame", "shellfish", "fish", "mustard"]
Route = Literal["recommend", "clarify", "escalate"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")

    craving: Optional[str] = None                      # free text, e.g. "spicy Thai main"
    party_size: Optional[int] = None
    budget_inr: Optional[int] = None                   # total for the order
    max_wait_min: Optional[int] = None                 # how soon the food is needed
    diet: Optional[Literal["veg", "egg", "non-veg", "jain"]] = None
    allergies: list[Allergen] = Field(default_factory=list)
    spice_tolerance: Optional[Literal["mild", "medium", "hot"]] = None
    avoid_ingredients: list[str] = Field(default_factory=list)
    language: Literal["en", "hi", "hinglish"] = "en"   # hi = Devanagari script, hinglish = Hindi in Latin script
    escalation: bool = False


class Recommendation(BaseModel):
    item_id: str
    reason: str
    cited_fields: list[str] = Field(default_factory=list)   # menu.json field names the reason relies on


class RuleTrace(BaseModel):
    rule_id: str                                       # e.g. "P-03"
    item_id: Optional[str] = None                      # None for conversation-level rules (P-01, P-02)
    outcome: Literal["exclude", "penalize", "pass"]
    detail: Optional[str] = None


class Tokens(BaseModel):
    prompt: int = 0
    completion: int = 0


class Output(BaseModel):
    conversation_id: str
    route: Route
    profile: Profile
    reply: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    rule_trace: list[RuleTrace] = Field(default_factory=list)
    latency_ms: int = 0
    tokens: Tokens = Field(default_factory=Tokens)
    model: str = ""

    @field_validator("recommendations")
    @classmethod
    def at_most_three(cls, v):
        if len(v) > 3:
            raise ValueError("at most 3 recommendations")
        return v
