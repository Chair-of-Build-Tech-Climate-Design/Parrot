"""
generate_report.py

Turns a saved ParrotFeedback output JSON into a formatted PDF grading
report, using an editable .tex template (see src/templates/).

Usage:
    python generate_report.py src/outputs/AM_2026_Seminarpaper_Bauta.json
    python generate_report.py path/to/output.json --profile src/profiles/AM_2026_Seminarpaper.json
    python generate_report.py path/to/output.json --template src/templates/my_template.tex
    python generate_report.py path/to/output.json --out some/other/dir --keep-tex
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from modules.profile_loader import load_profile, ProfileError, PROFILES_DIR  # noqa: E402
from modules.latex_writer import (  # noqa: E402
    list_templates,
    load_template,
    render_template,
    compile_pdf,
    LatexCompileError,
)


def _resolve_profile_path(output: dict, explicit_path: str | None) -> str:
    if explicit_path:
        return explicit_path
    profile_name = output.get("Profile")
    if not profile_name:
        raise SystemExit("Output JSON has no 'Profile' field; pass --profile explicitly.")
    guess = os.path.join(PROFILES_DIR, f"{profile_name}.json")
    if os.path.isfile(guess):
        return guess
    raise SystemExit(
        f"Could not find a profile file for '{profile_name}' at {guess}. "
        "Pass --profile to point at it explicitly."
    )


def _resolve_template_path(explicit_path: str | None) -> str:
    if explicit_path:
        return explicit_path
    templates = list_templates()
    if len(templates) == 1:
        return templates[0]
    if not templates:
        raise SystemExit(
            "No .tex templates found under src/templates/. Add one, or pass "
            "--template to point at a template file explicitly."
        )
    raise SystemExit(
        "Multiple templates found under src/templates/: "
        f"{', '.join(templates)}. Pass --template to pick one."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_json", help="Path to a saved ParrotFeedback output JSON.")
    parser.add_argument(
        "--profile", help="Path to the profile JSON (auto-detected by name if omitted)."
    )
    parser.add_argument(
        "--template",
        help="Path to the .tex template (auto-detected if exactly one exists "
             "under src/templates/).",
    )
    parser.add_argument(
        "--out", default=None,
        help="Directory to write the PDF (and .tex, if --keep-tex) into. "
             "Defaults to the output JSON's own directory.",
    )
    parser.add_argument(
        "--keep-tex", action="store_true",
        help="Also save the generated .tex source next to the PDF.",
    )
    args = parser.parse_args()

    with open(args.output_json, "r", encoding="utf-8") as f:
        output = json.load(f)

    profile_path = _resolve_profile_path(output, args.profile)
    try:
        profile = load_profile(profile_path)
    except ProfileError as e:
        raise SystemExit(f"Could not load profile: {e}")

    template_path = _resolve_template_path(args.template)
    template_source = load_template(template_path)
    tex_source = render_template(template_source, profile, output)

    out_dir = args.out or os.path.dirname(os.path.abspath(args.output_json)) or "."
    stem = os.path.splitext(os.path.basename(args.output_json))[0]

    if args.keep_tex:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"{stem}.tex"), "w", encoding="utf-8") as f:
            f.write(tex_source)

    try:
        pdf_path = compile_pdf(tex_source, out_dir, stem)
    except LatexCompileError as e:
        raise SystemExit(str(e))

    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
