"""
scanner.py — 로그인 흔적 검사

크롬 프로필 폴더를 살펴보고 다음을 확인합니다.
  1) 주요 사이트에 로그인된 상태인지 (로그인 쿠키의 '이름'만 확인)
  2) 크롬 자체에 구글 계정으로 로그인(동기화)되어 있는지
  3) 저장된 비밀번호가 몇 개인지 (개수만 셉니다)

[개인정보를 읽지 않는 설계]
- 쿠키 DB에서는 host_key(사이트 주소)와 name(쿠키 이름) 두 열만 읽습니다. value(값)는 읽지 않습니다.
- 비밀번호 DB에서는 COUNT(*)로 개수만 셉니다.
- 크롬 계정은 '있는지 없는지'만 판단하고, 이메일 주소를 화면에 보여 주거나 저장하지 않습니다.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from config import LOGIN_SITES


class DatabaseLocked(Exception):
    """크롬이 켜져 있어서 파일이 잠겨 읽을 수 없을 때 발생하는 오류"""


# ---------------------------------------------------------------------------
# 크롬 폴더 찾기
# ---------------------------------------------------------------------------
def default_user_data_dir() -> Path:
    """크롬이 사용자 정보를 저장하는 기본 폴더(User Data)를 돌려준다."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:  # 윈도우
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    return Path.home() / ".config" / "google-chrome"  # 윈도우가 아닐 때(개발용)


def list_profiles(user_data_dir: Path) -> list[Path]:
    """User Data 안의 프로필 폴더(Default, Profile 1, Profile 2 ...) 목록을 돌려준다."""
    if not user_data_dir.is_dir():
        return []
    profiles = []
    for child in sorted(user_data_dir.iterdir()):
        is_profile = child.is_dir() and (child / "Preferences").is_file()
        if is_profile and child.name not in ("System Profile", "Guest Profile"):
            profiles.append(child)
    return profiles


def _read_preferences(profile_dir: Path) -> dict:
    """프로필 설정 파일(Preferences, JSON 형식)을 읽는다. 실패하면 빈 딕셔너리."""
    try:
        with open(profile_dir / "Preferences", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def profile_display_name(profile_dir: Path) -> str:
    """크롬 화면에 보이는 프로필 이름(예: '사람 1')을 돌려준다."""
    name = _read_preferences(profile_dir).get("profile", {}).get("name")
    return name or profile_dir.name


def is_signed_in_to_chrome(profile_dir: Path) -> bool:
    """
    크롬 자체에 구글 계정이 연결되어 있는지만 확인한다. (이메일은 돌려주지 않음)
    설정 파일에 계정 기록이 있고, 실제 로그인 토큰도 남아 있어야 '연결됨'으로 본다.
    (토큰을 지우면 설정 파일에 기록이 남아 있어도 로그인은 풀린다)
    """
    accounts = _read_preferences(profile_dir).get("account_info") or []
    has_account = any(isinstance(a, dict) and a.get("email") for a in accounts)
    return has_account and count_login_tokens(profile_dir) > 0


# ---------------------------------------------------------------------------
# SQLite 데이터베이스 읽기
# ---------------------------------------------------------------------------
def _query_copy(db_path: Path, sql: str) -> list[tuple]:
    """
    DB 파일을 임시 폴더에 '복사'한 뒤 읽기 전용으로 연다.
    원본을 직접 열면 크롬이 쓰는 파일을 건드릴 수 있으므로 항상 복사본을 사용한다.
    """
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / "copy.db"
        try:
            shutil.copyfile(db_path, copy_path)
        except PermissionError as e:
            # 크롬이 실행 중이면 윈도우가 파일을 잠가서 복사조차 안 된다.
            raise DatabaseLocked(str(db_path)) from e
        conn = sqlite3.connect(copy_path.as_uri() + "?mode=ro", uri=True)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()  # 임시 폴더가 지워지기 전에 반드시 닫기 (윈도우에서 중요)


def cookie_db_path(profile_dir: Path) -> Path | None:
    """쿠키 DB 위치. 최신 크롬은 Network/Cookies, 예전 크롬은 Cookies에 있다."""
    for relative in ("Network/Cookies", "Cookies"):
        path = profile_dir / relative
        if path.is_file():
            return path
    return None


def read_cookie_names(db_path: Path) -> list[tuple[str, str]]:
    """(사이트 주소, 쿠키 이름) 목록. 쿠키 '값'은 읽지 않는다."""
    return _query_copy(db_path, "SELECT host_key, name FROM cookies")


def count_saved_passwords(profile_dir: Path) -> int:
    """저장된 비밀번호 '개수'만 센다."""
    db_path = profile_dir / "Login Data"
    if not db_path.is_file():
        return 0
    return _query_copy(db_path, "SELECT COUNT(*) FROM logins")[0][0]


def count_login_tokens(profile_dir: Path) -> int:
    """크롬 계정 로그인 토큰(Web Data의 token_service 표)의 '개수'만 센다."""
    db_path = profile_dir / "Web Data"
    if not db_path.is_file():
        return 0
    try:
        return _query_copy(db_path, "SELECT COUNT(*) FROM token_service")[0][0]
    except sqlite3.OperationalError:  # 표가 없는 경우
        return 0


# ---------------------------------------------------------------------------
# 로그인 판단
# ---------------------------------------------------------------------------
def _domain_matches(host: str, domain: str) -> bool:
    """host가 domain이거나 그 하위 주소인지. (notgoogle.com은 google.com으로 치지 않음)"""
    host = host.lstrip(".").lower()
    return host == domain or host.endswith("." + domain)


def find_logged_in_sites(cookie_pairs: list[tuple[str, str]]) -> list[str]:
    """쿠키 이름 목록을 config.LOGIN_SITES와 비교해 로그인된 사이트 이름을 돌려준다."""
    found = []
    for site_name, (domains, login_cookie_names) in LOGIN_SITES.items():
        for host, cookie_name in cookie_pairs:
            if cookie_name in login_cookie_names and any(
                _domain_matches(host, d) for d in domains
            ):
                found.append(site_name)
                break
    return found


@dataclass
class ProfileReport:
    """프로필 하나의 검사 결과"""

    name: str
    path: Path
    chrome_signed_in: bool = False
    sites: list[str] = field(default_factory=list)
    saved_passwords: int = 0
    locked: bool = False          # 크롬이 켜져 있어서 검사하지 못함
    error: str | None = None

    @property
    def has_traces(self) -> bool:
        """정리가 필요한 흔적이 있는가? (검사를 못 한 경우도 '위험'으로 본다)"""
        return (
            self.locked
            or self.error is not None
            or self.chrome_signed_in
            or bool(self.sites)
            or self.saved_passwords > 0
        )


@dataclass
class Summary:
    """여러 프로필의 검사 결과를 한 줄로 요약한 것 (마스코트·통계에서 사용)"""

    profiles: int = 0
    has_traces: bool = False
    locked: bool = False
    site_count: int = 0
    signed_in: bool = False
    has_passwords: bool = False

    @property
    def trace_count(self) -> int:
        """마스코트가 말할 '흔적 개수': 로그인된 사이트 + 크롬 계정 + 저장된 비밀번호"""
        return self.site_count + int(self.signed_in) + int(self.has_passwords)


def summarize(reports: list[ProfileReport]) -> Summary:
    return Summary(
        profiles=len(reports),
        has_traces=any(r.has_traces for r in reports),
        locked=any(r.locked for r in reports),
        site_count=sum(len(r.sites) for r in reports),
        signed_in=any(r.chrome_signed_in for r in reports),
        has_passwords=any(r.saved_passwords > 0 for r in reports),
    )


def scan_profile(profile_dir: Path) -> ProfileReport:
    report = ProfileReport(name=profile_display_name(profile_dir), path=profile_dir)
    try:
        report.chrome_signed_in = is_signed_in_to_chrome(profile_dir)
        db_path = cookie_db_path(profile_dir)
        if db_path:
            report.sites = find_logged_in_sites(read_cookie_names(db_path))
        report.saved_passwords = count_saved_passwords(profile_dir)
    except DatabaseLocked:
        report.locked = True
    except sqlite3.DatabaseError as e:
        report.error = f"DB를 읽지 못함: {e}"
    return report


def scan_all(user_data_dir: Path) -> list[ProfileReport]:
    """모든 크롬 프로필을 검사한다."""
    return [scan_profile(p) for p in list_profiles(user_data_dir)]


# ---------------------------------------------------------------------------
# 크롬 실행 여부
# ---------------------------------------------------------------------------
def is_chrome_running() -> bool:
    """크롬(chrome.exe)이 실행 중인지 확인한다."""
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                capture_output=True, text=True, errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW,  # 검은 창이 깜빡이지 않게
            ).stdout
            return "chrome.exe" in output.lower()
        result = subprocess.run(["pgrep", "-x", "chrome"], capture_output=True)
        return result.returncode == 0
    except OSError:
        return False
