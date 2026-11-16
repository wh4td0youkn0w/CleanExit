"""
winapi.py — 윈도우 기능 연결

Python에 기본으로 들어 있는 ctypes로 윈도우 API를 직접 호출한다. (별도 설치 필요 없음)
  - idle_seconds()     : 키보드·마우스를 마지막으로 쓴 뒤 몇 초가 지났는지 (자리 비움 감지)
  - block_shutdown()   : PC를 끌 때 "정리 중" 안내를 띄우고 정리할 시간을 잠깐 확보
  - enable_dpi_awareness(): 고해상도 화면에서 글자가 흐릿하지 않게
윈도우가 아닌 환경(개발·테스트용)에서는 아무 일도 하지 않는다.
"""

import ctypes
import os

IS_WINDOWS = os.name == "nt"


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """마지막 입력 이후 지난 시간(초)."""
    if not IS_WINDOWS:
        return 0.0
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    get_tick_count = ctypes.windll.kernel32.GetTickCount
    get_tick_count.restype = ctypes.c_uint  # 부호 없는 32비트 값
    # 두 값 모두 '컴퓨터를 켠 뒤 지난 밀리초'. 약 49일마다 0으로 돌아가므로 32비트로 맞춰 뺀다.
    return ((get_tick_count() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def _window_handle(widget) -> int:
    """tkinter 창의 실제 윈도우 핸들(HWND)을 구한다."""
    GA_ROOT = 2
    return ctypes.windll.user32.GetAncestor(widget.winfo_id(), GA_ROOT)


def block_shutdown(widget, reason: str) -> bool:
    """PC 종료 화면에 '정리 중' 이유를 보여 주며 종료를 잠깐 붙잡는다."""
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        user32.ShutdownBlockReasonCreate.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        return bool(user32.ShutdownBlockReasonCreate(_window_handle(widget), reason))
    except (AttributeError, OSError):
        return False


def unblock_shutdown(widget) -> None:
    if not IS_WINDOWS:
        return
    try:
        user32 = ctypes.windll.user32
        user32.ShutdownBlockReasonDestroy.argtypes = [ctypes.c_void_p]
        user32.ShutdownBlockReasonDestroy(_window_handle(widget))
    except (AttributeError, OSError):
        pass


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def open_in_explorer(path) -> None:
    """파일 탐색기로 폴더를 연다."""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: 윈도우 전용 함수
