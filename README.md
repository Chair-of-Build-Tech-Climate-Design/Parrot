# ParrotFeedback

A small support tool for producing standardized grading feedback for
student papers. You define the questions, sections and feedback text
once in a JSON profile; ParrotFeedback turns that into a tabbed
click-through interface, saves your selections to a JSON file, and can
render that straight into a PDF grading report using a LaTeX template
you fully control.

Parrot Icon from https://img.icons8.com/?size=100&id=KhmZ1QJoUFqp&format=png&color=000000

## Project structure

```
parrot.py                  # main application (entry point)
generate_report.py         # CLI: turn a saved output JSON into a PDF report
modules/
  profile_loader.py        # discovers & validates profile JSON files
  output_writer.py         # builds & saves the grading output JSON
  gui_widgets.py           # scrollable-frame + compact multi-select checklist
  latex_writer.py          # fills in a .tex template and compiles it to PDF
src/
  profiles/                # your profile JSON files live here
  templates/                # your .tex report templates live here
  outputs/                 # saved grading results (and PDFs) land here by default
```

## Profile JSON schema

```json
{
  "Profile": "AM_2026_Seminarpaper",
  "Questions": [
    {
      "Question": "Document layout & Use of template",
      "Description": "Correct use of the provided Moodle template and compliance with TUM Corporate Design.",
      "Section": "Formal Requirements & Structure",
      "Feedback": [
        { "Points": 0, "Text": ["This was really bad, you can do better.", "Another way this could be phrased."] },
        { "Points": 1, "Text": "This was somewhat bad, you can improve." },
        { "Points": 2, "Text": "Neutral / meets expectations." }
      ]
    }
  ]
}
```

- `Section` controls which tab a question appears under. Tabs are
  created automatically in first-seen order — no need to declare them
  separately.
- `Feedback` can have any number of entries with any point values (not
  limited to 0/1/2). Each entry's `"Text"` can be a single string, or a
  list of strings when several alternative phrasings share the same
  point value — every string becomes its own selectable option in the
  UI, so `{"Points": 0, "Text": ["A.", "B."]}` shows up as two separate
  checkable options, both worth 0 points, without repeating the number.
- Add as many `Questions` as you like, mixing sections freely — they'll
  be grouped correctly regardless of order in the file.
- `Meta` is entirely optional. It's only used by the PDF report
  generator to fill in the header, the weighting paragraph, and the
  grading-scale table — leave any part of it out and the report just
  skips that section.

A ready-to-use example lives at `src/profiles/AM_2026_Seminarpaper.json`.

To add a new profile, drop another `.json` file following this schema
into `src/profiles/` — it will show up in the dropdown automatically.

## Grading interface

Each question shows its feedback options in a compact, independently
scrollable checklist (not a dropdown, and not one giant unscrollable
stack of checkboxes) — any number of options can be checked, long
option text still wraps and stays fully readable, and a question with
many options doesn't balloon the whole tab. Points are auto-suggested
from whatever's checked (the highest point value among the checked
options, since alternative phrasings of the same tier shouldn't sum
together) but the Points field stays a normal, freely editable entry.

On the start screen you pick both a **Profile** and a **PDF template**
(see below) before grading — same dropdown-and-load pattern for both.

## Output JSON

Saved results look like this:

```json
{
  "Profile": "AM_2026_Seminarpaper",
  "Student": "Max Mustermann",
  "MatriculationNumber": "03123456",
  "SubmissionDate": "27.03.2026",
  "CreatedAt": "2026-09-07T12:00:00",
  "TotalPoints": 10,
  "Results": [
    {
      "section": "Formal Requirements & Structure",
      "question": "Document layout & Use of template",
      "description": "Correct use of the provided Moodle template...",
      "points": 2,
      "feedback_text": "Neutral / meets expectations. see Fig. 3.",
      "feedback_selections": [
        { "points": 2, "text": "Neutral / meets expectations.", "appended_text": "see Fig. 3" }
      ]
    }
  ]
}
```

- `points` is whatever ends up in the Points field — the highest points
  value among the checked options by default, or your overwritten
  value if you typed one in.
- `feedback_text` is all selected feedback texts joined into a single
  paragraph, each followed by its own appended note (if any).
- `feedback_selections` is the structured version: one entry per checked
  option with its `points`, `text` and `appended_text`.
- **Per-answer notes:** when you check an answer, a small "Append to this
  answer" box opens right below it. Use it to say where you found the
  problem ("see Fig. 3 and 5", "p. 6, second paragraph") or to add a
  comment. Each selected answer has its own note; unchecking an answer
  hides its box (the typed text is ignored while unchecked).
- Older output files with a question-level `appended_text` are still
  rendered correctly by the PDF generator.

## PDF report templates

Reports are generated from a plain `.tex` file that you fully control —
there's no templating engine or special syntax to learn. ParrotFeedback
just looks for a handful of literal keywords in the file and replaces
them; everything else about the file (fonts, colors, layout, your own
logo image, page size, whatever) is normal LaTeX you can edit by hand.

Drop `.tex` files into `src/templates/` — they show up in the "PDF
template" dropdown on the start screen, next to the profile picker.

**Placeholders your template can use:**

| Keyword                  | Replaced with |
|---------------------------|----------------|
| `COURSE_TITLE`             | Profile `Meta.CourseTitle` |
| `SHEET_TITLE`              | Profile `Meta.SheetTitle` |
| `SEMESTER`                 | Profile `Meta.Semester` |
| `STUDENT_NAME`             | The "Student name" field |
| `MATRICULATION_NUMBER`     | The "Matriculation number" field |
| `SUBMISSION_DATE`          | The "Submission date" field |
| `TOTAL_POINTS`             | Grand total points achieved |
| `MAX_POINTS`               | Grand total points achievable |

A ready-to-use example lives at
`src/templates/AM_default_template.tex`. Copy it as a starting point
for your own layout.

**One rule when editing a template**: don't spell out a placeholder's
exact keyword anywhere in the file except where you want its value
inserted — the replacement is a straightforward find-and-replace, so
mentioning e.g. `SEMESTER` again in an explanatory comment would get
overwritten too. (Regular LaTeX comments — text after an unescaped `%`
— are skipped during replacement as a safety net, but it's simplest to
just avoid the exact spelling elsewhere.)

### Generating a PDF report

1. **From the app**: click "Generate PDF report" next to "Save
   feedback" once you've graded a student — it builds the output data
   in memory, re-reads your chosen template fresh from disk (so edits
   you made after selecting it are picked up), and compiles straight to
   a PDF you choose a save location for.
2. **From the command line**, using a previously saved output JSON:

   ```bash
   python generate_report.py src/outputs/AM_2026_Seminarpaper_Bauta.json
   ```

   This auto-detects the matching profile under `src/profiles/` from
   the JSON's `"Profile"` field, and auto-detects the template if
   exactly one `.tex` file exists under `src/templates/`. Pass
   `--profile path/to/profile.json` or `--template path/to/template.tex`
   to point at either explicitly, `--out some/dir` to control where the
   PDF lands, and `--keep-tex` if you also want the filled-in `.tex`
   source saved alongside it (handy for debugging your template).

**Requirements**: a working LaTeX installation with `pdflatex` on your
`PATH` (e.g. TeX Live or MiKTeX). If it's missing, both the button and
the CLI script will tell you clearly rather than failing silently.
