"""
profile_loader.py

Utilities for discovering and loading grading profiles (JSON files that
define the questions, sections and feedback options used to build the
ParrotFeedback interface).

Expected profile schema
------------------------
{
  "Profile": "SomeName",
  "Meta": {
    "CourseTitle": "Advanced Modeling",
    "SheetTitle": "Grading Sheet Assignment 02",
    "Semester": "Winter semester 2025/26",
    "ChairLines": ["Technical University Munich", "Chair of ..."],
    "WeightingText": "Optional paragraph explaining section weights.",
    "GradingScale": [
      {"Label": "> 76", "Grade": "1.0 - 1.3"},
      {"Label": "75 - 66", "Grade": "1.3 - 2.1"}
    ]
  },
  "Questions": [
    {
      "Question": "string",
      "Description": "string",
      "Section": "string",
      "Feedback": [
        {"Points": 0, "Text": "string"},
        {"Points": 1, "Text": ["string", "alternative phrasing", "..."]},
        ...
      ]
    },
    ...
  ]
}

"Text" may be a single string, or a list of strings when several
alternative phrasings share the same point value. Each string in the
list becomes its own selectable option in the UI (all tagged with that
Feedback entry's "Points" value); grouping them under one "Points" key
just avoids repeating the number in the JSON.

"Meta" is entirely optional and only used by the LaTeX report generator
(modules/latex_writer.py) to fill in the document header, the weighting
paragraph, and the grade-scale table at the end. Leave it out (or omit
individual keys) and the report simply skips those parts.
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
class GradingScaleRow:
    label: str
    grade: str


@dataclass
class ProfileMeta:
    """Optional header/report metadata - see module docstring."""
    course_title: str = ""
    sheet_title: str = ""
    semester: str = ""
    chair_lines: List[str] = field(default_factory=list)
    weighting_text: str = ""
    grading_scale: List[GradingScaleRow] = field(default_factory=list)


@dataclass
class Profile:
    name: str
    path: str
    questions: List[Question] = field(default_factory=list)
    meta: ProfileMeta = field(default_factory=ProfileMeta)

    def sections(self) -> List[str]:
        """Return section names, in first-seen order (no duplicates)."""
        seen = []
        for q in self.questions:
            if q.section not in seen:
                seen.append(q.section)
        return seen

    def questions_in_section(self, section: str) -> List[Question]:
        return [q for q in self.questions if q.section == section]

    def max_points_in_section(self, section: str) -> float:
        """Highest Points value any Feedback option in this section has."""
        values = [
            option.points
            for q in self.questions_in_section(section)
            for option in q.feedback
        ]
        return max(values, default=0)

    def max_points_for_question(self, question: Question) -> float:
        return max((o.points for o in question.feedback), default=0)


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
            feedback: List[FeedbackOption] = []
            for fb in feedback_raw:
                points = fb["Points"]
                text = fb["Text"]
                # "Text" can be a single string or a list of alternative
                # phrasings that all share the same Points value.
                texts = text if isinstance(text, list) else [text]
                for t in texts:
                    if not isinstance(t, str):
                        raise ProfileError(
                            f"Question #{i} in {path} has a non-string entry "
                            f"in 'Text': {t!r}."
                        )
                    feedback.append(FeedbackOption(points=points, text=t))
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

    meta_raw = raw.get("Meta", {}) or {}
    grading_scale = [
        GradingScaleRow(label=row.get("Label", ""), grade=row.get("Grade", ""))
        for row in meta_raw.get("GradingScale", [])
    ]
    meta = ProfileMeta(
        course_title=meta_raw.get("CourseTitle", ""),
        sheet_title=meta_raw.get("SheetTitle", ""),
        semester=meta_raw.get("Semester", ""),
        chair_lines=list(meta_raw.get("ChairLines", [])),
        weighting_text=meta_raw.get("WeightingText", ""),
        grading_scale=grading_scale,
    )

    return Profile(name=name, path=path, questions=questions, meta=meta)
