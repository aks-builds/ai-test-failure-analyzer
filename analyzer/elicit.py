"""Single source of clarifying questions, reused by every UI surface.

This lets the MCP server, CLI, TUI, and Web dashboard all ask the same questions
in the same place — no duplication, consistent demo narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Question:
    id: str
    text: str
    choices: list[str] = field(default_factory=list)
    default: str | None = None
    multiselect: bool = False
    free_form: bool = False  # if True, choices are suggestions only

    def json_schema(self) -> dict[str, Any]:
        """A JSON Schema for the answer — used by MCP elicitation."""
        if self.free_form:
            return {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                },
                "required": ["answer"],
            }
        if self.multiselect:
            return {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "array",
                        "items": {"type": "string", "enum": self.choices},
                    },
                },
                "required": ["answer"],
            }
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": self.choices},
            },
            "required": ["answer"],
        }


QUESTIONS: dict[str, Question] = {
    "framework_ambiguous": Question(
        id="framework_ambiguous",
        text="Multiple report formats look plausible. Which framework produced these results?",
        choices=["playwright", "pytest", "jest", "vitest", "cypress", "webdriverio", "junit"],
    ),
    "results_path_missing": Question(
        id="results_path_missing",
        text="No test results file found. Where should I look? (relative path)",
        free_form=True,
        choices=["test-results/results.json", "junit.xml", "reports/results.json"],
    ),
    "no_git_history": Question(
        id="no_git_history",
        text="No git history available. Continue analysis without commit evidence?",
        choices=["yes", "no"],
        default="yes",
    ),
    "confirm_create_issue": Question(
        id="confirm_create_issue",
        text="Create a GitHub issue for the top hypothesis?",
        choices=["yes", "no"],
        default="no",
    ),
    "select_repo": Question(
        id="select_repo",
        text="Which GitHub repository (owner/repo) should the issue be filed against?",
        free_form=True,
    ),
}


def get(qid: str) -> Question:
    """Look up a question by id. Raises KeyError on unknown id."""
    return QUESTIONS[qid]
