"""
profile_loader.py

Utilities for discovering and loading grading profiles (JSON files that
define the questions, sections and feedback options used to build the
ParrotFeedback interface).

Expected profile schema
------------------------
{
  "Profile": "SomeName",
  "Questions": [
    {
      "Question": "string",
      "Description": "string",
      "Section": "string",
      "Feedback": [
        {"Points": 0, "Text": "string"},
        {"Points": 1, "Text": "string"},
        ...
      ]
    },
    ...
  ]
}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any


PROFILES_DIR = os.path.join("src", "profiles")


@dataclass
class FeedbackOption:
    points: float
    text: str


@dataclass
class Question:
    question: str
    description: str
    section: str
    feedback: List[FeedbackOption] = field(default_factory=list)


@dataclass
class Profile:
    name: str
    path: str
    questions: List[Question] = field(default_factory=list)

    def sections(self) -> List[str]:
        """Return section names, in first-seen order (no duplicates)."""
        seen = []
        for q in self.questions:
            if q.section not in seen:
                seen.append(q.section)
        return seen

    def questions_in_section(self, section: str) -> List[Question]:
        return [q for q in self.questions if q.section == section]


class ProfileError(Exception):
    """Raised when a profile file is missing or malformed."""


def list_profiles(base_dir: str | None = None) -> List[str]:
    """
    Return a sorted list of relative paths (as strings) to *.json files
    found under the profiles directory.
    """
    profiles_dir = base_dir or PROFILES_DIR
    if not os.path.isdir(profiles_dir):
        return []

    found = []
    for fname in os.listdir(profiles_dir):
        if fname.lower().endswith(".json"):
            found.append(os.path.join(profiles_dir, fname))
    return sorted(found)


def load_profile(path: str) -> Profile:
    """
    Load and validate a profile JSON file, returning a Profile object.
    Raises ProfileError on any structural problem, with a message that
    points at what's wrong so profile authors can fix their JSON.
    """
    if not os.path.isfile(path):
        raise ProfileError(f"Profile file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            raw: Dict[str, Any] = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileError(f"Invalid JSON in {path}: {e}") from e

    if "Questions" not in raw or not isinstance(raw["Questions"], list):
        raise ProfileError(
            f"Profile {path} must contain a 'Questions' list."
        )

    name = raw.get("Profile") or os.path.splitext(os.path.basename(path))[0]

    questions: List[Question] = []
    for i, q in enumerate(raw["Questions"]):
        try:
            feedback_raw = q["Feedback"]
            feedback = [
                FeedbackOption(points=fb["Points"], text=fb["Text"])
                for fb in feedback_raw
            ]
            question = Question(
                question=q["Question"],
                description=q.get("Description", ""),
                section=q.get("Section", "General"),
                feedback=feedback,
            )
        except KeyError as e:
            raise ProfileError(
                f"Question #{i} in {path} is missing required field {e}."
            ) from e
        questions.append(question)

    if not questions:
        raise ProfileError(f"Profile {path} contains no questions.")

    return Profile(name=name, path=path, questions=questions)
