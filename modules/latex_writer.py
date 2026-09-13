"""
latex_writer.py

Turns a completed grading output JSON (as saved by parrot.py) plus its
source Profile (loaded via profile_loader.load_profile) into a final
LaTeX document, by taking a user-editable .tex template (from
src/templates/) and replacing a handful of placeholder keywords in it -
then compiles that to PDF with pdflatex.

Template placeholders
----------------------
Simple ones, replaced with plain (LaTeX-escaped) text:
    COURSE_TITLE, SHEET_TITLE, SEMESTER, STUDENT_NAME,
    MATRICULATION_NUMBER, SUBMISSION_DATE, CHAIR_FOOTER,
    TOTAL_POINTS, MAX_POINTS

One big one, replaced with a whole block of generated LaTeX (one table
per section, totals, and the optional weighting/grading-scale blocks):
    FEEDBACK_TABLE_REPLACEMENT

Put these keywords anywhere in your template - see
src/templates/AM_default_template.tex for a working example. Nothing
else about the template is special; edit fonts, colors, layout, add
your own logo, etc. freely.

Usage (see also generate_report.py for a CLI wrapper):

    from modules.profile_loader import load_profile
    from modules.latex_writer import load_template, render_template, compile_pdf

    profile = load_profile("src/profiles/AM_2026_Seminarpaper.json")
    with open("src/outputs/AM_2026_Seminarpaper_Bauta.json") as f:
        output = json.load(f)

    template_source = load_template("src/templates/AM_default_template.tex")
    tex_source = render_template(template_source, profile, output)
    pdf_path = compile_pdf(tex_source, "src/outputs", "Bauta_feedback")
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from .profile_loader import Profile, Question, PROFILES_DIR


TEMPLATES_DIR = os.path.join("src", "templates")

FEEDBACK_MARKER = "FEEDBACK_TABLE_REPLACEMENT"


# ----------------------------------------------------------------------
# Template discovery
# ----------------------------------------------------------------------
def list_templates(base_dir: str | None = None) -> List[str]:
    """Return a sorted list of relative paths to *.tex files under the
    templates directory - mirrors profile_loader.list_profiles()."""
    templates_dir = base_dir or TEMPLATES_DIR
    if not os.path.isdir(templates_dir):
        return []
    found = []
    for fname in os.listdir(templates_dir):
        if fname.lower().endswith(".tex"):
            found.append(os.path.join(templates_dir, fname))
    return sorted(found)


def load_template(path: str) -> str:
    """Read a template file fresh (so edits made between selecting it
    and generating a report are picked up)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Template file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ----------------------------------------------------------------------
# LaTeX escaping
# ----------------------------------------------------------------------
_LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_LATEX_ESCAPE_RE = re.compile("|".join(re.escape(c) for c in _LATEX_SPECIAL_CHARS))


def escape_latex(text: Optional[str]) -> str:
    """Escape a plain string so it's safe to drop into LaTeX source."""
    if not text:
        return ""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group()], str(text))


def _cell(text: Optional[str]) -> str:
    """Escape text for use inside a table cell (also fixes line breaks)."""
    escaped = escape_latex(text)
    return escaped.replace("\n", r" \newline ")


# ----------------------------------------------------------------------
# Matching profile questions with saved results
# ----------------------------------------------------------------------
def _index_results(output: Dict[str, Any]) -> Dict[tuple, Dict[str, Any]]:
    """Map (section, question) -> result dict, for quick lookup."""
    index = {}
    for r in output.get("Results", []):
        index[(r.get("section"), r.get("question"))] = r
    return index


# ----------------------------------------------------------------------
# Table building
# ----------------------------------------------------------------------
def _section_table(profile: Profile, section: str, results_by_key: dict) -> str:
    """Build the longtable for one section, in the style of the sample
    grading sheet: one column per possible point value (0..max), an
    X mark in whichever column was awarded, and a wide Comments column
    with the selected feedback text."""

    max_points = profile.max_points_in_section(section)
    if float(max_points).is_integer():
        max_points = int(max_points)
    point_cols = list(range(0, max_points + 1)) if isinstance(max_points, int) else [0]

    n_point_cols = len(point_cols)
    criteria_width = 0.38
    comments_width = 0.38  # fixed, same on every table
    point_col_width = (1 - criteria_width - comments_width) / n_point_cols

    point_col_spec = ">{\\centering\\arraybackslash}p{%.3f\\textwidth}|" % point_col_width
    col_spec = (
        "|p{%.3f\\textwidth}|" % criteria_width
        + point_col_spec * n_point_cols
        + "p{%.3f\\textwidth}|" % comments_width
    )

    lines = []
    lines.append(r"\begin{longtable}{%s}" % col_spec)
    lines.append(r"\hline")
    lines.append(
        r"\textbf{Criteria} & "
        + " & ".join(rf"\textbf{{{p}}}" for p in point_cols)
        + r" & \textbf{Comments} \\ \hline"
    )
    lines.append(r"\endfirsthead")
    lines.append(r"\hline")
    lines.append(
        r"\textbf{Criteria} & "
        + " & ".join(rf"\textbf{{{p}}}" for p in point_cols)
        + r" & \textbf{Comments} \\ \hline"
    )
    lines.append(r"\endhead")
    lines.append(r"\hline\endfoot")
    lines.append(r"\hline\endlastfoot")

    questions = profile.questions_in_section(section)
    achieved_counts = {p: 0 for p in point_cols}
    total_points = 0
    total_max = 0

    for q in questions:
        result = results_by_key.get((section, q.question))
        q_max = profile.max_points_for_question(q)
        total_max += q_max

        points = None
        comment = ""
        if result is not None:
            points = result.get("points")
            feedback_text = result.get("feedback_text") or ""
            appended = result.get("appended_text") or ""
            comment = feedback_text
            if appended:
                comment = f"{comment}\n{appended}" if comment else appended

        if points is not None:
            total_points += points
            if points in achieved_counts:
                achieved_counts[points] += 1

        criteria_cell = rf"\textbf{{{_cell(q.question)}}}"
        if q.description:
            criteria_cell += r" \newline {\small\itshape \hspace{1em}- " + _cell(q.description) + "}"

        marks = []
        for p in point_cols:
            marks.append("X" if points == p else "")

        row = f"{criteria_cell} & " + " & ".join(marks) + f" & {_cell(comment)}"
        lines.append(row + r" \\ \hline")

    lines.append(r"\end{longtable}")

    return (
        "\n".join(lines),
        {"total_points": total_points, "total_max": total_max},
    )

# ----------------------------------------------------------------------
# The FEEDBACK_TABLE_REPLACEMENT blob: every section's table, section
# and grand totals, and the optional weighting/grading-scale blocks.
# ----------------------------------------------------------------------
def _build_feedback_blob(profile: Profile, output: Dict[str, Any]) -> tuple[str, int, int]:
    meta = profile.meta
    results_by_key = _index_results(output)

    section_blocks = []
    grand_total = 0
    grand_max = 0
    for section in profile.sections():
        table_tex, stats = _section_table(profile, section, results_by_key)
        grand_total += stats["total_points"]
        grand_max += stats["total_max"]

        section_blocks.append(
            "\n".join(
                [
                    r"\subsection*{%s}" % escape_latex(section),
                    table_tex,
                    r"\vspace{-0.5em}",
                    r"\noindent\textbf{Section total: %s / %s points}"
                    % (stats["total_points"], stats["total_max"]),
                    r"\bigskip",
                ]
            )
        )

    blob_parts = list(section_blocks)
    blob_parts.append(
        r"\noindent\textbf{Total: %s / %s points}" % (grand_total, grand_max)
    )

    return "\n\n".join(blob_parts), grand_total, grand_max


# ----------------------------------------------------------------------
# Template rendering (simple keyword replacement - no templating engine)
# ----------------------------------------------------------------------
def _split_latex_comment(line: str) -> tuple[str, str]:
    """Split a line into (code, comment) at the first unescaped '%'."""
    i = 0
    while True:
        idx = line.find("%", i)
        if idx == -1:
            return line, ""
        if idx == 0 or line[idx - 1] != "\\":
            return line[:idx], line[idx:]
        i = idx + 1


def render_template(template_source: str, profile: Profile, output: Dict[str, Any]) -> str:
    """
    Fill in a .tex template by literally replacing placeholder keywords
    with generated content. See the module docstring for the list of
    keywords.

    Replacement only happens in the "code" part of each line (before an
    unescaped '%'), so a keyword mentioned inside your own explanatory
    LaTeX comments won't accidentally get substituted too.
    """
    meta = profile.meta
    feedback_blob, grand_total, grand_max = _build_feedback_blob(profile, output)

    logo_path = os.path.abspath(os.path.join(PROFILES_DIR, "TUM_Logo.png")).replace("\\", "/")

    replacements = {
        "COURSE_TITLE": escape_latex(meta.course_title) or "Grading Sheet",
        "SHEET_TITLE": escape_latex(meta.sheet_title),
        "SEMESTER": escape_latex(meta.semester),
        "STUDENT_NAME": escape_latex(output.get("Student", "")),
        "MATRICULATION_NUMBER": escape_latex(output.get("MatriculationNumber", "")),
        "SUBMISSION_DATE": escape_latex(output.get("SubmissionDate", "")),
        "TOTAL_POINTS": str(grand_total),
        "MAX_POINTS": str(grand_max),
        "LOGO_PATH": logo_path,
        FEEDBACK_MARKER: feedback_blob,
    }
    # Replace longest keywords first so no keyword can accidentally be a
    # substring match inside another keyword's replacement value.
    ordered_keys = sorted(replacements, key=len, reverse=True)

    out_lines = []
    for line in template_source.split("\n"):
        code, comment = _split_latex_comment(line)
        for key in ordered_keys:
            if key in code:
                code = code.replace(key, replacements[key])
        out_lines.append(code + comment)
    return "\n".join(out_lines)


# ----------------------------------------------------------------------
# Compilation
# ----------------------------------------------------------------------
class LatexCompileError(Exception):
    """Raised when pdflatex fails; carries its log output."""


def compile_pdf(tex_source: str, out_dir: str, filename_stem: str) -> str:
    """
    Write tex_source to a temp working dir, run pdflatex twice (for
    longtable page-break stability), and copy the resulting PDF into
    out_dir. Returns the path to the final PDF.
    """
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise LatexCompileError(
            "pdflatex was not found on PATH. Install a LaTeX distribution "
            "(e.g. TeX Live) or run report generation on a machine that has it."
        )

    os.makedirs(out_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tex_path = os.path.join(tmp, f"{filename_stem}.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)

        log_tail = ""
        for _ in range(2):  # run twice for stable page breaks/refs
            proc = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
                 f"{filename_stem}.tex"],
                cwd=tmp,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            log_tail = proc.stdout[-4000:]
            if proc.returncode != 0:
                raise LatexCompileError(
                    f"pdflatex failed (exit {proc.returncode}). Last log output:\n"
                    f"{log_tail}"
                )

        pdf_src = os.path.join(tmp, f"{filename_stem}.pdf")
        if not os.path.isfile(pdf_src):
            raise LatexCompileError(
                f"pdflatex reported success but no PDF was produced. Log:\n{log_tail}"
            )

        pdf_dest = os.path.join(out_dir, f"{filename_stem}.pdf")
        shutil.copyfile(pdf_src, pdf_dest)
        return pdf_dest
