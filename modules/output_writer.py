"""
output_writer.py

Utilities for assembling and saving the grading output JSON: one entry
per question, with the chosen feedback option and any appended free text.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Dict, Any


def build_output(
    profile_name: str,
    student_name: str,
    selections: List[Dict[str, Any]],
    matriculation_number: str = "",
    submission_date: str = "",
) -> Dict[str, Any]:
    """
    Assemble the final output dict.

    selections: list of dicts, each with keys:
        section, question, points, feedback_text, feedback_selections
        (each selection: points, text, appended_text)
    """
    total_points = sum(
        s["points"] for s in selections if s.get("points") is not None
    )

    return {
        "Profile": profile_name,
        "Student": student_name,
        "MatriculationNumber": matriculation_number,
        "SubmissionDate": submission_date,
        "CreatedAt": datetime.now().isoformat(timespec="seconds"),
        "TotalPoints": total_points,
        "Results": selections,
    }


def save_output(path: str, data: Dict[str, Any]) -> None:
    """Write the output dict to disk as pretty-printed JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def default_output_path(profile_name: str, student_name: str) -> str:
    """Suggest a reasonable default filename for the save dialog."""
    safe_student = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in student_name.strip()
    ) or "student"
    safe_profile = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in profile_name.strip()
    )
    outputs_dir = os.path.join("src", "outputs")
    return os.path.join(outputs_dir, f"{safe_profile}_{safe_student}.json")
