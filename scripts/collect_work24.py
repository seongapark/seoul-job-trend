# -*- coding: utf-8 -*-
"""
고용행정통계 OpenAPI(work24) — 서울 25개 구 월별 수집.

  OPIA 구인구직 : 신규구인/신규구직/취업건수  (성×연령 전 조합 합산 → 구별 1행)
  OPIB 피보험자 : 피보험자수/취득/상실        (사업장 단위 행이라 무거움 → WITH_OPIB=1일 때만)

이미 수집한 (연월, 구) 조합은 건너뛰므로 매일 돌려도 새 마감월이 나올 때만 실제 호출한다.
인증키 없음. 간헐적 무응답이 있어 common.http_get의 재시도에 의존.
"""
import os, sys, time, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from common import DATA, GU, http_get, append_csv
from datetime import date

URL = {"OPIA": "https://eis.work24.go.kr/opi/joApi.do",
       "OPIB": "https://eis.work24.go.kr/opi/ipsApi.do"}
AGES = [f"{i:02d}" for i in range(1, 16)]
N_MONTHS = int(os.environ.get("N_MONTHS", "24"))
WITH_OPIB = os.environ.get("WITH_OPIB", "0") == "1"
WORKERS = int(os.environ.get("WORKERS", "4"))
OPIA_CSV = os.path.join(DATA, "work24_opia.csv")
OPIB_CSV = os.path.join(DATA, "work24_opib.csv")


def fetch(api, **params):
    p = {"apiSecd": api, "rernSecd": "XML", "bgnPage": 1, "display": 10000}
    p.update(params)
    url = URL[api] + "?" + "&".join(f"{k}={v}" for k, v in p.items())
    txt = http_get(url, encoding="euc-kr", timeout=60)
    root = ET.fromstring(txt)
    if root.findtext(".//error"):
        return 0, []
    cnt = int(root.findtext(".//rqst-cnt") or 0)
    rows = [{c.tag: (c.text or "").strip() for c in rq} for rq in root.iter("rqst")]
    return cnt, rows


def fetch_all(api, **params):
    """rqst-cnt만큼 전량 수신 (OPIB 페이징)."""
    cnt, rows = fetch(api, **params)
    if cnt <= len(rows):
        return rows
    got = list(rows)
    while len(got) < cnt:
        _, more = fetch(api, bgnPage=len(got) // 10000 + 1, **params)
        if not more:
            break
        got += more
    return got


def latest_month():
    y, m = date.today().year, date.today().month
    for _ in range(6):
        ym = f"{y}{m:02d}"
        cnt, _ = fetch("OPIA", rsdAreaCd="11110", sxdsCd="M", ageCd="07",
                       closStdrYm=ym, display=1)
        if cnt > 0:
            return ym
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    sys.exit("최신 제공월을 찾지 못했습니다")


def months(latest, n):
    y, m, out = int(latest[:4]), int(latest[4:]), []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def done_keys(path):
    import csv
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8-sig") as f:
        return {(r["ym"], r["gu_code"]) for r in csv.DictReader(f)}


def run_opia(mons):
    done = done_keys(OPIA_CSV)
    todo = [(ym, g) for ym in mons for g in GU if (ym, g[1]) not in done]
    print(f"[OPIA] 대상 {len(todo)}개 (구×월), 완료 {len(done)}개 건너뜀")
    if not todo:
        return

    def work(t):
        ym, (name, cd, _s) = t
        jo = jhnt = emp = vald = 0
        for sx in ("M", "F"):
            for ag in AGES:
                for r in fetch_all("OPIA", rsdAreaCd=cd, sxdsCd=sx, ageCd=ag, closStdrYm=ym):
                    jo   += int(r.get("newJoNmpr") or 0)
                    jhnt += int(r.get("newJhntNmpr") or 0)
                    emp  += int(r.get("empmCt") or 0)
                    vald += int(r.get("valdJoNmpr") or 0)
        return [ym, cd, name, jo, jhnt, emp, vald]

    with ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(work, todo))
    n = append_csv(OPIA_CSV,
                   ["ym", "gu_code", "gu_name", "신규구인", "신규구직", "취업건수", "유효구인"],
                   rows, [0, 1])
    print(f"[OPIA] {n}행 저장")


def run_opib(mons):
    done = done_keys(OPIB_CSV)
    todo = [(ym, g) for ym in mons for g in GU if (ym, g[1]) not in done]
    print(f"[OPIB] 대상 {len(todo)}개 (구×월) — 사업장 단위라 오래 걸립니다")
    if not todo:
        return

    def work(t):
        ym, (name, cd, _s) = t
        ipnb = acqs = frft = 0
        for sx in ("1", "2"):
            for ag in AGES:
                for r in fetch_all("OPIB", rsdAreaCd=cd, sxdsCd=sx, ageCd=ag, closStdrYm=ym):
                    ipnb += int(r.get("prtyIpnb") or 0)
                    acqs += int(r.get("prtyAcqsNmpr") or 0)
                    frft += int(r.get("prtyFrftNmpr") or 0)
        return [ym, cd, name, ipnb, acqs, frft]

    with ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(work, todo))
    n = append_csv(OPIB_CSV,
                   ["ym", "gu_code", "gu_name", "피보험자수", "취득자수", "상실자수"],
                   rows, [0, 1])
    print(f"[OPIB] {n}행 저장")


if __name__ == "__main__":
    lm = latest_month()
    mons = months(lm, N_MONTHS)
    print(f"최신 제공월 {lm} → {mons[0]}~{mons[-1]}")
    t0 = time.time()
    run_opia(mons)
    if WITH_OPIB:
        run_opib(mons)
    print(f"소요 {(time.time()-t0)/60:.1f}분")
