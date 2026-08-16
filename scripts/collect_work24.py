# -*- coding: utf-8 -*-
"""
고용행정통계 OpenAPI(work24) — 서울 25개 구 월별 수집.

  OPIA 구인구직 : 신규구인/신규구직/취업건수  (성×연령 전 조합 합산 → 구별 1행)
  OPIB 피보험자 : 피보험자수/취득/상실        (사업장 단위 행이라 무거움 → WITH_OPIB=1일 때만)

인증키는 없지만 **IP당 일일 조회 한도(HITS_EXCEEDED)**가 있다.
한 달치 = 25구 × 성2 × 연령15 = 750회. 24개월이면 18,000회라 하루에 못 받는다.
그래서 최신 월부터 거꾸로 한 달씩 받아 즉시 저장하고, 한도에 걸리면 정상 종료한다.
다음 실행이 이미 저장된 (연월, 구)를 건너뛰고 이어받으므로 며칠에 걸쳐 채워진다.
"""
import os, re, sys, time, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import DATA, GU, http_get, append_csv
from datetime import date

URL = {"OPIA": "https://eis.work24.go.kr/opi/joApi.do",
       "OPIB": "https://eis.work24.go.kr/opi/ipsApi.do"}
AGES = [f"{i:02d}" for i in range(1, 16)]
N_MONTHS = int(os.environ.get("N_MONTHS", "24"))
WITH_OPIB = os.environ.get("WITH_OPIB", "0") == "1"
WORKERS = int(os.environ.get("WORKERS", "3"))
# display는 10보다 크고 10000보다 작아야 한다(API 제약). 1이나 10000을 넣으면 에러 응답.
DISPLAY = 9999
OPIA_CSV = os.path.join(DATA, "work24_opia.csv")
OPIB_CSV = os.path.join(DATA, "work24_opib.csv")


class QuotaExceeded(Exception):
    """work24는 IP당 일일 조회 횟수 상한이 있다(HITS_EXCEEDED). 도달하면 그날은 더 못 받는다."""


def fetch(api, **params):
    """(건수, 행목록) 반환. 에러 응답이면 (-1, [에러메시지])."""
    p = {"apiSecd": api, "rernSecd": "XML", "bgnPage": 1, "display": DISPLAY}
    p.update(params)
    url = URL[api] + "?" + "&".join(f"{k}={v}" for k, v in p.items())
    txt = http_get(url, encoding="euc-kr", timeout=60)

    # 이 API는 루트 닫힘태그 뒤에 '>'를 하나 더 붙여 보낸다 → 그대로 파싱하면 깨진다
    m = re.search(r"</(rqstApi|baroone)>", txt)
    if m:
        txt = txt[:m.end()]

    root = ET.fromstring(txt)
    err = root.findtext(".//error")
    if err:
        if "HITS_EXCEEDED" in err:
            raise QuotaExceeded(err)
        return -1, [err]
    cnt = int(root.findtext(".//rqst-cnt") or 0)
    rows = [{c.tag: (c.text or "").strip() for c in rq} for rq in root.iter("rqst")]
    return cnt, rows


def fetch_all(api, **params):
    """rqst-cnt만큼 전량 수신 (OPIB 페이징)."""
    cnt, rows = fetch(api, **params)
    if cnt < 0:
        print(f"  [에러] {params} → {rows[0][:60]}")
        return []
    if cnt <= len(rows):
        return rows
    got = list(rows)
    while len(got) < cnt:
        c2, more = fetch(api, bgnPage=len(got) // DISPLAY + 1, **params)
        if c2 < 0 or not more:
            break
        got += more
    return got


def latest_month():
    y, m = date.today().year, date.today().month
    for _ in range(8):
        ym = f"{y}{m:02d}"
        cnt, info = fetch("OPIA", rsdAreaCd="11110", sxdsCd="M", ageCd="07", closStdrYm=ym)
        if cnt < 0:
            print(f"  {ym}: API 에러 → {info[0][:80]}")
        elif cnt > 0:
            return ym
        else:
            print(f"  {ym}: 아직 미제공")
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


def collect_by_month(mons, csv_path, header, work, label):
    """
    최신 월부터 거꾸로, **한 달씩 끊어서 수집하고 그때그때 저장**한다.

    work24는 IP당 일일 조회 한도가 있어서 24개월(=구25×성2×연령15×24 = 18,000회)을
    하루에 다 받을 수 없다. 한도에 걸리면 그 시점까지 받은 달까지만 저장하고 정상 종료하고,
    다음 날 실행에서 이미 저장된 (연월, 구)를 건너뛰고 이어받는다.
    한 달치 = 750회이므로 며칠에 걸쳐 24개월이 채워진다.
    """
    done = done_keys(csv_path)
    todo_months = [ym for ym in reversed(mons)
                   if any((ym, g[1]) not in done for g in GU)]
    print(f"[{label}] 남은 달 {len(todo_months)}개 (이미 저장된 구×월 {len(done)}개)")

    for ym in todo_months:
        gus = [g for g in GU if (ym, g[1]) not in done]
        rows, quota, fails = [], False, 0
        with ThreadPoolExecutor(WORKERS) as ex:
            futs = {ex.submit(work, ym, g): g for g in gus}
            for f in as_completed(futs):
                try:
                    rows.append(f.result())
                except QuotaExceeded:
                    quota = True
                except Exception as e:
                    fails += 1
                    print(f"  [{label}] {ym} {futs[f][0]} 실패: {type(e).__name__}")
        if rows:
            n = append_csv(csv_path, header, rows, [0, 1])
            print(f"  [{label}] {ym}: {n}개 구 저장" + (f" (실패 {fails})" if fails else ""))
        if quota or fails >= 5:
            print(f"[{label}] 일일 IP 호출 한도 도달 → 오늘은 여기까지. "
                  f"내일 실행 때 {ym}부터 이어받습니다.")
            return
    print(f"[{label}] 모든 달 수집 완료")


def run_opia(mons):
    def work(ym, g):
        name, cd, _s = g
        jo = jhnt = emp = vald = 0
        for sx in ("M", "F"):
            for ag in AGES:
                for r in fetch_all("OPIA", rsdAreaCd=cd, sxdsCd=sx, ageCd=ag, closStdrYm=ym):
                    jo   += int(r.get("newJoNmpr") or 0)
                    jhnt += int(r.get("newJhntNmpr") or 0)
                    emp  += int(r.get("empmCt") or 0)
                    vald += int(r.get("valdJoNmpr") or 0)
                time.sleep(0.1)
        return [ym, cd, name, jo, jhnt, emp, vald]

    collect_by_month(mons, OPIA_CSV,
                     ["ym", "gu_code", "gu_name", "신규구인", "신규구직", "취업건수", "유효구인"],
                     work, "OPIA")


def run_opib(mons):
    def work(ym, g):
        name, cd, _s = g
        ipnb = acqs = frft = 0
        for sx in ("1", "2"):
            for ag in AGES:
                for r in fetch_all("OPIB", rsdAreaCd=cd, sxdsCd=sx, ageCd=ag, closStdrYm=ym):
                    ipnb += int(r.get("prtyIpnb") or 0)
                    acqs += int(r.get("prtyAcqsNmpr") or 0)
                    frft += int(r.get("prtyFrftNmpr") or 0)
                time.sleep(0.1)
        return [ym, cd, name, ipnb, acqs, frft]

    collect_by_month(mons, OPIB_CSV,
                     ["ym", "gu_code", "gu_name", "피보험자수", "취득자수", "상실자수"],
                     work, "OPIB")


if __name__ == "__main__":
    lm = latest_month()
    mons = months(lm, N_MONTHS)
    print(f"최신 제공월 {lm} → {mons[0]}~{mons[-1]}")
    t0 = time.time()
    run_opia(mons)
    if WITH_OPIB:
        run_opib(mons)
    print(f"소요 {(time.time()-t0)/60:.1f}분")
