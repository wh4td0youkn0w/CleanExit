"""
config.py — Clean Exit 설정 파일

프로그램 동작에 필요한 '목록'과 '기본값'을 한곳에 모아 둔 파일입니다.
검사할 사이트를 추가하거나 기본 옵션을 바꾸고 싶으면 이 파일만 고치면 됩니다.
"""

APP_NAME = "Clean Exit"
APP_SUBTITLE = "자리를 뜨기 전에, 흔적 없이."
MASCOT_NAME = "싹"

# ---------------------------------------------------------------------------
# ① 로그인 흔적 감지 — 로그인했을 때만 생기는 쿠키 목록
# ---------------------------------------------------------------------------
# 쿠키의 '이름'이 남아 있는지만 확인하고, 쿠키의 '값'(실제 비밀 정보)은 절대 읽지 않습니다.
#
# 형식: "화면에 보일 이름": (도메인 목록, 로그인 쿠키 이름 목록)
#   - 도메인은 끝부분만 적으면 됩니다. "google.com"은 accounts.google.com 등을 모두 포함합니다.
#   - 사이트가 쿠키 이름을 바꾸면 감지가 안 될 수 있으니, 그때는 이 목록을 갱신하세요.
#
# 학교 사이트를 추가하려면: 크롬에서 그 사이트에 로그인 → F12 → Application → Cookies에서
# 로그인 전후로 새로 생기는 쿠키 이름을 찾아 아래에 한 줄 추가하면 됩니다.
LOGIN_SITES = {
    "구글 (Gmail·유튜브·클래스룸)": (
        ("google.com", "google.co.kr", "youtube.com"),
        {"SID", "__Secure-1PSID", "__Secure-3PSID", "SAPISID"},
    ),
    "네이버": (("naver.com",), {"NID_AUT", "NID_SES"}),
    "카카오·다음": (("kakao.com", "daum.net"), {"_kawlt", "_kawltea", "_karmt"}),
    "마이크로소프트 (Office·Teams)": (
        ("login.microsoftonline.com", "login.live.com"),
        {"ESTSAUTH", "ESTSAUTHPERSISTENT", "__Host-MSAAUTH"},
    ),
    "인스타그램": (("instagram.com",), {"sessionid"}),
    "페이스북": (("facebook.com",), {"c_user", "xs"}),
    "깃허브": (("github.com",), {"user_session"}),
}

# ---------------------------------------------------------------------------
# ② 원클릭 정리 — 정리할 수 있는 항목
# ---------------------------------------------------------------------------
# (1) 크롬 프로필 폴더 안의 항목
# 형식: "키": (화면에 보일 이름, 기본으로 체크할지, 지울 파일·폴더 목록(프로필 폴더 기준))
PROFILE_ITEMS = {
    "cookies": (
        "쿠키 (모든 사이트에서 로그아웃)", True,
        ["Network/Cookies", "Network/Cookies-journal", "Cookies", "Cookies-journal"],
    ),
    "passwords": (
        "저장된 비밀번호", True,
        ["Login Data", "Login Data-journal",
         "Login Data For Account", "Login Data For Account-journal"],
    ),
    "autofill": (
        "크롬 계정 연결·자동 완성 정보", True,
        ["Web Data", "Web Data-journal"],
    ),
    "history": (
        "방문 기록", True,
        ["History", "History-journal", "Visited Links", "Top Sites", "Top Sites-journal"],
    ),
    "sessions": (
        "열려 있던 탭 기록", True,
        ["Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs"],
    ),
}

# (2) 크롬 밖, 윈도우 사용자 폴더의 항목
# 형식: "키": (화면에 보일 이름, 기본으로 체크할지)
SYSTEM_ITEMS = {
    "recent": ("윈도우 '최근 연 파일' 목록", True),
    "downloads": ("다운로드 폴더의 파일 (실제 파일이 지워져요!)", False),
}

# ---------------------------------------------------------------------------
# ③ 종료 시 경고 — 기본값
# ---------------------------------------------------------------------------
IDLE_MINUTES_DEFAULT = 5          # 키보드·마우스 입력이 없는 시간이 이만큼 지나면 경고
AUTO_CLEAN_SECONDS = 60           # '응답이 없으면 자동 정리'를 켰을 때 기다리는 시간
CLEAN_ON_SHUTDOWN_DEFAULT = True  # PC를 끌 때 흔적이 있으면 자동으로 정리할지

# ---------------------------------------------------------------------------
# 그 밖의 설정
# ---------------------------------------------------------------------------
AUTO_SCAN_SECONDS = 30            # 이 간격마다 조용히 다시 검사해서 마스코트 상태를 갱신
STATS_SAMPLE_MINUTES = 5          # 이 간격마다 사용 기록(통계)에 현재 상태를 한 줄 남김
