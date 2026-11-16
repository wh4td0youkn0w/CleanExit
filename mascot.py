"""
mascot.py — 마스코트 '싹'

하늘색 솜뭉치 '싹'을 tkinter Canvas에 도형(원·선·다각형)으로 직접 그린다.
그림 파일 없이 코드로 그리기 때문에 크기를 바꿔도 깨지지 않고, 상태에 따라 표정과 소품이 바뀐다.

상태 6가지
  default  기본       : 흔적 없이 깨끗할 때 (초록 체크)
  traces   흔적 발견  : 로그인이 남아 있을 때 (빨간 느낌표, 식은땀)
  checking 확인 중    : 검사하는 동안 (말줄임표)
  waiting  크롬 사용 중: 크롬이 켜져 있어 기다릴 때 (주황 시계)
  sweeping 정리 중    : 흔적을 치우는 동안 (빗자루질, 먼지)
  done     정리 완료  : 깨끗해졌을 때 (손 흔들기, 반짝이)

[좌표 그리는 방법]
디자인 시안을 그릴 때 쓴 좌표(캐릭터 중심이 (340, 172))를 그대로 쓰고,
Pen 클래스가 원하는 위치·크기로 옮겨서 그려 준다.
"""

from __future__ import annotations

import math
import time
import tkinter as tk

FONT = "Malgun Gothic"

# --- 색 ---------------------------------------------------------------------
BODY, BODY_LINE, FEET = "#d9eefc", "#8cc3e8", "#bfe2f8"
INK, WHITE, CHEEK = "#2b3442", "#ffffff", "#ffc4d3"
STICK, BRUSH, BRUSH_LINE = "#d4a373", "#ffe08a", "#e0b44c"
GREEN, RED, ORANGE = "#7fd6a8", "#f2777f", "#ffb84d"
DOT, DOT_ACTIVE, SPARKLE, DUST = "#c3c9d3", "#6b7686", "#ffd166", "#dfe3ea"
TRANSPARENT_KEY = "#fe01fe"   # 오버레이 창에서 이 색은 투명하게 처리된다

STATE_LABELS = {
    "default": "기본", "traces": "흔적 발견", "checking": "확인 중",
    "waiting": "크롬 사용 중", "sweeping": "정리 중", "done": "정리 완료",
}

# 솜뭉치 몸통 = 원 여러 개를 겹친 모양 (중심x, 중심y, 가로 반지름, 세로 반지름)
BODY_PUFFS = [
    (340, 184, 58, 46), (310, 136, 22, 22), (341, 126, 22, 22), (374, 138, 22, 22),
    (284, 180, 20, 20), (396, 180, 20, 20), (316, 214, 20, 20), (364, 214, 20, 20),
]
BROOM_STICK = [(404, 150), (414, 216)]
BROOM_HEAD = [(402, 210), (414, 206), (426, 210), (430, 236), (414, 240), (398, 236)]
BROOM_BRISTLES = [[(408, 214), (406, 236)], [(414, 213), (414, 238)], [(420, 214), (422, 236)]]
HAND = (402, 186)


class Pen:
    """시안 좌표를 캔버스 좌표로 바꿔서 그려 주는 도구"""

    def __init__(self, canvas, ox: float, oy: float, scale: float, tag: str):
        self.canvas, self.ox, self.oy, self.s, self.tag = canvas, ox, oy, scale, tag

    def p(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + (x - 340) * self.s, self.oy + (y - 172) * self.s

    def _w(self, width: float) -> float:
        return max(1.0, width * self.s)

    def oval(self, cx, cy, rx, ry, fill, outline="", width=0):
        x1, y1 = self.p(cx - rx, cy - ry)
        x2, y2 = self.p(cx + rx, cy + ry)
        self.canvas.create_oval(x1, y1, x2, y2, fill=fill, outline=outline,
                                width=self._w(width) if outline else 0, tags=self.tag)

    def line(self, points, fill, width, smooth=False):
        coords = [c for x, y in points for c in self.p(x, y)]
        self.canvas.create_line(*coords, fill=fill, width=self._w(width), smooth=smooth,
                                capstyle="round", joinstyle="round", tags=self.tag)

    def polygon(self, points, fill, outline="", width=0, smooth=False):
        coords = [c for x, y in points for c in self.p(x, y)]
        self.canvas.create_polygon(*coords, fill=fill, outline=outline, smooth=smooth,
                                   width=self._w(width) if outline else 0, tags=self.tag)


def _rotate(points, degrees, cx, cy):
    r = math.radians(degrees)
    c, s = math.cos(r), math.sin(r)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c)
            for x, y in points]


def _star(pen: Pen, cx, cy, size, fill):
    k = size * 0.3
    pen.polygon([(cx, cy - size), (cx + k, cy - k), (cx + size, cy), (cx + k, cy + k),
                 (cx, cy + size), (cx - k, cy + k), (cx - size, cy), (cx - k, cy - k)], fill)


# =========================================================================
# 싹 그리기
# =========================================================================
def draw_ssak(canvas, ox, oy, scale, state="default", t=0.0, blink=False, tag="ssak"):
    """(ox, oy)를 중심으로 scale 크기의 '싹'을 그린다. t는 애니메이션 시간(초)."""
    pen = Pen(canvas, ox, oy, scale, tag)

    # 몸통: 테두리 색의 조금 큰 원들을 먼저 그리고, 그 위에 몸통 색 원들을 겹치면
    # 원끼리 겹친 안쪽 선은 가려지고 바깥 테두리만 남는다.
    for cx, cy, rx, ry in BODY_PUFFS:
        pen.oval(cx, cy, rx + 2.5, ry + 2.5, BODY_LINE)
    for cx, cy, rx, ry in BODY_PUFFS:
        pen.oval(cx, cy, rx, ry, BODY)
    for fx in (320, 358):
        pen.oval(fx, 236, 13, 6, FEET, BODY_LINE, 2)

    _draw_face(pen, state, t, blink)
    _draw_broom(pen, state, t)
    _draw_extras(pen, state, t)


def _eyes(pen, big=False, look=(0, 0), single_highlight=False):
    rx, ry, hl = (10, 12, 4.0) if big else (9, 11, 3.6)
    dx, dy = look
    for ex in (318, 362):
        pen.oval(ex + dx, 176 + dy, rx, ry, INK)
        pen.oval(ex + dx + 3, 171 + dy, hl, hl, WHITE)
        if not single_highlight:
            pen.oval(ex + dx - 3, 180 + dy, 1.6, 1.6, WHITE)


def _eyes_closed(pen):
    pen.line([(309, 178), (327, 178)], INK, 2.6)
    pen.line([(353, 178), (371, 178)], INK, 2.6)


def _eyes_happy(pen):
    pen.line([(308, 180), (318, 168), (328, 180)], INK, 2.8, smooth=True)
    pen.line([(352, 180), (362, 168), (372, 180)], INK, 2.8, smooth=True)


def _cheeks(pen, y=196):
    pen.oval(302, y, 11, 6, CHEEK)
    pen.oval(378, y, 11, 6, CHEEK)


def _smile(pen):
    pen.line([(334, 193), (340, 200), (346, 193)], INK, 2.4, smooth=True)


def _open_mouth(pen, depth=9):
    pen.polygon([(333, 192), (336, 192 + depth * 0.7), (340, 192 + depth),
                 (344, 192 + depth * 0.7), (347, 192)], INK)


def _draw_face(pen, state, t, blink):
    if state == "traces":
        _cheeks(pen, 198)
        pen.line([(306, 158), (326, 151)], INK, 2.4)
        pen.line([(354, 151), (374, 158)], INK, 2.4)
        _eyes_closed(pen) if blink else _eyes(pen, big=True)
        pen.line([(331, 197), (335.5, 192), (340, 197), (344.5, 202), (349, 197)],
                 INK, 2.4, smooth=True)
    elif state == "checking":
        _cheeks(pen)
        _eyes_closed(pen) if blink else _eyes(pen, look=(2, -2))
        pen.line([(335, 196), (347, 196)], INK, 2.4)
    elif state == "waiting":
        _cheeks(pen)
        _eyes_closed(pen)
        _smile(pen)
    elif state == "sweeping":
        _cheeks(pen)
        pen.line([(307, 152), (327, 159)], INK, 2.4)
        pen.line([(353, 159), (373, 152)], INK, 2.4)
        _eyes(pen, single_highlight=True)
        _open_mouth(pen, 9)
    elif state == "done":
        _cheeks(pen)
        _eyes_happy(pen)
        _open_mouth(pen, 11)
    else:  # default
        _cheeks(pen)
        _eyes_closed(pen) if blink else _eyes(pen)
        _smile(pen)


def _draw_broom(pen, state, t):
    angle = 22 + 16 * math.sin(t * 9) if state == "sweeping" else 0
    hx, hy = HAND
    pen.line(_rotate(BROOM_STICK, angle, hx, hy), STICK, 5)
    pen.polygon(_rotate(BROOM_HEAD, angle, hx, hy), BRUSH, BRUSH_LINE, 2)
    for bristle in BROOM_BRISTLES:
        pen.line(_rotate(bristle, angle, hx, hy), BRUSH_LINE, 1.4)
    pen.oval(hx, hy, 9, 8, BODY, BODY_LINE, 2.5)  # 빗자루를 쥔 손


def _badge(pen, color):
    pen.oval(290, 104, 14, 14, color)


def _draw_extras(pen, state, t):
    if state == "default":
        _badge(pen, GREEN)
        pen.line([(283, 104), (288, 109), (297, 99)], WHITE, 3)
    elif state == "traces":
        _badge(pen, RED)
        pen.line([(290, 96), (290, 104)], WHITE, 5)
        pen.oval(290, 111, 2.6, 2.6, WHITE)
        drop_y = 2 * math.sin(t * 3)  # 식은땀이 살짝 흔들림
        pen.polygon([(394, 128 + drop_y), (399, 138 + drop_y), (398, 145 + drop_y),
                     (394, 148 + drop_y), (390, 145 + drop_y), (389, 138 + drop_y)],
                    "#9fd3f7", "#6fb3e0", 1.5, smooth=True)
    elif state == "checking":
        pen.oval(290, 103, 28, 15, WHITE, "#c5ccd6", 2)
        active = int(t * 3) % 3  # 점이 하나씩 차례로 진해짐
        for i, dx in enumerate((278, 290, 302)):
            pen.oval(dx, 103, 3.5, 3.5, DOT_ACTIVE if i == active else DOT)
    elif state == "waiting":
        _badge(pen, ORANGE)
        a = math.radians(t * 90)  # 시곗바늘이 천천히 돈다
        pen.line([(290, 104), (290 + 8 * math.sin(a), 104 - 8 * math.cos(a))], WHITE, 2.6)
        pen.line([(290, 104), (296, 107)], WHITE, 2.6)
    elif state == "sweeping":
        if math.sin(t * 9) > 0:
            puffs = [(384, 242, 7), (374, 248, 5), (394, 250, 5)]
        else:
            puffs = [(436, 244, 6), (446, 250, 4), (426, 252, 4)]
        for cx, cy, r in puffs:
            pen.oval(cx, cy, r, r, DUST)
        pen.line([(428, 196), (436, 206), (432, 218)], BODY_LINE, 2.4, smooth=True)
        pen.line([(438, 192), (448, 206), (442, 224)], BODY_LINE, 2.4, smooth=True)
    elif state == "done":
        wave = 5 * math.sin(t * 10)  # 손 흔들기
        pen.oval(270, 150 + wave, 9, 8, BODY, BODY_LINE, 2.5)
        pen.line([(254, 136 + wave), (250, 146 + wave), (256, 154 + wave)],
                 BODY_LINE, 2.2, smooth=True)
        twinkle = 0.8 + 0.2 * math.sin(t * 6)
        _star(pen, 300, 92, 10 * twinkle, SPARKLE)
        _star(pen, 384, 100, 8 * (1.8 - twinkle), SPARKLE)
        pen.oval(268, 118, 3, 3, GREEN)
        pen.oval(406, 128, 3, 3, GREEN)


def _round_rect_points(x1, y1, x2, y2, r):
    """smooth=True 다각형으로 그리면 모서리가 둥근 사각형이 되는 점 목록"""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# =========================================================================
# 화면 위에 떠 있는 '싹' (오버레이)
# =========================================================================
class MascotOverlay:
    """
    제목 표시줄 없는 투명 창에 '싹'과 말풍선을 그린다.
    - 항상 다른 창보다 위에 있고, 배경은 투명해서 캐릭터만 보인다.
    - 왼쪽 클릭: on_click 실행 / 끌기: 위치 옮기기 / 오른쪽 클릭: 메뉴
    """

    W, H = 360, 165
    SCALE = 0.75
    FPS_MS = 66  # 약 15프레임/초

    def __init__(self, root, on_click, menu_items):
        self.on_click = on_click
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)          # 제목 표시줄·테두리 없애기
        self.win.attributes("-topmost", True)    # 항상 위
        try:
            self.win.attributes("-transparentcolor", TRANSPARENT_KEY)  # 이 색을 투명하게 (윈도우)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H, bg=TRANSPARENT_KEY,
                                highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack()

        x = self.win.winfo_screenwidth() - self.W - 16
        y = self.win.winfo_screenheight() - self.H - 56  # 작업 표시줄 위
        self.win.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.state = "checking"
        self.bubble_text: str | None = None
        self.bubble_until: float | None = None
        self.started = time.time()
        self.next_blink = self.started + 3
        self.blink_until = 0.0
        self._drag_start = None

        self.menu = tk.Menu(self.win, tearoff=0)
        for label, command in menu_items:
            if label is None:
                self.menu.add_separator()
            else:
                self.menu.add_command(label=label, command=command)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._tick()

    # --- 바깥에서 쓰는 기능 -------------------------------------------------
    def set_state(self, state: str, bubble: str | None = None, seconds: float | None = 6):
        self.state = state
        if bubble:
            self.say(bubble, seconds)

    def say(self, text: str, seconds: float | None = 6):
        """말풍선 띄우기. seconds=None이면 다음 말풍선이 올 때까지 계속 표시."""
        self.bubble_text = text
        self.bubble_until = None if seconds is None else time.time() + seconds

    def hide_bubble(self):
        self.bubble_text = None

    def redraw_now(self):
        self._redraw()
        self.win.update_idletasks()

    def top_y(self) -> int:
        return self.win.winfo_y()

    # --- 마우스 ---------------------------------------------------------------
    def _on_press(self, event):
        self._drag_start = (event.x_root, event.y_root, self.win.winfo_x(), self.win.winfo_y())

    def _on_drag(self, event):
        if self._drag_start:
            sx, sy, wx, wy = self._drag_start
            self.win.geometry(f"+{wx + event.x_root - sx}+{wy + event.y_root - sy}")

    def _on_release(self, event):
        if self._drag_start:
            sx, sy, _, _ = self._drag_start
            moved = abs(event.x_root - sx) + abs(event.y_root - sy)
            self._drag_start = None
            if moved < 5:  # 거의 안 움직였으면 '클릭'으로 본다
                self.on_click()

    # --- 애니메이션 -----------------------------------------------------------
    def _tick(self):
        try:
            self._redraw()
        except tk.TclError:
            return  # 창이 닫힘
        self.win.after(self.FPS_MS, self._tick)

    def _redraw(self):
        now = time.time()
        t = now - self.started
        c = self.canvas
        c.delete("all")

        if self.bubble_text and (self.bubble_until is None or now < self.bubble_until):
            self._draw_bubble(self.bubble_text)

        if now >= self.next_blink:  # 3~5초마다 눈 깜빡
            self.blink_until = now + 0.15
            self.next_blink = now + 3 + (int(now * 1000) % 2000) / 1000
        blink = now < self.blink_until

        bob = 2.5 * math.sin(t * 2.6)  # 숨 쉬듯 위아래로
        draw_ssak(c, self.W - 86, 84 + bob, self.SCALE, self.state, t, blink)

    def _draw_bubble(self, text):
        c = self.canvas
        right, cy = 196, 78
        label = c.create_text(right - 92, cy, text=text, width=170, justify="center",
                              font=(FONT, 10, "bold"), fill=INK)
        x1, y1, x2, y2 = c.bbox(label)
        x1, y1, x2, y2 = x1 - 12, y1 - 9, x2 + 12, y2 + 9
        c.create_polygon(x2 - 3, cy - 8, x2 + 12, cy + 2, x2 - 3, cy + 9,
                         fill=WHITE, outline=BODY_LINE, width=2)               # 꼬리
        c.create_polygon(*_round_rect_points(x1, y1, x2, y2, 14), smooth=True,
                         fill=WHITE, outline=BODY_LINE, width=2)               # 말풍선
        c.tag_raise(label)


# =========================================================================
# 오른쪽 아래에서 미끄러져 나오는 경고 알림
# =========================================================================
class Toast:
    """
    제목 표시줄 없는 작은 알림 창. 마스코트 위쪽에 오른쪽에서 미끄러져 들어온다.
    body 프레임에 원하는 내용을 넣은 뒤 show()를 호출한다.
    """

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        border = tk.Frame(self.win, bg=BODY_LINE, padx=2, pady=2)
        border.pack()
        self.body = tk.Frame(border, bg=WHITE, padx=20, pady=16)
        self.body.pack()

    def label(self, text, size=10, bold=False, color=INK):
        widget = tk.Label(self.body, text=text, bg=WHITE, fg=color, justify="left",
                          font=(FONT, size, "bold" if bold else "normal"))
        widget.pack(anchor="w")
        return widget

    def buttons(self, items):
        """items: [(글자, 명령, 강조여부), ...]"""
        row = tk.Frame(self.body, bg=WHITE)
        row.pack(anchor="w", pady=(12, 0))
        for text, command, primary in items:
            tk.Button(row, text=text, command=command, relief="flat", cursor="hand2",
                      padx=14, pady=6, font=(FONT, 10, "bold" if primary else "normal"),
                      bg="#4aa3df" if primary else "#eef2f6",
                      fg=WHITE if primary else INK,
                      activebackground="#3b8fc8" if primary else "#dde3ea").pack(side="left", padx=(0, 8))

    def show(self, above_y: int):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        screen_w = self.win.winfo_screenwidth()
        target_x, y = screen_w - w - 20, max(10, above_y - h - 4)
        steps = 12

        def slide(i=0):
            try:
                x = int(screen_w - (screen_w - target_x) * (1 - (1 - i / steps) ** 3))
                self.win.geometry(f"+{x}+{y}")
                if i < steps:
                    self.win.after(15, slide, i + 1)
            except tk.TclError:
                pass

        slide()
        self.win.lift()

    def destroy(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
