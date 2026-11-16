"""
main.py — Clean Exit 실행 파일

    python main.py                                      ← 실제 크롬 검사
    python main.py --background                         ← 창 없이 마스코트만 띄우고 시작
    python main.py --user-data-dir "C:\\CleanExitTest"  ← 테스트용 크롬 폴더 검사 (안전)

프로그램 구성 (프로젝트 개요의 해결 아이디어와 같은 순서)
  ① 로그인 흔적 감지 : 크롬에 남은 로그인 상태를 검사 (30초마다 자동으로 다시 검사)
  ② 원클릭 정리     : 버튼 한 번으로 크롬 종료 + 쿠키·비밀번호·방문 기록 등 정리
  ③ 종료 시 경고    : 자리를 비우면 경고 알림, PC를 끌 때는 자동 정리, 프로그램을 끌 때 확인
  + 마스코트 '싹'   : 화면 오른쪽 아래에 항상 떠서 지금 상태를 표정으로 보여 줌
  + 사용 기록       : 기대 효과 확인용 통계를 개인정보 없이 CSV로 저장

[화면이 멈추지 않게 하는 방법]
크롬 종료처럼 몇 초 걸리는 일은 '작업 스레드'에서 하고, 결과는 queue(대기열)에 넣는다.
화면(메인 스레드)은 0.1초마다 대기열을 확인해 결과를 표시한다.
tkinter 화면은 메인 스레드에서만 건드려야 안전하기 때문이다.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import cleaner
import scanner
import winapi
from config import (APP_NAME, APP_SUBTITLE, AUTO_CLEAN_SECONDS, AUTO_SCAN_SECONDS,
                    CLEAN_ON_SHUTDOWN_DEFAULT, IDLE_MINUTES_DEFAULT, MASCOT_NAME,
                    PROFILE_ITEMS, STATS_SAMPLE_MINUTES, SYSTEM_ITEMS)
from mascot import FONT, MascotOverlay, Toast, draw_ssak
from stats import StatsLog

RED, GREEN, ORANGE, GRAY = "#d64550", "#2e9d62", "#e08a00", "#6b7686"
HEADER_BG = "#eaf4fc"

# 마스코트 상태별 안내 문구
STATUS_TEXT = {
    "default": ("✔ 깨끗해요. 안심하고 자리를 떠도 돼요.", GREEN),
    "traces": ("⚠ 로그인 흔적이 남아 있어요. 자리를 뜨기 전에 정리하세요.", RED),
    "waiting": ("⏳ 크롬이 켜져 있어서 정확히 검사할 수 없어요. 다 쓰면 정리하세요.", ORANGE),
    "checking": ("검사하는 중이에요…", GRAY),
    "sweeping": ("정리하는 중이에요…", GRAY),
    "done": ("✔ 깨끗하게 정리했어요!", GREEN),
}


class CleanExitApp:
    def __init__(self, root: tk.Tk, user_data_dir: Path, test_mode: bool, start_hidden: bool):
        self.root = root
        self.user_data_dir = user_data_dir
        self.test_mode = test_mode
        self.stats = StatsLog()

        self.tasks: queue.Queue = queue.Queue()  # 작업 스레드 → 화면으로 결과 전달
        self.busy = False
        self.last_reports: list[scanner.ProfileReport] = []
        self.last_chrome_running = False
        self.last_state = None            # 마지막으로 표시한 상태 (바뀔 때만 말풍선·기록)
        self.toast: Toast | None = None
        self.warned_this_idle = False     # 한 번 자리를 비운 동안 경고는 한 번만
        self.exit_after_clean = False
        self.shutdown_handled = False

        self._build_window()
        self.mascot = MascotOverlay(root, on_click=self.show_window, menu_items=[
            ("창 열기", self.show_window),
            ("지금 검사하기", self.scan),
            ("지금 정리하기 (Clean Exit)", self.clean_exit),
            (None, None),
            ("Clean Exit 끄기", self.quit_app),
        ])

        # 창 닫기(X)는 '숨기기'. 마스코트는 계속 떠 있다.
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        # ③ PC를 끄거나 로그아웃할 때 윈도우가 보내는 신호 (tkinter에서는 WM_SAVE_YOURSELF로 전달됨)
        self.root.protocol("WM_SAVE_YOURSELF", self.on_system_shutdown)
        self.mascot.win.protocol("WM_SAVE_YOURSELF", self.on_system_shutdown)

        if start_hidden:
            self.root.withdraw()
            self.mascot.say(f"안녕! 나는 {MASCOT_NAME}이야. 흔적을 지켜볼게!", 6)

        self.stats.record("프로그램_시작", note="테스트 모드" if test_mode else "")
        self.root.after(100, self._poll_tasks)
        self.root.after(5000, self._watch_idle)
        self.root.after(AUTO_SCAN_SECONDS * 1000, self._auto_scan)
        self.root.after(STATS_SAMPLE_MINUTES * 60_000, self._sample_stats)
        self.scan()

    # =====================================================================
    # 창 만들기
    # =====================================================================
    def _build_window(self):
        root = self.root
        root.title(APP_NAME)
        root.geometry("800x820")
        root.minsize(720, 700)
        style = ttk.Style()
        style.configure(".", font=(FONT, 10))
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"))
        style.configure("Treeview", rowheight=26)
        style.configure("Section.TLabelframe.Label", font=(FONT, 11, "bold"))
        style.configure("Big.TButton", font=(FONT, 12, "bold"), padding=(18, 10))

        # --- 머리말: 마스코트 + 제목 + 현재 상태 ---------------------------------
        header = tk.Frame(root, bg=HEADER_BG, padx=16, pady=10)
        header.pack(fill="x")
        self.header_canvas = tk.Canvas(header, width=130, height=118, bg=HEADER_BG,
                                       highlightthickness=0)
        self.header_canvas.pack(side="left")
        titles = tk.Frame(header, bg=HEADER_BG)
        titles.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(titles, text=APP_NAME, bg=HEADER_BG, fg="#1f2a36",
                 font=(FONT, 22, "bold")).pack(anchor="w")
        tk.Label(titles, text=APP_SUBTITLE, bg=HEADER_BG, fg=GRAY,
                 font=(FONT, 10)).pack(anchor="w")
        self.status_label = tk.Label(titles, text="", bg=HEADER_BG, font=(FONT, 12, "bold"),
                                     anchor="w", justify="left", wraplength=560)
        self.status_label.pack(anchor="w", fill="x", pady=(8, 0))
        if self.test_mode:
            tk.Label(titles, text=f"테스트 모드: {self.user_data_dir}", bg=HEADER_BG,
                     fg=RED, font=(FONT, 9)).pack(anchor="w")

        main = ttk.Frame(root, padding=(16, 10, 16, 12))
        main.pack(fill="both", expand=True)

        # --- ① 로그인 흔적 감지 ---------------------------------------------------
        detect = ttk.LabelFrame(main, text="① 로그인 흔적 감지", padding=10,
                                style="Section.TLabelframe")
        detect.pack(fill="x")
        top = ttk.Frame(detect)
        top.pack(fill="x", pady=(0, 6))
        self.chrome_label = ttk.Label(top, text="크롬 상태 확인 중…", foreground=GRAY)
        self.chrome_label.pack(side="left")
        self.scan_button = ttk.Button(top, text="다시 검사", command=self.scan)
        self.scan_button.pack(side="right")
        columns = ("profile", "account", "sites", "passwords")
        self.tree = ttk.Treeview(detect, columns=columns, show="headings", height=3)
        for col, title, width in [("profile", "크롬 프로필", 110), ("account", "크롬 계정", 90),
                                  ("sites", "로그인된 사이트", 380),
                                  ("passwords", "저장된 비밀번호", 110)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x")

        # --- ② 원클릭 정리 ---------------------------------------------------------
        clean = ttk.LabelFrame(main, text="② 원클릭 정리", padding=10,
                               style="Section.TLabelframe")
        clean.pack(fill="x", pady=(10, 0))
        options = ttk.Frame(clean)
        options.pack(fill="x")
        self.option_vars: dict[str, tk.BooleanVar] = {}
        items = [(k, label, default) for k, (label, default, _) in PROFILE_ITEMS.items()]
        items += [(k, label, default) for k, (label, default) in SYSTEM_ITEMS.items()]
        for i, (key, label, default) in enumerate(items):
            is_system = key in SYSTEM_ITEMS
            var = tk.BooleanVar(value=default and not (is_system and self.test_mode))
            self.option_vars[key] = var
            check = ttk.Checkbutton(options, text=label, variable=var)
            if is_system and self.test_mode:
                check.configure(state="disabled", text=label + "  (테스트 모드에서는 꺼짐)")
            check.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=2)
        actions = ttk.Frame(clean)
        actions.pack(fill="x", pady=(10, 0))
        self.preview_button = ttk.Button(actions, text="미리 보기", command=self.preview)
        self.preview_button.pack(side="left")
        self.clean_button = ttk.Button(actions, text="Clean Exit  (정리하기)",
                                       style="Big.TButton", command=self.clean_exit)
        self.clean_button.pack(side="right")

        # --- ③ 종료 시 경고 --------------------------------------------------------
        guard = ttk.LabelFrame(main, text="③ 종료 시 경고", padding=10,
                               style="Section.TLabelframe")
        guard.pack(fill="x", pady=(10, 0))
        self.guard_var = tk.BooleanVar(value=True)
        self.idle_minutes_var = tk.IntVar(value=IDLE_MINUTES_DEFAULT)
        self.auto_clean_var = tk.BooleanVar(value=False)
        self.shutdown_clean_var = tk.BooleanVar(value=CLEAN_ON_SHUTDOWN_DEFAULT)
        row = ttk.Frame(guard)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="자리 비움 경고: 키보드·마우스 입력이",
                        variable=self.guard_var).pack(side="left")
        ttk.Spinbox(row, from_=1, to=60, width=4,
                    textvariable=self.idle_minutes_var).pack(side="left", padx=4)
        ttk.Label(row, text="분 동안 없으면 알림 띄우기").pack(side="left")
        ttk.Checkbutton(guard, variable=self.auto_clean_var,
                        text=f"알림에 {AUTO_CLEAN_SECONDS}초 동안 응답이 없으면 자동으로 정리하기"
                        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(guard, variable=self.shutdown_clean_var,
                        text="PC를 끌 때 흔적이 남아 있으면 자동으로 정리하기"
                        ).pack(anchor="w", pady=(4, 0))

        # --- 기록 ------------------------------------------------------------------
        log_frame = ttk.LabelFrame(main, text="기록", padding=6, style="Section.TLabelframe")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        footer = ttk.Frame(log_frame)
        footer.pack(fill="x", side="bottom", pady=(6, 0))
        ttk.Button(footer, text="사용 기록(통계) 폴더 열기",
                   command=lambda: self._open_stats_folder()).pack(side="left")
        ttk.Label(footer, text="창을 닫아도 오른쪽 아래의 싹이 계속 지켜봐요.",
                  foreground=GRAY).pack(side="right")
        self.log_text = tk.Text(log_frame, height=6, font=(FONT, 9), state="disabled",
                                wrap="word", relief="flat", bg="#fafbfc")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    # =====================================================================
    # 공통 도구
    # =====================================================================
    def log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _options(self) -> dict[str, bool]:
        return {key: var.get() for key, var in self.option_vars.items()}

    def _set_buttons(self, enabled: bool):
        for button in (self.scan_button, self.preview_button, self.clean_button):
            button.configure(state="normal" if enabled else "disabled")

    def _run_in_background(self, work, on_done):
        """work()를 작업 스레드에서 실행하고, 끝나면 on_done(결과)을 화면 쪽에서 실행한다."""
        if self.busy:
            return False
        self.busy = True
        self._set_buttons(False)

        def runner():
            try:
                self.tasks.put((on_done, work(), None))
            except Exception as error:  # 어떤 오류든 화면에 알려 준다
                self.tasks.put((on_done, None, error))

        threading.Thread(target=runner, daemon=True).start()
        return True

    def _poll_tasks(self):
        try:
            while True:
                on_done, result, error = self.tasks.get_nowait()
                self.busy = False
                self._set_buttons(True)
                if error:
                    self.exit_after_clean = False
                    self.log(f"오류: {error}")
                    self._apply_state(self._state_from_scan(), force=True)
                    messagebox.showerror(APP_NAME, str(error))
                else:
                    on_done(result)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_tasks)

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self):
        self.root.withdraw()
        self.mascot.say("여기 있을게! 나를 누르면 창이 다시 열려.", 5)

    def _open_stats_folder(self):
        self.stats.path.parent.mkdir(parents=True, exist_ok=True)
        winapi.open_in_explorer(self.stats.path.parent)
        self.log(f"사용 기록 파일: {self.stats.path}")

    # =====================================================================
    # 상태 표시 (머리말 + 마스코트)
    # =====================================================================
    def _state_from_scan(self) -> str:
        summary = scanner.summarize(self.last_reports)
        if summary.locked:
            return "waiting"
        if summary.has_traces:
            return "traces"
        return "default"

    def _apply_state(self, state: str, bubble: str | None = None,
                     seconds: float | None = 6, force: bool = False):
        """머리말과 마스코트를 같은 상태로 맞춘다. 상태가 바뀔 때만 말풍선을 띄운다."""
        changed = state != self.last_state
        self.last_state = state
        text, color = STATUS_TEXT[state]
        self.status_label.configure(text=text, fg=color)
        self.header_canvas.delete("all")
        draw_ssak(self.header_canvas, 62, 64, 0.62, state, 0.0)
        if changed or force or bubble:
            if bubble is None:
                bubble, seconds = self._default_bubble(state)
            self.mascot.set_state(state, bubble, seconds)
        else:
            self.mascot.set_state(state)

    def _default_bubble(self, state):
        summary = scanner.summarize(self.last_reports)
        if state == "traces":
            return f"로그인 흔적 {max(1, summary.trace_count)}개 발견!\n나를 눌러서 정리해 줘", None
        if state == "waiting":
            return "크롬 다 쓰면\n나한테 정리를 맡겨 줘!", 8
        if state == "default":
            if not self.last_reports:
                return "크롬 프로필을 못 찾았어", 6
            return "깨끗해! 안심하고 가도 돼", 5
        return None, 6

    # =====================================================================
    # ① 로그인 흔적 감지
    # =====================================================================
    def scan(self, quiet: bool = False):
        directory = self.user_data_dir
        started = self._run_in_background(
            lambda: (scanner.is_chrome_running(), scanner.scan_all(directory)),
            lambda result: self._show_scan(result, quiet),
        )
        if started and not quiet:
            self.log("검사를 시작합니다.")
            self._apply_state("checking", "흔적이 있나 볼게…", None)

    def _auto_scan(self):
        if not self.busy and self.toast is None and self.last_state not in ("done", "sweeping"):
            self.scan(quiet=True)
        self.root.after(AUTO_SCAN_SECONDS * 1000, self._auto_scan)

    def _show_scan(self, result, quiet=False):
        chrome_running, reports = result
        self._fill_table(reports, chrome_running)

        state = self._state_from_scan()
        changed = state != self.last_state
        if not quiet or changed:
            if not reports:
                self.log(f"크롬 프로필을 찾지 못했습니다: {self.user_data_dir}")
            elif state == "default":
                self.log("로그인 흔적이 없습니다.")
            self._log_traces(reports)
            self.stats.record("상태_변화" if quiet else "검사", reports, chrome_running)
        self._apply_state(state, force=not quiet)

    def _log_traces(self, reports):
        for r in reports:
            if r.has_traces:
                self.log(f"[{r.name}] " + self._describe(r))

    def _fill_table(self, reports, chrome_running):
        """검사 결과를 저장하고 ① 표에 표시한다."""
        self.last_reports, self.last_chrome_running = reports, chrome_running
        self.chrome_label.configure(
            text="크롬 상태: 실행 중" if chrome_running else "크롬 상태: 꺼져 있음")

        self.tree.delete(*self.tree.get_children())
        for r in reports:
            if r.locked:
                sites, passwords = "확인 불가 (크롬이 켜져 있어 파일이 잠김)", "확인 불가"
            elif r.error:
                sites, passwords = r.error, "-"
            else:
                sites = ", ".join(r.sites) if r.sites else "없음"
                passwords = f"{r.saved_passwords}개" if r.saved_passwords else "없음"
            self.tree.insert("", "end", values=(
                r.name, "연결됨" if r.chrome_signed_in else "없음", sites, passwords))

    @staticmethod
    def _describe(r: scanner.ProfileReport) -> str:
        parts = []
        if r.locked:
            parts.append("크롬이 켜져 있어 확인하지 못함")
        if r.sites:
            parts.append("로그인: " + ", ".join(r.sites))
        if r.chrome_signed_in:
            parts.append("크롬에 계정 연결됨")
        if r.saved_passwords:
            parts.append(f"저장된 비밀번호 {r.saved_passwords}개")
        if r.error:
            parts.append(r.error)
        return " / ".join(parts)

    # =====================================================================
    # ② 원클릭 정리
    # =====================================================================
    def preview(self):
        plan = cleaner.plan_cleanup(self.user_data_dir, self._options(),
                                    include_system=not self.test_mode)
        if not plan:
            self.log("[미리 보기] 지울 항목이 없습니다.")
            return
        self.log(f"[미리 보기] {len(plan)}개 항목을 지울 예정입니다.")
        for item in plan[:30]:
            self.log(f"  · {item.label}: {item.path.name}")
        if len(plan) > 30:
            self.log(f"  · … 외 {len(plan) - 30}개")

    def clean_exit(self, ask: bool = True, trigger: str = "버튼"):
        options = self._options()
        if not any(options.values()):
            self.exit_after_clean = False
            messagebox.showinfo(APP_NAME, "정리할 항목을 하나 이상 선택해 주세요.")
            return
        if ask:
            message = ("크롬 창을 모두 닫고 선택한 항목을 정리합니다.\n"
                       "크롬에서 작성 중이던 내용은 저장되지 않아요.\n\n계속할까요?")
            if options.get("downloads") and not self.test_mode:
                message += "\n\n⚠ 다운로드 폴더의 파일이 실제로 삭제됩니다."
            if not messagebox.askyesno(APP_NAME, message, icon="warning"):
                return

        directory, include_system = self.user_data_dir, not self.test_mode

        def work():
            if not cleaner.close_chrome():
                raise RuntimeError("크롬을 종료하지 못했어요. 크롬을 직접 닫고 다시 시도해 주세요.")
            results = cleaner.execute_cleanup(
                cleaner.plan_cleanup(directory, options, include_system))
            return results, scanner.is_chrome_running(), scanner.scan_all(directory)

        if self._run_in_background(work, lambda result: self._show_cleanup(result, trigger)):
            self.log(f"정리를 시작합니다. ({trigger})")
            self._apply_state("sweeping", "쓱싹쓱싹… 정리하는 중!", None)

    def _show_cleanup(self, result, trigger):
        results, chrome_running, reports = result
        done = sum(1 for _, status in results if status == "삭제함")
        failed = [(item, status) for item, status in results if status.startswith("실패")]
        self.log(f"정리 완료: {done}개 삭제, {len(failed)}개 실패")
        for item, status in failed:
            self.log(f"  · {item.label} ({item.path.name}): {status}")
        self.stats.record("정리", reports, chrome_running,
                          note=f"{trigger} / 삭제 {done} / 실패 {len(failed)}")

        self._fill_table(reports, chrome_running)
        if scanner.summarize(reports).has_traces:
            self.log("정리 후에도 남은 흔적이 있습니다.")
            self._log_traces(reports)
            self._apply_state(self._state_from_scan(), force=True)
        else:
            self._apply_state("done", "싹 치웠어! 잘 가~", 5)
            self.root.after(5000, lambda: self.last_state == "done" and self._apply_state("default"))

        if self.exit_after_clean:
            self.root.after(1500, self._final_exit)

    # =====================================================================
    # ③ 종료 시 경고
    # =====================================================================
    def _watch_idle(self):
        """5초마다 자리 비움을 확인한다."""
        try:
            limit = max(1, int(self.idle_minutes_var.get())) * 60
        except (tk.TclError, ValueError):
            limit = IDLE_MINUTES_DEFAULT * 60

        seconds = winapi.idle_seconds()
        if seconds < limit:
            self.warned_this_idle = False  # 다시 사용하기 시작함
        elif (self.guard_var.get() and not self.warned_this_idle
              and not self.busy and self.toast is None):
            self.warned_this_idle = True
            directory = self.user_data_dir
            self._run_in_background(
                lambda: (scanner.is_chrome_running(), scanner.scan_all(directory)),
                self._after_idle_scan,
            )
        self.root.after(5000, self._watch_idle)

    def _after_idle_scan(self, result):
        self._show_scan(result, quiet=True)
        chrome_running, reports = result
        if chrome_running or scanner.summarize(reports).has_traces:
            self.stats.record("자리비움_경고", reports, chrome_running)
            self.log("자리 비움이 감지되어 알림을 띄웠습니다.")
            self._show_idle_toast(reports, chrome_running)

    def _show_idle_toast(self, reports, chrome_running):
        toast = Toast(self.root)
        self.toast = toast
        self.mascot.set_state("traces", "저기요! 로그인이\n남아 있어요!", None)
        toast.label("자리를 비우셨나요?", size=14, bold=True)
        reasons = [self._describe(r) for r in reports if r.has_traces]
        if chrome_running and not reasons:
            reasons.append("크롬이 켜져 있어요")
        toast.label("\n".join("· " + x for x in reasons), color=RED).pack_configure(pady=(6, 0))
        countdown = toast.label("", color=GRAY)

        def close(answer):
            if self.toast is toast:
                self.toast = None
                toast.destroy()
                self.stats.record("경고_응답", note=answer)

        def clean_now():
            close("지금 정리")
            self.clean_exit(ask=False, trigger="자리 비움 알림")

        def still_using():
            close("아직 사용 중")
            self._apply_state(self._state_from_scan(), force=True)

        toast.buttons([("지금 정리하기", clean_now, True), ("아직 사용 중이에요", still_using, False)])
        toast.show(above_y=self.mascot.top_y())

        if self.auto_clean_var.get():
            remaining = [AUTO_CLEAN_SECONDS]

            def tick():
                if self.toast is not toast:
                    return
                if remaining[0] <= 0:
                    close("응답 없음 → 자동 정리")
                    self.clean_exit(ask=False, trigger="자리 비움 자동")
                    return
                countdown.configure(text=f"{remaining[0]}초 뒤 자동으로 정리합니다.")
                remaining[0] -= 1
                self.root.after(1000, tick)

            tick()

    def on_system_shutdown(self):
        """
        PC를 끄거나 로그아웃할 때 호출된다.
        윈도우는 이 함수가 끝날 때까지 종료를 기다리므로, 여기서는 스레드 없이 바로 정리한다.
        종료 화면에는 'Clean Exit: 로그인 흔적을 정리하고 있어요'라는 안내가 표시된다.
        """
        if self.shutdown_handled or not self.shutdown_clean_var.get():
            return
        self.shutdown_handled = True
        reports = scanner.scan_all(self.user_data_dir)
        if not (scanner.is_chrome_running() or scanner.summarize(reports).has_traces):
            self.stats.record("PC_종료", reports, False, note="흔적 없음")
            return

        winapi.block_shutdown(self.mascot.win, "Clean Exit: 로그인 흔적을 정리하고 있어요")
        try:
            self.mascot.set_state("sweeping", "PC 끄기 전에\n정리할게요!", None)
            self.mascot.redraw_now()
            cleaner.close_chrome(timeout=4)
            results = cleaner.execute_cleanup(cleaner.plan_cleanup(
                self.user_data_dir, self._options(), not self.test_mode))
            done = sum(1 for _, status in results if status == "삭제함")
            self.stats.record("정리", scanner.scan_all(self.user_data_dir), None,
                              note=f"PC 종료 시 자동 / 삭제 {done}")
        finally:
            winapi.unblock_shutdown(self.mascot.win)

    def _sample_stats(self):
        """기대 효과 계산용: 일정 간격마다 '지금 흔적이 있는지'를 한 줄씩 기록"""
        if self.last_reports:
            self.stats.record("정기_기록", self.last_reports, self.last_chrome_running)
        self.root.after(STATS_SAMPLE_MINUTES * 60_000, self._sample_stats)

    # =====================================================================
    # 프로그램 끄기
    # =====================================================================
    def quit_app(self):
        if self.busy:
            return
        if scanner.summarize(self.last_reports).has_traces:
            self.show_window()
            answer = messagebox.askyesnocancel(
                APP_NAME,
                "로그인 흔적이 남아 있어요.\n정리하고 끌까요? (크롬이 닫혀요)\n\n"
                "예: 정리 후 끄기   아니요: 그냥 끄기   취소: 돌아가기",
                icon="warning")
            if answer is None:
                return
            if answer:
                self.exit_after_clean = True
                self.clean_exit(ask=False, trigger="프로그램 종료")
                return
        self._final_exit()

    def _final_exit(self):
        self.stats.record("프로그램_종료")
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--user-data-dir", type=Path, help="검사할 크롬 User Data 폴더 (테스트용)")
    parser.add_argument("--background", action="store_true", help="창 없이 마스코트만 띄우고 시작")
    args = parser.parse_args()

    winapi.enable_dpi_awareness()
    root = tk.Tk()
    # 창 아이콘(싹). exe로 만들었을 때는 PyInstaller가 파일을 풀어 둔 임시 폴더에서 찾는다.
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "ssak.ico"
    try:
        root.iconbitmap(default=str(icon))
    except tk.TclError:
        pass
    if args.user_data_dir:
        CleanExitApp(root, args.user_data_dir, test_mode=True, start_hidden=args.background)
    else:
        CleanExitApp(root, scanner.default_user_data_dir(), test_mode=False,
                     start_hidden=args.background)
    root.mainloop()


if __name__ == "__main__":
    main()
