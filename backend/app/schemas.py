from typing import Literal, Optional

from pydantic import BaseModel, Field

# From the "Upwork Proposal Hooks" doc. The doc's "written by a human / took me 20 minutes" hooks are NOT
# default: an AI draft would make those claims untrue. Add them yourself only if you rewrite each proposal.
DEFAULT_HOOKS = [
    "Let's make this the last proposal you need to read today. I have attached a work sample that matches what you're looking for.",
    "I believe a good proposal should make sense, not noise. So let's get straight to the point.",
    "If you are tired of long explanations, you will love how simple I make it.",
]
DEFAULT_BANNED = ["tailored", "deliver", "ensuring", "embrace", "data-driven"]


class ScrapedJob(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    raw_text: str = ""
    activity_text: str = ""
    client_text: str = ""
    skills: list[str] = Field(default_factory=list)
    country: str = ""
    page_type: str = "job"
    scraped_at: Optional[str] = None


class Profile(BaseModel):
    name: str = ""
    title: str = ""
    country: str = ""
    years_experience: Optional[int] = None
    hourly_rate: Optional[float] = None
    min_fixed_budget: float = 0
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    niche: str = ""
    past_projects: list[str] = Field(default_factory=list)
    case_study_links: list[str] = Field(default_factory=list)
    portfolio_links: list[str] = Field(default_factory=list)
    preferred_countries: list[str] = Field(default_factory=lambda: ["United States"])
    tone_notes: str = ""
    signature: str = ""
    hooks: list[str] = Field(default_factory=lambda: list(DEFAULT_HOOKS))
    banned_words: list[str] = Field(default_factory=lambda: list(DEFAULT_BANNED))


class AnalyzeRequest(BaseModel):
    job: ScrapedJob
    profile: Profile
    deep_research: bool = True


class ProposalRequest(BaseModel):
    profile: Profile
    extra_instructions: str = ""
    deep_research: bool = False


class OutcomeRequest(BaseModel):
    status: Literal["analyzed", "skipped", "applied", "interviewing", "hired", "rejected", "no_response"]
    notes: str = ""
    connects_spent: Optional[int] = None


# ---- LLM structured outputs ----
class Analysis(BaseModel):
    verdict: Literal["APPLY", "MAYBE", "SKIP"]
    confidence: int = Field(description="0-100 confidence in the verdict")
    profile_fit: int = Field(description="0-100 how well the freelancer's profile matches the job")
    response_chance: int = Field(description="0-100 chance the client replies if applying now")
    win_chance: int = Field(description="0-100 chance of being hired")
    summary: str = Field(description="2-3 sentence plain-language recommendation")
    reasons_apply: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    best_angle: str = Field(default="", description="How to pitch this job, grounded in the job text")
    suggested_bid: str = ""
    questions_to_ask: list[str] = Field(default_factory=list)


class QA(BaseModel):
    question: str
    answer: str


class ProposalOut(BaseModel):
    hook_used: str
    cover_letter: str
    screening_answers: list[QA] = Field(default_factory=list)
    suggested_bid: str = ""
    attachments_to_mention: list[str] = Field(default_factory=list)
    what_changed: str = Field(default="", description="If a previous version existed: what was changed and why")
