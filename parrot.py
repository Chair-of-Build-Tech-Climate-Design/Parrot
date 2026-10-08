"""
ParrotFeedback - a small support tool that helps produce standardized
grading feedback for student papers, based on a reusable JSON profile
that defines questions, sections and feedback text options.

Run it with:
    python parrot.py

Workflow:
    1. Pick a profile from src/profiles/ (dropdown, searched automatically).
    2. Click "Load profile" - a tab is created for each Section.
    3. For each question, check the matching feedback option(s) and, if
       you like, add a note under any selected answer.
    4. Click "Save feedback" to write the result to a JSON file, and/or
       "Generate PDF report" to render it straight to a formatted PDF.
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
from modules.gui_widgets import ScrollableFrame, CheckboxList  # noqa: E402
from modules.latex_writer import (  # noqa: E402
    list_templates,
    load_template,
    render_template,
    compile_pdf,
    LatexCompileError,
)


APP_TITLE = "ParrotFeedback"

# Path to the app icon (PNG). Relative to this file so it works no matter
# what directory the script is launched from.
ICON_PATH = os.path.join(BASE_DIR, "assets", "icons8-parrot-96.png")


class QuestionRow(ttk.Frame):
    """
    Renders a single question: title, description, a compact
    independently-scrolling checklist of feedback options (fully
    readable, no truncation, multiple may be selected at once, and
    doesn't balloon the page even with many options), an editable
    "Points" field (auto-updated from the checked options but freely
    overwritable), and a free-text note that can be appended to each selected answer.
    """

    # How many options are shown before the checklist starts scrolling
    # instead of growing taller.
    _VISIBLE_OPTION_ROWS = 5

    def __init__(self, parent, question, **kwargs):
        super().__init__(parent, padding=(8, 8), **kwargs)
        self.question = question

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

        option_labels = [
            f"[{option.points} pts]  {option.text}" for option in question.feedback
        ]
        # Roughly 28px per option row; capped so short lists don't leave
        # a lot of empty space and long lists scroll instead of growing.
        approx_height = min(len(option_labels), self._VISIBLE_OPTION_ROWS) * 28 + 8
        self.options_list = CheckboxList(
            self, option_labels, max_height=max(approx_height, 40) + 160,
            with_append=True,
        )
        self.options_list.pack(anchor="w", fill="x")
        self.options_list.set_on_change(self._on_options_changed)

        # Points row - shows the auto-updated suggestion, but is a normal
        # entry so the grader can type over it with whatever value they want.
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


    # ------------------------------------------------------------------
    # Option / points interaction
    # ------------------------------------------------------------------
    def _on_options_changed(self):
        if not self._points_manual:
            self._set_points_value(self._default_points())

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
            self.question.feedback[i].points
            for i in self.options_list.selected_indices()
        ]
        return max(selected_points, default=0)

    def _set_points_value(self, value):
        # Show ints without a trailing ".0"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        self.points_var.set(str(value))

    def _selected_options(self):
        return [
            self.question.feedback[i]
            for i in self.options_list.selected_indices()
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

    @staticmethod
    def _join(text, appended):
        text = text.strip()
        if not appended:
            return text
        if appended[-1] not in ".!?:;)":
            appended += "."
        return f"{text} {appended}"

    def _selected_with_appends(self):
        """[(option, appended_text), ...] for every checked answer."""
        return [
            (self.question.feedback[i], self.options_list.append_text(i))
            for i in self.options_list.selected_indices()
        ]

    def get_selection(self):
        pairs = self._selected_with_appends()
        base = {
            "section": self.question.section,
            "question": self.question.question,
            "description": self.question.description,
        }
        if not pairs:
            base.update({
                "points": self._resolved_points() if self._points_manual else None,
                "feedback_text": None,
                "feedback_selections": [],
            })
            return base

        base.update({
            "points": self._resolved_points(),
            "feedback_text": " ".join(self._join(o.text, a) for o, a in pairs),
            "feedback_selections": [
                {"points": o.points, "text": o.text, "appended_text": a}
                for o, a in pairs
            ],
        })
        return base

    def is_answered(self) -> bool:
        return bool(self.options_list.selected_indices())


def _fix_windows_taskbar_icon():
    """
    On Windows, the taskbar icon is tied to the process's "App User Model
    ID", not the Tk window icon. Without this, apps launched via
    python.exe/pythonw.exe get grouped under Python's own icon on the
    taskbar regardless of what iconphoto()/iconbitmap() is set to.
    Calling this before the Tk window is created gives the process its
    own identity so the taskbar uses our icon instead.
    No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ParrotFeedback.App"
        )
    except Exception as e:
        print(f"Warning: could not set AppUserModelID: {e}", file=sys.stderr)


class ParrotApp(tk.Tk):
    def __init__(self):
        _fix_windows_taskbar_icon()
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x700")
        self._set_app_icon()

        self.profile: Profile | None = None
        self.question_rows: list[QuestionRow] = []
        self.template_path: str | None = None

        self._build_start_screen()

    # ------------------------------------------------------------------
    # Window icon
    # ------------------------------------------------------------------
    def _set_app_icon(self):
        """
        Set the window/taskbar icon from assets/icons8-parrot-96.png.

        Uses iconphoto (not iconbitmap) since the icon is a PNG rather
        than a .ico/.xbm file. Keep a reference on self so the PhotoImage
        isn't garbage-collected (which would blank the icon).
        """
        if not os.path.isfile(ICON_PATH):
            print(f"Warning: icon not found at {ICON_PATH}", file=sys.stderr)
            return
        try:
            large = tk.PhotoImage(file=ICON_PATH)
            # A smaller subsampled copy tends to render more reliably as
            # the taskbar/Alt-Tab "small" icon than scaling the 96px image
            # down on the fly.
            small = large.subsample(3, 3)  # ~32px
            self._icon_images = (large, small)  # keep refs alive
            self.iconphoto(True, large, small)
        except tk.TclError as e:
            print(f"Warning: could not load icon '{ICON_PATH}': {e}", file=sys.stderr)

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
            text="Select a grading profile and a PDF report template to get started.",
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

        if not display_names:
            ttk.Label(
                self.start_frame,
                text=f"No profiles found under '{os.path.join('src', 'profiles')}'.",
                foreground="red",
            ).pack(anchor="w")

        template_row = ttk.Frame(self.start_frame)
        template_row.pack(fill="x", pady=(8, 0))

        ttk.Label(template_row, text="PDF template:").pack(side="left")

        self.template_paths = list_templates()
        template_display_names = [os.path.relpath(p) for p in self.template_paths]

        self.template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(
            template_row, textvariable=self.template_var, values=template_display_names,
            state="readonly", width=60,
        )
        self.template_combo.pack(side="left", padx=8, fill="x", expand=True)
        if template_display_names:
            self.template_combo.current(0)

        if not template_display_names:
            ttk.Label(
                self.start_frame,
                text=f"No .tex templates found under '{os.path.join('src', 'templates')}' "
                     "- you can still grade and save JSON, but PDF generation needs one.",
                foreground="#a06000",
            ).pack(anchor="w", pady=(4, 0))

        ttk.Button(
            self.start_frame, text="Load profile", command=self._on_load_profile
        ).pack(pady=16)

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

        self.template_path = self.template_var.get() or None

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

        ttk.Button(
            top_bar, text="Choose different profile", command=self._restart
        ).pack(side="right")

        details_bar = ttk.Frame(self, padding=(10, 0, 10, 8))
        details_bar.pack(fill="x")

        ttk.Label(details_bar, text="Student name:").pack(side="left")
        self.student_var = tk.StringVar()
        ttk.Entry(details_bar, textvariable=self.student_var, width=24).pack(
            side="left", padx=(4, 16)
        )

        ttk.Label(details_bar, text="Matriculation number:").pack(side="left")
        self.matriculation_number_var = tk.StringVar()
        ttk.Entry(
            details_bar, textvariable=self.matriculation_number_var, width=14
        ).pack(side="left", padx=(4, 16))

        ttk.Label(details_bar, text="Submission date:").pack(side="left")
        self.submission_date_var = tk.StringVar()
        ttk.Entry(
            details_bar, textvariable=self.submission_date_var, width=12
        ).pack(side="left", padx=(4, 0))

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
            bottom_bar, text="Generate PDF report", command=self._on_generate_pdf
        ).pack(side="right", padx=(0, 8))

        ttk.Button(
            bottom_bar, text="Save feedback", command=self._on_save
        ).pack(side="right")

    def _restart(self):
        for child in list(self.children.values()):
            child.destroy()
        self.profile = None
        self.question_rows = []
        self.template_path = None
        self._build_start_screen()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _confirm_unanswered(self) -> bool:
        """Warn about unanswered questions; returns True if it's OK to proceed."""
        unanswered = [r for r in self.question_rows if not r.is_answered()]
        if not unanswered:
            return True
        return messagebox.askyesno(
            APP_TITLE,
            f"{len(unanswered)} question(s) have no feedback option selected. "
            "Continue anyway?",
        )

    def _build_current_output(self) -> dict:
        student_name = self.student_var.get().strip() or "unknown_student"
        selections = [row.get_selection() for row in self.question_rows]
        return build_output(
            self.profile.name,
            student_name,
            selections,
            matriculation_number=self.matriculation_number_var.get().strip(),
            submission_date=self.submission_date_var.get().strip(),
        )

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def _on_save(self):
        if not self._confirm_unanswered():
            return

        output = self._build_current_output()
        student_name = output["Student"]

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

    # ------------------------------------------------------------------
    # PDF report generation
    # ------------------------------------------------------------------
    def _on_generate_pdf(self):
        if not self.template_path:
            messagebox.showwarning(
                APP_TITLE,
                "No PDF template was selected on the start screen. "
                f"Add a .tex file under '{os.path.join('src', 'templates')}' "
                "and choose a different profile to pick it up.",
            )
            return

        if not self._confirm_unanswered():
            return

        output = self._build_current_output()
        student_name = output["Student"]

        suggested_path = default_output_path(self.profile.name, student_name)
        suggested_pdf = os.path.splitext(suggested_path)[0] + ".pdf"
        os.makedirs(os.path.dirname(suggested_pdf), exist_ok=True)

        path = filedialog.asksaveasfilename(
            title="Save PDF report as",
            initialdir=os.path.dirname(suggested_pdf),
            initialfile=os.path.basename(suggested_pdf),
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not path:
            return

        self.status_var.set("Compiling PDF report...")
        self.update_idletasks()

        try:
            # Re-read the template file fresh, in case it was edited by
            # hand since it was selected on the start screen.
            template_source = load_template(self.template_path)
            tex_source = render_template(template_source, self.profile, output)
            out_dir, filename = os.path.split(path)
            stem = os.path.splitext(filename)[0]
            compiled_path = compile_pdf(tex_source, out_dir, stem)
        except (LatexCompileError, FileNotFoundError) as e:
            self.status_var.set("PDF generation failed.")
            messagebox.showerror(APP_TITLE, f"Could not generate the PDF report:\n\n{e}")
            return

        self.status_var.set(f"PDF report saved to {compiled_path}")
        messagebox.showinfo(APP_TITLE, f"PDF report saved to:\n{compiled_path}")


if __name__ == "__main__":
    app = ParrotApp()
    app.mainloop()