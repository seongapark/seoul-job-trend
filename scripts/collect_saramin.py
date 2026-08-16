# -*- coding: utf-8 -*-
"""
사람인 채용정보 오픈API — 서울 채용공고 '건수'만 매일 수집.

호출 예산: 1일 500회 제한 → 실제 사용 77회
  · 서울 전체                 1회
  · 서울 × 25개 구            25회
  · 서울 × 21개 직무 대분류   21회
  · 서울 × 30개 트렌드 키워드 30회
개별 공고를 받지 않고 count=1로 응답의 total 값만 읽는다.
(25구 × 21직무 = 525회는 한도를 넘으므로 교차표 대신 '주변합'만 수집)

환경변수: SARAMIN_KEY
"""
import json, os, sys, time, urllib.parse
from common import DATA, GU, JOB, KEYWORD, http_get, append_csv
from datetime import datetime, timezone, timedelta

API = "https://oapi.saramin.co.kr/job-search"
KEY = os.environ.get("SARAMIN_KEY", "").strip()
JOB_PARAM = "job_mid_cd"     # 직무 대분류 파라미터명
OUT = os.path.join(DATA, "saramin_daily.csv")
KST = timezone(timedelta(hours=9))


def total(**params):
    """count=1로 호출해 검색결과 총 건수만 반환."""
    q = {"access-key": KEY, "count": 1, "fields": "count"}
    q.update(params)
    url = API + "?" + urllib.parse.urlencode(q)
    txt = http_get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    js = json.loads(txt)
    return int(js["jobs"]["total"])


def main():
    if not KEY:
        sys.exit("SARAMIN_KEY 환경변수가 없습니다.")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    rows = []

    seoul = total(loc_cd="101000")
    rows.append([today, "all", "101000", "서울전체", seoul])
    print(f"서울전체 {seoul:,}건")

    for name, _w24, cd in GU:
        rows.append([today, "gu", cd, name, total(loc_cd=cd)])
        time.sleep(0.3)

    for cd, name in JOB:
        rows.append([today, "job", cd, name, total(**{"loc_cd": "101000", JOB_PARAM: cd})])
        time.sleep(0.3)

    for kw in KEYWORD:
        rows.append([today, "kw", kw, kw, total(loc_cd="101000", keywords=kw)])
        time.sleep(0.3)

    # 파라미터명이 틀리면 모든 값이 서울전체와 같아진다 → 즉시 감지
    jobvals = {r[4] for r in rows if r[1] == "job"}
    if len(jobvals) == 1 and seoul in jobvals:
        print(f"[경고] 직무별 값이 전부 서울전체와 동일합니다. "
              f"'{JOB_PARAM}' 파라미터명이 맞는지 확인하세요.")

    n = append_csv(OUT, ["date", "dim", "code", "name", "count"], rows, [0, 1, 2])
    print(f"{today}: {n}행 저장 → {OUT}")


if __name__ == "__main__":
    main()
