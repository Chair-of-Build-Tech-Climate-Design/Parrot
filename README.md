# ParrotFeedback

A small support tool for producing standardized grading feedback for
student papers. You define the questions, sections and feedback text
once in a JSON profile; ParrotFeedback turns that into a tabbed
click-through interface, and saves your selections to a JSON file you
can reuse later (e.g. to auto-fill a Word document).

## Requirements

- Python 3.9+
- `tkinter` (ships with most Python installs; on Linux you may need
  `sudo apt-get install python3-tk`)

No other dependencies.

## Running it

```bash
python parrot.py
```

1. Pick a profile from the dropdown (auto-discovered under `src/profiles/`).
2. Click **Load profile** — a tab is created per `Section`.
3. For each question, check the box next to any feedback text(s) that
   fit — you can select none, one, or several (e.g. several different
   explanations that all justify the same point tier, like "diagrams
   don't fit the template", "tables don't fit the template", "abstract
   too long"). The **Points** field auto-fills with the *highest*
   points value among the checked options (not a sum — picking three
   1-point explanations still suggests 1 point, not 3), but you can
   type over it with whatever value you want. Use **Reset to suggested
   points** to go back to that auto-calculated value. Optionally add
   extra notes in the **Append** box - a **Combined output** preview
   below it always shows the selected feedback texts as one paragraph,
   followed by a blank line, followed by your appended text, updated
   live as you type or check/uncheck options.
4. Click **Save feedback** and choose where to save. A sensible default
   filename/location is suggested under `src/outputs/`.

## Project structure

```
parrot.py                  # main application (entry point)
modules/
  profile_loader.py        # discovers & validates profile JSON files
  output_writer.py         # builds & saves the grading output JSON
  gui_widgets.py           # reusable scrollable-frame widget
src/
  profiles/                # your profile JSON files live here
  outputs/                 # saved grading results land here by default
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
        { "Points": 0, "Text": "This was really bad, you can do better." },
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
- `Feedback` can have any number of options with any point values
  (not limited to 0/1/2).
- Add as many `Questions` as you like, mixing sections freely — they'll
  be grouped correctly regardless of order in the file.

A ready-to-use example lives at `src/profiles/AM_2026_Seminarpaper.json`.

To add a new profile, drop another `.json` file following this schema
into `src/profiles/` — it will show up in the dropdown automatically.

## Output JSON

Saved results look like this:

```json
{
  "Profile": "AM_2026_Seminarpaper",
  "Student": "Max Mustermann",
  "CreatedAt": "2026-09-07T12:00:00",
  "TotalPoints": 10,
  "Results": [
    {
      "section": "Formal Requirements & Structure",
      "question": "Document layout & Use of template",
      "points": 2,
      "feedback_text": "Neutral / meets expectations.",
      "feedback_selections": [
        { "points": 2, "text": "Neutral / meets expectations." }
      ],
      "appended_text": "extra note",
      "combined_text": "Neutral / meets expectations.\n\nextra note"
    }
  ]
}
```

- `points` is whatever ends up in the Points field — the highest points
  value among the checked options by default, or your overwritten
  value if you typed one in.
- `feedback_text` is all selected feedback texts joined into a single
  paragraph.
- `feedback_selections` gives you the same information as a structured
  list, one entry per checked option, in case you need points/text
  separately.
- `combined_text` is exactly what's shown in the GUI's "Combined
  output" preview: `feedback_text`, then a blank line, then
  `appended_text` - ready to drop straight into a Word doc.

This is the file you'd later feed into a Word-generation step.

## Notes on the original spec

The JSON layout originally sketched in the request wasn't valid JSON —
a list (`[...]`) can only contain values, not bare `"key": value`
pairs; those need to live inside objects (`{...}`). The schema above
keeps the same information (Question, Description, Section, Feedback)
but wraps each question in its own `{}` inside a `Questions` list, and
turns each `Feedback` entry into a `{"Points": ..., "Text": ...}`
object so multi-word/long feedback text is unambiguous.
