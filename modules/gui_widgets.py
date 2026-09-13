"""
gui_widgets.py

Small reusable tkinter widgets for ParrotFeedback.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """
    A vertically scrollable frame.

    Usage:
        scrollable = ScrollableFrame(parent)
        scrollable.pack(fill="both", expand=True)
        # add widgets to scrollable.inner instead of `scrollable` itself
        ttk.Label(scrollable.inner, text="hello").pack()
    """

    def __init__(self, container: tk.Widget, *args, **kwargs):
        super().__init__(container, *args, **kwargs)

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        self._window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Make the inner frame track the canvas width so wraplength-based
        # labels reflow correctly when the window is resized.
        def _resize_inner(event):
            canvas.itemconfig(self._window_id, width=event.width)

        canvas.bind("<Configure>", _resize_inner)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel support (Windows / Linux / macOS)
        def _on_mousewheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        self.canvas = canvas


class CheckboxList(ttk.Frame):
    """
    A compact, independently-scrollable list of checkbox options.

    Built for questions that may have many feedback options: instead of
    every option permanently taking up vertical space (which pushes
    everything below it down the page) or a dropdown (which only lets
    you pick one), this renders a fixed-height panel with its own
    scrollbar. Any number of options can be checked at once, long option
    text still wraps and is fully readable, and the question's row
    height stays predictable regardless of how many options it has.
    """

    def __init__(self, parent, labels, *, max_height=140, wraplength=640, **kwargs):
        super().__init__(parent, **kwargs)
        self.vars = [tk.BooleanVar(value=False) for _ in labels]
        self._on_change = None

        canvas = tk.Canvas(self, height=max_height, highlightthickness=1,
                           highlightbackground="#cccccc")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _resize_inner(event):
            canvas.itemconfig(window_id, width=event.width)

        canvas.bind("<Configure>", _resize_inner)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)

        def _wheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def _bind_local_wheel(widget):
            # Bound directly on each widget (not bind_all) so scrolling
            # this list doesn't hijack the outer tab's scrollbar.
            widget.bind("<MouseWheel>", _wheel)
            widget.bind("<Button-4>", _wheel)
            widget.bind("<Button-5>", _wheel)

        _bind_local_wheel(canvas)
        _bind_local_wheel(self.inner)

        for idx, label_text in enumerate(labels):
            row = ttk.Frame(self.inner)
            row.pack(anchor="w", fill="x", pady=1, padx=3)
            _bind_local_wheel(row)

            cb = ttk.Checkbutton(
                row, variable=self.vars[idx], command=self._changed,
            )
            cb.pack(side="left", anchor="n")
            _bind_local_wheel(cb)

            lbl = ttk.Label(
                row, text=label_text, wraplength=wraplength, justify="left",
                cursor="hand2",
            )
            lbl.pack(side="left", anchor="w")
            lbl.bind("<Button-1>", lambda e, i=idx: self._toggle(i))
            _bind_local_wheel(lbl)

    def _toggle(self, idx):
        self.vars[idx].set(not self.vars[idx].get())
        self._changed()

    def _changed(self):
        if self._on_change:
            self._on_change()

    def set_on_change(self, callback):
        """Register a no-arg callback fired whenever a checkbox is toggled."""
        self._on_change = callback

    def selected_indices(self):
        return [i for i, v in enumerate(self.vars) if v.get()]
