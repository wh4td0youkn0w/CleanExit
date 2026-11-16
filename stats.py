"""
stats.py — 사용 기록(통계) 저장

기대 효과를 '숫자로' 확인하기 위해, 프로그램이 한 일을 CSV 파일에 한 줄씩 남긴다.
엑셀이나 구글 시트로 열어서 바로 그래프를 그릴 수 있다.

[개인정보를 남기지 않는 기록]
- 계정 이름, 이메일, 사이트 주소, 파일 이름은 기록하지 않는다.
- '흔적이 있었는지', '로그인된 사이트가 몇 개였는지' 같은 숫자만 남긴다.

저장 위치: C:\\Users\\(사용자)\\AppData\\Local\\CleanExit\\usage_log.csv
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from scanner import ProfileReport, summarize

FIELDS = ["시각", "이벤트", "흔적_있음", "로그인_사이트_수", "크롬_계정_연결",
          "비밀번호_저장", "크롬_실행중", "비고"]


def default_stats_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home()) / "CleanExit"


class StatsLog:
    def __init__(self, path: Path | None = None):
        self.path = path or default_stats_dir() / "usage_log.csv"

    def record(self, event: str, reports: list[ProfileReport] | None = None,
               chrome_running: bool | None = None, note: str = "") -> None:
        """이벤트 한 줄을 기록한다. 기록에 실패해도 프로그램은 계속 동작한다."""
        row = {"시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "이벤트": event, "비고": note}
        if reports is not None:
            s = summarize(reports)
            row.update({"흔적_있음": int(s.has_traces), "로그인_사이트_수": s.site_count,
                        "크롬_계정_연결": int(s.signed_in), "비밀번호_저장": int(s.has_passwords)})
        if chrome_running is not None:
            row["크롬_실행중"] = int(chrome_running)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not self.path.exists()
            # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않는 인코딩
            with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                if is_new:
                    writer.writeheader()
                writer.writerow(row)
        except OSError:
            pass
