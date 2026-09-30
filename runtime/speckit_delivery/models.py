from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Obligation(Strict):
    id: Identifier
    kind: Literal["requirement", "acceptance", "task"]
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)


class Assertion(Strict):
    field: str = Field(min_length=1)
    operator: Literal["equals", "contains", "exists"] = "equals"
    value: Any = None


class Step(Strict):
    action: Literal["goto", "click", "fill", "assert_text", "assert_visible"]
    target: str = Field(min_length=1)
    value: str = ""


class Scenario(Strict):
    id: Identifier
    title: str = Field(min_length=1)
    kind: Literal["cli", "api", "ui", "inspection"]
    obligations: list[Identifier] = Field(min_length=1)
    expected: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    command: list[str] = Field(default_factory=list)
    url: str = ""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    body: Any = None
    file: str = ""
    steps: list[Step] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    regression: bool = False

    @model_validator(mode="after")
    def meaningful(self):
        if len(set(self.obligations)) != len(self.obligations):
            raise ValueError("duplicate scenario obligation")
        if self.kind == "ui":
            if not self.steps or not any(s.action.startswith("assert_") for s in self.steps):
                raise ValueError("UI scenarios require observable assertions, not just screenshots")
        elif not self.assertions:
            raise ValueError("scenarios require explicit assertions")
        if self.kind == "cli" and (
            not self.command or not any(a.field == "exit_code" and a.operator == "equals" for a in self.assertions)
        ):
            raise ValueError("CLI scenarios require argv and an expected exit code")
        if self.kind == "api" and (not self.url or not any(a.field != "status" for a in self.assertions)):
            raise ValueError("API scenarios require a URL and a response-content assertion")
        if self.kind == "inspection" and not self.file:
            raise ValueError("inspection requires a repository file")
        return self


class Narrative(Strict):
    problem: str = "Describe the problem addressed by this feature."
    expected_benefit: str = "Expected benefit has not been measured."
    implementation: str = "See the approved implementation plan."
    operations: str = "Review rollout, dependencies, recovery, and ownership before release."
    limitations: list[str] = Field(default_factory=list)
    brand: str = "Spec Kit Delivery"
    accent: str = Field(default="#245B78", pattern=r"^#[0-9a-fA-F]{6}$")


class Baseline(Strict):
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1)
    documents: dict[str, str]
    obligations: list[Obligation]
    scenarios: list[Scenario]
    narrative: Narrative = Field(default_factory=Narrative)

    @model_validator(mode="after")
    def coverage(self):
        ids = [o.id for o in self.obligations]
        scenario_ids = [s.id for s in self.scenarios]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("missing or duplicate obligation IDs")
        if not scenario_ids or len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("missing or duplicate scenario IDs")
        covered = {o for s in self.scenarios for o in s.obligations}
        if covered != set(ids):
            raise ValueError(f"coverage mismatch: missing={set(ids) - covered}, unknown={covered - set(ids)}")
        if not any(s.regression for s in self.scenarios):
            raise ValueError("at least one scenario must cover the project's regression checks")
        return self


class Policy(Strict):
    schema_version: Literal[1] = 1
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    agent: str
    approvers: list[str] = Field(min_length=1)
    verification_workflow: str = ".github/workflows/delivery-evidence.yml"
    required_check: str = "delivery-acceptance"

    @model_validator(mode="after")
    def separation(self):
        if self.agent.casefold() in {a.casefold() for a in self.approvers}:
            raise ValueError("agent identity cannot be a human approver")
        return self
