"""
main.py — Disk Audit & Clean desktop application.
"""
from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv

from scanner import DiskScanner
from ai_auditor import AIAuditor

load_dotenv()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── colour constants ───────────────────────────────────────────────────────────
RISK_FG: Dict[str, str] = {
    "low": "#1d7a1d",
    "medium": "#b07418",
    "high": "#b01818",
}
REC_FG: Dict[str, str] = {
    "delete": "#b01818",
    "backup": "#1a5fa8",
    "keep": "#1d7a1d",
}
ROW_ALT: tuple[str, str] = ("gray17", "gray14")  # alternating row colours


# ── single result row ──────────────────────────────────────────────────────────
class ResultRow:
    """
    Renders one file/folder as a row of widgets inside a CTkScrollableFrame.
    Supports in-place updating when AI audit data arrives.
    """

    COLS = (0, 1, 2, 3, 4, 5)  # Name/Path | Size | Risk | Rec | Description | Delete

    def __init__(
        self,
        parent: ctk.CTkScrollableFrame,
        grid_row: int,
        item: Dict,
        on_delete: Callable[[Dict], None],
        row_parity: int,
    ) -> None:
        self._parent = parent
        self._grid_row = grid_row
        self._item = item
        self._on_delete = on_delete
        self._bg = ROW_ALT[row_parity % 2]
        self._widgets: list = []
        self._render(audit_data=None)

    # ------------------------------------------------------------------ public

    def update_audit(self, audit_data: Optional[Dict]) -> None:
        self._destroy_widgets()
        self._render(audit_data)

    def remove(self) -> None:
        self._destroy_widgets()

    # ------------------------------------------------------------------ private

    def _render(self, audit_data: Optional[Dict]) -> None:
        r = self._grid_row
        p = self._parent
        item = self._item
        bg = self._bg

        # ---- col 0: name + path ----
        safe = item.get("safe_delete", False)
        tag = "[DIR] " if item["type"] == "folder" else "[FILE]"
        safe_tag = "  [SAFE TO DELETE]" if safe else ""
        name_lbl = ctk.CTkLabel(
            p,
            text=f"{tag} {item['name']}{safe_tag}\n{item['path']}",
            anchor="w",
            justify="left",
            wraplength=260,
            fg_color=bg,
            text_color="#2ea82e" if safe else None,
        )
        name_lbl.grid(row=r, column=0, padx=(6, 2), pady=2, sticky="ew")

        # ---- col 1: size ----
        size_lbl = ctk.CTkLabel(p, text=item["size_str"], anchor="e", fg_color=bg, width=75)
        size_lbl.grid(row=r, column=1, padx=2, pady=2, sticky="e")

        # ---- col 2: risk badge ----
        risk = (audit_data or {}).get("risk_level", "")
        risk_lbl = ctk.CTkLabel(
            p,
            text=risk.upper() if risk else "—",
            anchor="center",
            fg_color=RISK_FG.get(risk, "gray30"),
            corner_radius=5,
            width=70,
        )
        risk_lbl.grid(row=r, column=2, padx=2, pady=2, sticky="ew")

        # ---- col 3: recommendation badge ----
        rec = (audit_data or {}).get("recommendation", "")
        rec_lbl = ctk.CTkLabel(
            p,
            text=rec.upper() if rec else "—",
            anchor="center",
            fg_color=REC_FG.get(rec, "gray30"),
            corner_radius=5,
            width=70,
        )
        rec_lbl.grid(row=r, column=3, padx=2, pady=2, sticky="ew")

        # ---- col 4: description ----
        if audit_data:
            desc_text = audit_data.get("description", "")
            desc_color = ("white", "gray90")
        elif safe:
            desc_text = "Temp / cache folder — safe to delete."
            desc_color = ("#2ea82e", "#24862a")
        else:
            desc_text = "Click  Smart Audit (AI)  to analyse this item."
            desc_color = ("gray60", "gray50")
        desc_lbl = ctk.CTkLabel(
            p,
            text=desc_text,
            anchor="w",
            justify="left",
            wraplength=310,
            fg_color=bg,
            text_color=desc_color,
        )
        desc_lbl.grid(row=r, column=4, padx=2, pady=2, sticky="ew")

        # ---- col 5: delete / clean button ----
        is_cleanable = safe and item["type"] == "folder"
        del_btn = ctk.CTkButton(
            p,
            text="Clean" if is_cleanable else "Delete",
            width=70,
            fg_color="#1a6b1a" if is_cleanable else "#7a1515",
            hover_color="#125012" if is_cleanable else "#5a0f0f",
            command=self._confirm_delete,
        )
        del_btn.grid(row=r, column=5, padx=(2, 6), pady=2, sticky="ew")

        self._widgets = [name_lbl, size_lbl, risk_lbl, rec_lbl, desc_lbl, del_btn]

    def _confirm_delete(self) -> None:
        path = self._item["path"]
        safe = self._item.get("safe_delete", False)
        is_folder = self._item["type"] == "folder"

        if safe and is_folder:
            msg = (
                f"Clean the contents of this folder?\n\n"
                f"{path}\n\n"
                f"The folder itself will be kept, only its contents will be deleted."
            )
        elif is_folder:
            msg = (
                f"Permanently delete this folder and all its contents?\n\n"
                f"{path}\n\n"
                f"This action cannot be undone."
            )
        else:
            msg = (
                f"Permanently delete this file?\n\n"
                f"{path}\n\n"
                f"This action cannot be undone."
            )

        if messagebox.askyesno("Confirm", msg, icon="warning"):
            self._on_delete(self._item)

    def _destroy_widgets(self) -> None:
        for w in self._widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._widgets.clear()


# ── main application window ────────────────────────────────────────────────────
class DiskAuditApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Disk Audit & Clean")
        self.geometry("1340x840")
        self.minsize(960, 620)

        self._scanner = DiskScanner()
        self._auditor = AIAuditor()
        self._scan_results: List[Dict] = []
        self._rows: List[ResultRow] = []
        self._page: int = 0
        self._per_page: int = 20
        self._audit_map: Dict[str, Dict] = {}
        self._risk_filter: str = "All"  # "All" | "low" | "medium" | "high"

        self._build_ui()
        self._log("Application started.")
        if not self._auditor.available:
            self._log(
                "WARNING: GEMINI_API_KEY not found — Smart Audit will be unavailable."
            )

    # ================================================================== UI build

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # table row expands

        # ---- control bar ----
        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        ctrl.grid_columnconfigure(0, weight=1)

        self._path_var = ctk.StringVar()
        ctk.CTkEntry(
            ctrl,
            textvariable=self._path_var,
            placeholder_text="Select a drive or folder to scan…",
        ).grid(row=0, column=0, padx=(12, 6), pady=12, sticky="ew")

        ctk.CTkButton(ctrl, text="Browse", width=85, command=self._browse).grid(
            row=0, column=1, padx=6, pady=12
        )

        self._scan_btn = ctk.CTkButton(
            ctrl,
            text="Scan",
            width=85,
            command=self._start_scan,
            fg_color="#1a6b1a",
            hover_color="#125012",
        )
        self._scan_btn.grid(row=0, column=2, padx=6, pady=12)

        self._audit_btn = ctk.CTkButton(
            ctrl,
            text="Smart Audit (AI)",
            width=145,
            command=self._start_audit,
            state="disabled",
            fg_color="#5a2e08",
            hover_color="#3e1f04",
        )
        self._audit_btn.grid(row=0, column=3, padx=6, pady=12)

        ctk.CTkLabel(ctrl, text="Per page:", width=65).grid(
            row=0, column=4, padx=(12, 2), pady=12
        )
        self._per_page_var = ctk.StringVar(value="20")
        ctk.CTkOptionMenu(
            ctrl,
            variable=self._per_page_var,
            values=["10", "20", "50", "100"],
            width=80,
            command=self._on_per_page_changed,
        ).grid(row=0, column=5, padx=(2, 6), pady=12)

        ctk.CTkLabel(ctrl, text="Risk:", width=40).grid(
            row=0, column=6, padx=(6, 2), pady=12
        )
        self._risk_filter_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(
            ctrl,
            variable=self._risk_filter_var,
            values=["All", "Low", "Medium", "High"],
            width=95,
            command=self._on_risk_filter_changed,
        ).grid(row=0, column=7, padx=(2, 12), pady=12)

        # ---- progress bar ----
        prog = ctk.CTkFrame(self, height=36)
        prog.grid(row=1, column=0, padx=12, pady=2, sticky="ew")
        prog.grid_columnconfigure(0, weight=1)

        self._progress = ctk.CTkProgressBar(prog)
        self._progress.grid(row=0, column=0, padx=12, pady=8, sticky="ew")
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(prog, text="Ready", anchor="e", width=220)
        self._status_lbl.grid(row=0, column=1, padx=(4, 12), pady=8)

        # ---- column layout ----
        col_cfg = {
            0: {"weight": 3, "minsize": 260},
            1: {"weight": 0, "minsize": 80},
            2: {"weight": 0, "minsize": 80},
            3: {"weight": 0, "minsize": 80},
            4: {"weight": 4, "minsize": 200},
            5: {"weight": 0, "minsize": 80},
        }

        # ---- scrollable table (header is row 0 inside it) ----
        self._table = ctk.CTkScrollableFrame(self)
        self._table.grid(row=2, column=0, padx=12, pady=(4, 0), sticky="nsew")
        for c, cfg in col_cfg.items():
            self._table.grid_columnconfigure(c, **cfg)

        # Header row (row 0) — stays inside the scrollable frame for alignment
        hdr_bg = "gray22"
        for col, text, anchor, w in (
            (0, "Name / Path", "w", None),
            (1, "Size", "e", 75),
            (2, "Risk", "center", 70),
            (3, "Action", "center", 70),
            (4, "AI Description", "w", None),
            (5, "", "center", 70),
        ):
            lbl = ctk.CTkLabel(
                self._table,
                text=text,
                anchor=anchor,
                font=ctk.CTkFont(weight="bold"),
                fg_color=hdr_bg,
            )
            if w:
                lbl.configure(width=w)
            lbl.grid(row=0, column=col, padx=(6, 2), pady=(4, 6), sticky="ew")

        # placeholder shown before first scan
        self._placeholder = ctk.CTkLabel(
            self._table,
            text="No results yet — select a folder and click  Scan .",
            text_color="gray50",
        )
        self._placeholder.grid(row=1, column=0, columnspan=6, padx=20, pady=40)

        # ---- pagination bar ----
        pag = ctk.CTkFrame(self)
        pag.grid(row=3, column=0, padx=12, pady=2, sticky="ew")
        pag.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(
            pag, text="<< Prev", width=90, command=self._prev_page, state="disabled"
        )
        self._prev_btn.grid(row=0, column=0, padx=(12, 6), pady=6)

        self._page_lbl = ctk.CTkLabel(pag, text="", anchor="center")
        self._page_lbl.grid(row=0, column=1, padx=6, pady=6)

        self._next_btn = ctk.CTkButton(
            pag, text="Next >>", width=90, command=self._next_page, state="disabled"
        )
        self._next_btn.grid(row=0, column=2, padx=(6, 12), pady=6)

        # ---- log ----
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=4, column=0, padx=12, pady=(4, 12), sticky="ew")
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="Status Log",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=10, pady=(6, 0), sticky="w")

        self._log_box = ctk.CTkTextbox(log_frame, height=100, state="disabled")
        self._log_box.grid(row=1, column=0, padx=10, pady=(2, 8), sticky="ew")

    # ================================================================== actions

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="Select Folder or Drive Root")
        if path:
            self._path_var.set(path)

    def _start_scan(self) -> None:
        path = self._path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Invalid Path", "Please select a valid folder or drive.")
            return

        self._clear_rows()
        self._scan_results.clear()
        self._scan_btn.configure(state="disabled", text="Scanning…")
        self._audit_btn.configure(state="disabled")
        self._start_progress()
        self._set_status("Scanning…")

        threading.Thread(target=self._scan_worker, args=(path,), daemon=True).start()

    def _scan_worker(self, path: str) -> None:
        counter = [0]

        def on_progress(p: str) -> None:
            counter[0] += 1
            if counter[0] % 150 == 0:
                short = p if len(p) <= 55 else "…" + p[-54:]
                self.after(0, self._set_status, f"Scanning: {short}")

        try:
            results = self._scanner.scan(path, top_n=0, max_depth=4, on_progress=on_progress)
            self.after(0, self._on_scan_done, results)
        except Exception as exc:
            self.after(0, self._on_scan_error, str(exc))

    def _on_scan_done(self, results: List[Dict]) -> None:
        self._stop_progress()
        self._scan_btn.configure(state="normal", text="Scan")
        # Sort: safe-to-delete first, then by size descending
        results.sort(key=lambda x: (not x.get("safe_delete", False), -x["size"]))
        self._scan_results = results
        self._page = 0
        self._audit_map.clear()

        if not results:
            self._set_status("Scan complete — no items ≥ 1 MB found.")
            self._log("Scan complete. No items ≥ 1 MB found in the selected path.")
            self._update_pagination()
            return

        self._set_status(f"Scan complete — {len(results)} large items found.")
        self._log(f"Scan complete. Found {len(results)} items ≥ 1 MB.")
        self._audit_btn.configure(state="normal")
        self._render_current_page()

    def _on_scan_error(self, msg: str) -> None:
        self._stop_progress()
        self._scan_btn.configure(state="normal", text="Scan")
        self._set_status("Scan failed.")
        self._log(f"ERROR during scan: {msg}")
        messagebox.showerror("Scan Error", msg)

    def _start_audit(self) -> None:
        if not self._scan_results:
            return
        self._audit_btn.configure(state="disabled", text="Auditing…")
        self._start_progress()
        self._set_status("Running AI audit…")
        threading.Thread(target=self._audit_worker, daemon=True).start()

    def _audit_worker(self) -> None:
        try:
            # Audit only items on the current page that haven't been audited yet
            page_items = self._page_slice()
            unaudited = [i for i in page_items if i["name"] not in self._audit_map]
            if unaudited:
                result = self._auditor.audit(unaudited)
            else:
                result = []
            self.after(0, self._on_audit_done, result)
        except Exception as exc:
            self.after(0, self._on_audit_error, str(exc))

    def _on_audit_done(self, audit_list: List[Dict]) -> None:
        self._stop_progress()
        self._audit_btn.configure(state="normal", text="Smart Audit (AI)")
        self._set_status("AI audit complete.")
        self._log(f"AI audit complete. {len(audit_list)} items analysed.")

        self._audit_map.update({item["name"]: item for item in audit_list})
        for row in self._rows:
            row.update_audit(self._audit_map.get(row._item["name"]))

    def _on_audit_error(self, msg: str) -> None:
        self._stop_progress()
        self._audit_btn.configure(state="normal", text="Smart Audit (AI)")
        self._set_status("AI audit failed.")
        self._log(f"ERROR during AI audit: {msg}")
        messagebox.showerror("AI Audit Error", msg)

    def _do_delete(self, item: Dict) -> None:
        path = item["path"]
        safe = item.get("safe_delete", False)
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.remove(path)
                self._log(f"Deleted: {path}")
            elif os.path.isdir(path):
                if safe:
                    # Keep the folder, delete only its contents
                    self._clean_folder(path)
                    self._log(f"Cleaned contents: {path}")
                else:
                    shutil.rmtree(path)
                    self._log(f"Deleted: {path}")
            else:
                raise FileNotFoundError(f"Path no longer exists: {path}")

            # Remove from scan results
            self._scan_results = [r for r in self._scan_results if r["path"] != path]
            self._audit_map.pop(item["name"], None)

            if not self._scan_results:
                self._audit_btn.configure(state="disabled")

            # Clamp page if we deleted the last item on the last page
            if self._page >= self._total_pages and self._page > 0:
                self._page = self._total_pages - 1

            self._render_current_page()

        except Exception as exc:
            self._log(f"ERROR deleting {path}: {exc}")
            messagebox.showerror("Delete Error", str(exc))

    # ================================================================== pagination

    @property
    def _filtered_results(self) -> List[Dict]:
        """Return scan results filtered by current risk selection."""
        if self._risk_filter == "All":
            return self._scan_results
        return [
            item for item in self._scan_results
            if self._audit_map.get(item["name"], {}).get("risk_level", "") == self._risk_filter
        ]

    @property
    def _total_pages(self) -> int:
        filtered = self._filtered_results
        if not filtered:
            return 0
        return max(1, -(-len(filtered) // self._per_page))  # ceil division

    def _page_slice(self) -> List[Dict]:
        filtered = self._filtered_results
        start = self._page * self._per_page
        return filtered[start : start + self._per_page]

    def _render_current_page(self) -> None:
        self._populate_table(self._page_slice())
        self._update_pagination()

    def _update_pagination(self) -> None:
        total = self._total_pages
        filtered = self._filtered_results
        count = len(filtered)
        if total <= 1:
            self._page_lbl.configure(text=f"{count} items" if count else "No matching items")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
        else:
            self._page_lbl.configure(
                text=f"Page {self._page + 1} / {total}  ({count} items)"
            )
            self._prev_btn.configure(state="normal" if self._page > 0 else "disabled")
            self._next_btn.configure(state="normal" if self._page < total - 1 else "disabled")

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_current_page()

    def _next_page(self) -> None:
        if self._page < self._total_pages - 1:
            self._page += 1
            self._render_current_page()

    def _on_per_page_changed(self, value: str) -> None:
        self._per_page = int(value)
        self._page = 0
        if self._scan_results:
            self._render_current_page()

    def _on_risk_filter_changed(self, value: str) -> None:
        self._risk_filter = value.lower() if value != "All" else "All"
        self._page = 0
        if self._scan_results:
            self._render_current_page()

    # ================================================================== helpers

    def _populate_table(self, results: List[Dict]) -> None:
        self._clear_rows()
        if self._placeholder.winfo_exists():
            self._placeholder.grid_remove()
        for i, item in enumerate(results):
            audit_data = self._audit_map.get(item["name"])
            row = ResultRow(
                parent=self._table,
                grid_row=i + 1,  # row 0 is the header
                item=item,
                on_delete=self._do_delete,
                row_parity=i,
            )
            if audit_data:
                row.update_audit(audit_data)
            self._rows.append(row)

    @staticmethod
    def _clean_folder(path: str) -> None:
        """Delete all contents inside *path* but keep the folder itself."""
        for entry in os.scandir(path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path)
                else:
                    os.remove(entry.path)
            except (PermissionError, OSError):
                continue  # skip items that can't be removed

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.remove()
        self._rows.clear()

    def _start_progress(self) -> None:
        self._progress.configure(mode="indeterminate")
        self._progress.start()

    def _stop_progress(self) -> None:
        try:
            self._progress.stop()
        except Exception:
            pass
        self._progress.configure(mode="determinate")
        self._progress.set(1.0)

    def _set_status(self, text: str) -> None:
        self._status_lbl.configure(text=text)

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


# ── entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = DiskAuditApp()
    app.mainloop()
