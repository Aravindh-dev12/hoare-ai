from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Severity = Literal['critical', 'high', 'medium', 'low', 'info']
Category = Literal['security', 'correctness', 'performance', 'maintainability', 'readability', 'architecture', 'testing', 'reliability']


class Finding(BaseModel):
    category: Category = 'maintainability'
    severity: Severity = 'medium'
    title: str
    description: str
    evidence: str = ''
    file: str = ''
    line: int | None = None
    recommendation: str
    historical_rule_id: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class Chapter(BaseModel):
    name: str
    purpose: str
    files: list[str] = Field(default_factory=list)
    risk: Literal['high', 'medium', 'low'] = 'medium'


class ValidationItem(BaseModel):
    scenario: str
    why: str
    suggested_check: str


class ModelReview(BaseModel):
    summary: str
    change_intent: str = ''
    findings: list[Finding] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    architecture_notes: list[str] = Field(default_factory=list)
    validation_plan: list[ValidationItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    review_id: str
    user_id: str
    created_at: str
    language: str
    code_hash: str
    quality_score: float
    risk_level: str
    summary: str
    change_intent: str
    findings: list[Finding]
    chapters: list[Chapter]
    architecture_notes: list[str]
    validation_plan: list[ValidationItem]
    strengths: list[str]
    matched_rules: list[dict]
    file_count: int
    source: str
    model_backend: str = ''
    model_name: str = ''
