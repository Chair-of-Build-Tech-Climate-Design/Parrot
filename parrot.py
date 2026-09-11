"""
parrot.py

ParrotFeedback - a small support tool that helps produce standardized
grading feedback for student papers, based on a reusable JSON profile
that defines questions, sections and feedback text options.

Run it with:
    python parrot.py

Workflow:
    1. Pick a profile from src/profiles/ (dropdown, searched automatically).
    2. Click "Load profile" - a tab is created for each Section.
    3. For each question, pick the matching feedback option and, if you
       like, add extra free text in the "Append" box.
    4. Click "Save feedback" to write the result to a JSON file you can
       reuse later (e.g. to auto-fill a Word document).
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Allow running the script from any working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from modules.profile_loader import (  # noqa: E402
    list_profiles,
    load_profile,
    Profile,
    ProfileError,
)
from modules.output_writer import (  # noqa: E402
    build_output,
    save_output,
    default_output_path,
)
from modules.gui_widgets import ScrollableFrame  # noqa: E402


APP_TITLE = "ParrotFeedback"


class QuestionRow(ttk.Frame):
    """
    Renders a single question: title, description, one checkbox per
    feedback option (fully readable, no truncation, multiple may be
    selected at once), an editable "Points" field (auto-summed from the
    checked options but freely overwritable), and an "Append" free-text
    box.
    """

    def __init__(self, parent, question, **kwargs):
        super().__init__(parent, padding=(8, 8), **kwargs)
        self.question = question

        # One BooleanVar per feedback option - any number can be checked.
        self.option_vars = [tk.BooleanVar(value=False) for _ in question.feedback]

        # True once the user has typed into the Points field themselves;
        # from then on checking/unchecking options no longer overwrites it.
        self._points_manual = False

        self.configure(relief="groove", borderwidth=1)

        title = ttk.Label(
            self, text=question.question, font=("TkDefaultFont", 10, "bold"),
            wraplength=760, justify="left",
        )
        title.pack(anchor="w", fill="x")

        if question.description:
            desc = ttk.Label(
                self, text=question.description, foreground="#555555",
                wraplength=760, justify="left",
            )
            desc.pack(anchor="w", fill="x", pady=(2, 6))

        options_frame = ttk.Frame(self)
        options_frame.pack(anchor="w", fill="x")

        # Checkbutton text doesn't wrap by default, and feedback text can be
        # long, so pair a plain Checkbutton (no text) with a wrapping Label
        # that also toggles it when clicked.
        for idx, option in enumerate(question.feedback):
            label_text = f"[{option.points} pts]  {option.text}"

            row_frame = ttk.Frame(options_frame)
            row_frame.pack(anchor="w", fill="x", pady=1)

            cb = ttk.Checkbutton(
                row_frame, variable=self.option_vars[idx],
                command=self._on_options_changed,
            )
            cb.pack(side="left", anchor="n")

            lbl = ttk.Label(
                row_frame, text=label_text, wraplength=700, justify="left",
                cursor="hand2",
            )
            lbl.pack(side="left", anchor="w")
            lbl.bind("<Button-1>", lambda e, i=idx: self._toggle_option(i))

        # Points row - shows the auto-summed total, but is a normal entry
        # so the grader can type over it with whatever value they want.
        points_row = ttk.Frame(self)
        points_row.pack(anchor="w", fill="x", pady=(6, 0))

        ttk.Label(points_row, text="Points:").pack(side="left")

        self.points_var = tk.StringVar(value="0")
        self.points_entry = ttk.Entry(points_row, textvariable=self.points_var, width=8)
        self.points_entry.pack(side="left", padx=(4, 8))
        self.points_entry.bind("<KeyRelease>", self._on_points_typed)

        ttk.Button(
            points_row, text="Reset to suggested points",
            command=self._reset_points_to_sum,
        ).pack(side="left")

        append_label = ttk.Label(self, text="Append (optional):")
        append_label.pack(anchor="w", pady=(6, 0))

        self.append_text = tk.Text(self, height=2, wrap="word")
        self.append_text.pack(fill="x", pady=(2, 0))
        self.append_text.bind("<KeyRelease>", lambda e: self._update_preview())

        preview_label = ttk.Label(self, text="Combined output (preview):")
        preview_label.pack(anchor="w", pady=(6, 0))

        self.preview_text = tk.Text(
            self, height=3, wrap="word", background="#f2f2f2",
        )
        self.preview_text.pack(fill="x", pady=(2, 0))
        self.preview_text.configure(state="disabled")

        self._update_preview()

    # ------------------------------------------------------------------
    # Option / points interaction
    # ------------------------------------------------------------------
    def _toggle_option(self, idx: int):
        var = self.option_vars[idx]
        var.set(not var.get())
        self._on_options_changed()

    def _on_options_changed(self):
        if not self._points_manual:
            self._set_points_value(self._default_points())
        self._update_preview()

    def _on_points_typed(self, event=None):
        # Any manual keystroke in the Points field means "stop auto-updating".
        self._points_manual = True

    def _reset_points_to_sum(self):
        self._points_manual = False
        self._set_points_value(self._default_points())

    def _default_points(self):
        """
        Suggested points for whatever's currently checked.

        Feedback options are usually several alternative phrasings for the
        *same* point tier (e.g. three different "1 point" explanations for
        why the template wasn't followed), so this takes the highest points
        value among the checked options rather than summing them - summing
        would wrongly add up to 3 points if you picked all three 1-point
        explanations at once. You can always overwrite the field manually
        regardless.
        """
        selected_points = [
            option.points
            for var, option in zip(self.option_vars, self.question.feedback)
            if var.get()
        ]
        return max(selected_points, default=0)

    def _set_points_value(self, value):
        # Show ints without a trailing ".0"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        self.points_var.set(str(value))

    def _selected_options(self):
        return [
            option for var, option in zip(self.option_vars, self.question.feedback)
            if var.get()
        ]

    def _resolved_points(self):
        """Whatever is currently in the Points field, parsed as a number."""
        raw = self.points_var.get().strip()
        if not raw:
            return 0
        try:
            value = float(raw)
        except ValueError:
            return 0
        if value.is_integer():
            value = int(value)
        return value

    def _combined_feedback_text(self):
        """Selected feedback texts joined into a single paragraph."""
        selected = self._selected_options()
        return " ".join(option.text.strip() for option in selected)

    def _combined_output(self):
        """
        Full combined output text: the feedback paragraph, then a blank
        line, then the appended text (if any).
        """
        feedback = self._combined_feedback_text()
        appended = self.append_text.get("1.0", "end").strip()
        if feedback and appended:
            return f"{feedback}\n\n{appended}"
        return feedback or appended

    def _update_preview(self):
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", self._combined_output())
        self.preview_text.configure(state="disabled")

    def get_selection(self):
        appended = self.append_text.get("1.0", "end").strip()
        selected = self._selected_options()

        if not selected:
            return {
                "section": self.question.section,
                "question": self.question.question,
                "description": self.question.description,
                "points": self._resolved_points() if self._points_manual else None,
                "feedback_text": None,
                "feedback_selections": [],
                "appended_text": appended,
                "combined_text": appended or None,
            }

        feedback_text = self._combined_feedback_text()
        return {
            "section": self.question.section,
            "question": self.question.question,
            "description": self.question.description,
            "points": self._resolved_points(),
            "feedback_text": feedback_text,
            "feedback_selections": [
                {"points": option.points, "text": option.text} for option in selected
            ],
            "appended_text": appended,
            "combined_text": self._combined_output(),
        }

    def is_answered(self) -> bool:
        return any(var.get() for var in self.option_vars)


class ParrotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x700")

        self.profile: Profile | None = None
        self.question_rows: list[QuestionRow] = []

        self._build_start_screen()

    # ------------------------------------------------------------------
    # Screen 1: profile selection
    # ------------------------------------------------------------------
    def _build_start_screen(self):
        self.start_frame = ttk.Frame(self, padding=20)
        self.start_frame.pack(fill="both", expand=True)

        ttk.Label(
            self.start_frame, text="ParrotFeedback", font=("TkDefaultFont", 16, "bold")
        ).pack(pady=(0, 4))
        ttk.Label(
            self.start_frame,
            text="Select a grading profile to get started.",
        ).pack(pady=(0, 16))

        row = ttk.Frame(self.start_frame)
        row.pack(fill="x")

        ttk.Label(row, text="Profile:").pack(side="left")

        self.profile_paths = list_profiles()
        display_names = [os.path.relpath(p) for p in self.profile_paths]

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(
            row, textvariable=self.profile_var, values=display_names,
            state="readonly", width=60,
        )
        self.profile_combo.pack(side="left", padx=8, fill="x", expand=True)
        if display_names:
            self.profile_combo.current(0)

        ttk.Button(
            self.start_frame, text="Load profile", command=self._on_load_profile
        ).pack(pady=16)

        if not display_names:
            ttk.Label(
                self.start_frame,
                text=f"No profiles found under '{os.path.join('src', 'profiles')}'.",
                foreground="red",
            ).pack()

    def _on_load_profile(self):
        selected = self.profile_var.get()
        if not selected:
            messagebox.showwarning(APP_TITLE, "Please select a profile first.")
            return
        try:
            self.profile = load_profile(selected)
        except ProfileError as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        self.start_frame.destroy()
        self._build_grading_screen()

    # ------------------------------------------------------------------
    # Screen 2: grading interface (tabs per section)
    # ------------------------------------------------------------------
    def _build_grading_screen(self):
        top_bar = ttk.Frame(self, padding=(10, 8))
        top_bar.pack(fill="x")

        ttk.Label(top_bar, text=f"Profile: {self.profile.name}",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left")

        ttk.Label(top_bar, text="   Student name:").pack(side="left", padx=(20, 4))
        self.student_var = tk.StringVar()
        ttk.Entry(top_bar, textvariable=self.student_var, width=30).pack(side="left")

        ttk.Button(
            top_bar, text="Choose different profile", command=self._restart
        ).pack(side="right")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.question_rows = []

        for section in self.profile.sections():
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=section)

            scrollable = ScrollableFrame(tab)
            scrollable.pack(fill="both", expand=True)

            for question in self.profile.questions_in_section(section):
                row = QuestionRow(scrollable.inner, question)
                row.pack(fill="x", padx=8, pady=6)
                self.question_rows.append(row)

        bottom_bar = ttk.Frame(self, padding=(10, 8))
        bottom_bar.pack(fill="x")

        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom_bar, textvariable=self.status_var, foreground="#555555").pack(
            side="left"
        )

        ttk.Button(
            bottom_bar, text="Save feedback", command=self._on_save
        ).pack(side="right")

    def _restart(self):
        for child in list(self.children.values()):
            child.destroy()
        self.profile = None
        self.question_rows = []
        self._build_start_screen()

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def _on_save(self):
        unanswered = [r for r in self.question_rows if not r.is_answered()]
        if unanswered:
            proceed = messagebox.askyesno(
                APP_TITLE,
                f"{len(unanswered)} question(s) have no feedback option selected. "
                "Save anyway?",
            )
            if not proceed:
                return

        student_name = self.student_var.get().strip() or "unknown_student"
        selections = [row.get_selection() for row in self.question_rows]
        output = build_output(self.profile.name, student_name, selections)

        suggested_path = default_output_path(self.profile.name, student_name)
        os.makedirs(os.path.dirname(suggested_path), exist_ok=True)

        path = filedialog.asksaveasfilename(
            title="Save feedback as",
            initialdir=os.path.dirname(suggested_path),
            initialfile=os.path.basename(suggested_path),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return

        save_output(path, output)
        self.status_var.set(f"Saved to {path}")
        messagebox.showinfo(APP_TITLE, f"Feedback saved to:\n{path}")


if __name__ == "__main__":
    app = ParrotApp()
    app.mainloop()
