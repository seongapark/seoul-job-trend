# -*- coding: utf-8 -*-
"""공통 유틸: 재시도 HTTP 호출, CSV 누적 저장."""
import csv, os, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

# 서울 25개 구 — work24(행정구역코드) / 사람인(loc_cd) 대응표
GU = [
    # (구명, work24코드, 사람인코드)
    ("종로구",   "11110", "101230"), ("중구",     "11140", "101240"),
    ("용산구",   "11170", "101210"), ("성동구",   "11200", "101160"),
    ("광진구",   "11215", "101060"), ("동대문구", "11230", "101110"),
    ("중랑구",   "11260", "101250"), ("성북구",   "11290", "101170"),
    ("강북구",   "11305", "101030"), ("도봉구",   "11320", "101100"),
    ("노원구",   "11350", "101090"), ("은평구",   "11380", "101220"),
    ("서대문구", "11410", "101140"), ("마포구",   "11440", "101130"),
    ("양천구",   "11470", "101190"), ("강서구",   "11500", "101040"),
    ("구로구",   "11530", "101070"), ("금천구",   "11545", "101080"),
    ("영등포구", "11560", "101200"), ("동작구",   "11590", "101120"),
    ("관악구",   "11620", "101050"), ("서초구",   "11650", "101150"),
    ("강남구",   "11680", "101010"), ("송파구",   "11710", "101180"),
    ("강동구",   "11740", "101020"),
]

# 사람인 직무 대분류
JOB = [
    ("16", "기획·전략"),      ("14", "마케팅·홍보·조사"), ("3",  "회계·세무·재무"),
    ("5",  "인사·노무·HRD"),  ("4",  "총무·법무·사무"),    ("2",  "IT개발·데이터"),
    ("15", "디자인"),         ("8",  "영업·판매·무역"),    ("21", "고객상담·TM"),
    ("18", "구매·자재·물류"), ("12", "상품기획·MD"),       ("7",  "운전·운송·배송"),
    ("10", "서비스"),         ("11", "생산"),              ("22", "건설·건축"),
    ("6",  "의료"),           ("9",  "연구·R&D"),          ("19", "교육"),
    ("13", "미디어·문화·스포츠"), ("17", "금융·보험"),      ("20", "공공·복지"),
]


# 채용트렌드 키워드 — 사람인 keywords 통합검색(공고명·기업명·업직종)으로 건수를 센다.
# type="series" : 같은 범주 안에서 서로 비교되는 항목 → 추이 그래프
# type="cloud"  : 서로 비교 범주가 아닌 개별 트렌드 → 워드클라우드
# 1개당 하루 1회 호출. 늘리려면 일일 한도(500회) 안에서 조정할 것.
KW_GROUPS = [
    {"id": "hire", "title": "채용방식·조건", "type": "series",
     "kw": ["신입", "경력무관", "학력무관", "인턴", "채용전환", "수시채용"]},
    {"id": "target", "title": "정책 대상", "type": "series",
     "kw": ["청년", "시니어", "고령자", "장애인", "경력단절"]},
    {"id": "work", "title": "근무형태", "type": "series",
     "kw": ["재택근무", "하이브리드근무", "유연근무", "주4일", "시차출퇴근"]},
    {"id": "tech", "title": "업종·기술 키워드", "type": "cloud",
     "kw": ["AI", "인공지능", "챗GPT", "데이터분석", "클라우드", "보안",
            "반도체", "2차전지", "바이오", "로봇", "자동화", "플랫폼",
            "친환경", "스마트팩토리", "디지털전환"]},
]
KEYWORD = [k for g in KW_GROUPS for k in g["kw"]]


def http_get(url, headers=None, timeout=40, retries=4, encoding=None):
    """재시도 내장 GET. work24는 10회에 1회꼴로 무응답 타임아웃이 나므로 필수."""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw.decode(encoding, errors="replace") if encoding else raw.decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(2 ** i)          # 1, 2, 4초
    raise last


def append_csv(path, header, rows, key_idx):
    """key_idx 조합이 이미 있으면 건너뛰고 append. (재실행 안전)"""
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.reader(f):
                if r:
                    done.add(tuple(r[i] for i in key_idx))
    new = [r for r in rows if tuple(str(r[i]) for i in key_idx) not in done]
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerows(new)
    return len(new)
