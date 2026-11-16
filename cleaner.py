"""
cleaner.py — 로그인 흔적 정리

1) 크롬을 종료하고 (켜져 있으면 파일이 잠겨서 지울 수 없음)
2) 선택한 항목의 파일·폴더를 지운다.

[안전장치]
- '정리 계획(plan)'을 먼저 만들고, 그 계획대로만 지운다. → '미리 보기'에서 무엇이 지워질지 확인 가능
- 지우기 직전에 대상이 허용된 폴더(프로필 폴더, 최근 파일 폴더, 다운로드 폴더) 안에 있는지 다시 확인한다.
- 바로가기(심볼릭 링크)는 링크만 지우고, 링크가 가리키는 원본은 건드리지 않는다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from config import PROFILE_ITEMS, SYSTEM_ITEMS
from scanner import is_chrome_running, list_profiles, profile_display_name


# ---------------------------------------------------------------------------
# 크롬 종료
# ---------------------------------------------------------------------------
def close_chrome(timeout: float = 8.0) -> bool:
    """
    크롬을 종료한다. 먼저 '정상 종료'를 요청하고, 그래도 남아 있으면 강제 종료한다.
    종료에 성공하면(또는 원래 꺼져 있었으면) True.
    """
    if not is_chrome_running():
        return True
    if os.name != "nt":
        return False  # 이 프로그램의 종료 기능은 윈도우 전용

    no_window = subprocess.CREATE_NO_WINDOW
    # 1단계: 정상 종료 요청 (창 닫기 버튼을 누른 것과 비슷)
    subprocess.run(["taskkill", "/IM", "chrome.exe", "/T"],
                   capture_output=True, creationflags=no_window)
    if _wait_until_closed(timeout / 2):
        return True
    # 2단계: 강제 종료
    subprocess.run(["taskkill", "/IM", "chrome.exe", "/T", "/F"],
                   capture_output=True, creationflags=no_window)
    return _wait_until_closed(timeout / 2)


def _wait_until_closed(seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not is_chrome_running():
            time.sleep(1.0)  # 크롬이 파일 잠금을 완전히 풀 때까지 잠깐 기다림
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# 정리 계획 만들기
# ---------------------------------------------------------------------------
def downloads_dir() -> Path:
    return Path.home() / "Downloads"


def recent_dir() -> Path | None:
    """윈도우 '최근 항목' 폴더. 여기 있는 .lnk 파일은 바로가기일 뿐, 원본 파일이 아니다."""
    app_data = os.environ.get("APPDATA")
    return Path(app_data) / "Microsoft" / "Windows" / "Recent" if app_data else None


@dataclass
class PlanItem:
    label: str          # 화면에 보일 설명 (예: "사람 1 · 쿠키")
    path: Path          # 지울 파일·폴더
    allowed_root: Path  # 이 폴더 밖이면 절대 지우지 않음


def plan_cleanup(user_data_dir: Path, options: dict[str, bool],
                 include_system: bool = True) -> list[PlanItem]:
    """선택한 옵션에 따라 '지울 목록'을 만든다. 실제로 지우지는 않는다."""
    plan: list[PlanItem] = []

    for profile in list_profiles(user_data_dir):
        profile_name = profile_display_name(profile)
        for key, (label, _default, relative_paths) in PROFILE_ITEMS.items():
            if not options.get(key):
                continue
            for relative in relative_paths:
                path = profile / relative
                if path.exists() or path.is_symlink():
                    plan.append(PlanItem(f"{profile_name} · {label}", path, profile))

    if include_system:
        if options.get("recent"):
            folder = recent_dir()
            if folder and folder.is_dir():
                for item in folder.glob("*.lnk"):
                    plan.append(PlanItem(SYSTEM_ITEMS["recent"][0], item, folder))
        if options.get("downloads"):
            folder = downloads_dir()
            if folder.is_dir():
                for item in folder.iterdir():
                    plan.append(PlanItem("다운로드 폴더", item, folder))

    return plan


# ---------------------------------------------------------------------------
# 실제로 지우기
# ---------------------------------------------------------------------------
def _is_inside(path: Path, root: Path) -> bool:
    """path가 root 폴더 '안쪽'에 있는가? (root 자기 자신은 지우지 않으므로 False)"""
    path_abs = os.path.normcase(os.path.abspath(path))
    root_abs = os.path.normcase(os.path.abspath(root))
    return path_abs != root_abs and path_abs.startswith(root_abs + os.sep)


def remove_path(path: Path, allowed_root: Path) -> str:
    """파일 또는 폴더 하나를 지우고 결과를 글로 돌려준다."""
    if not _is_inside(path, allowed_root):
        return "건너뜀 (허용된 폴더 밖)"
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            return "이미 없음"
        return "삭제함"
    except PermissionError:
        return "실패 (다른 프로그램이 사용 중)"
    except OSError as e:
        return f"실패 ({e.strerror or e})"


def execute_cleanup(plan: list[PlanItem]) -> list[tuple[PlanItem, str]]:
    """정리 계획대로 지우고 (항목, 결과) 목록을 돌려준다."""
    return [(item, remove_path(item.path, item.allowed_root)) for item in plan]
