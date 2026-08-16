# -*- coding: utf-8 -*-
"""
수집 CSV → 대시보드용 JSON 2개.

  docs/data.json     차트가 그리는 원본 (일별 전체 시계열 포함)
  docs/context.json  Q&A가 근거로 쓰는 압축 요약본
                     (LLM 프롬프트에 통째로 넣을 수 있게 작게 유지)
"""
import csv, json, os
from collections import defaultdict
from datetime import datetime
from common import DATA, ROOT, GU, JOB, KW_GROUPS

DOCS = os.path.join(ROOT, "docs")
os.makedirs(DOCS, exist_ok=True)
MA = 7                       # 이동평균 창
GU_NAME = {g[2]: g[0] for g in GU}
JOB_NAME = dict(JOB)


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def moving_avg(vals, w):
    out = []
    for i in range(len(vals)):
        s = vals[max(0, i - w + 1): i + 1]
        out.append(round(sum(s) / len(s), 1))
    return out


def pct(a, b):
    return None if not b else round((a - b) / b * 100, 1)


def build_saramin():
    rows = read(os.path.join(DATA, "saramin_daily.csv"))
    if not rows:
        return None
    for r in rows:
        r["count"] = int(r["count"])

    dates = sorted({r["date"] for r in rows})
    allv = {r["date"]: r["count"] for r in rows if r["dim"] == "all"}
    series = [allv.get(d, 0) for d in dates]
    base = next((v for v in series if v), 1)

    by_gu, by_job, by_kw = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for r in rows:
        d = {"gu": by_gu, "job": by_job, "kw": by_kw}.get(r["dim"])
        if d is not None:
            d[r["date"]][r["name"]] = r["count"]

    last = dates[-1]
    prev7 = dates[max(0, len(dates) - 8)]
    prev30 = dates[max(0, len(dates) - 31)]

    def delta(d, base=None):
        cur, old = d.get(last, {}), d.get(base or prev7, {})
        return sorted(
            ({"name": k, "count": v, "delta": pct(v, old.get(k, 0))} for k, v in cur.items()),
            key=lambda x: -x["count"])

    # 월평균 (월단위 work24와 비교하기 위한 접기)
    mon = defaultdict(list)
    for d, v in zip(dates, series):
        if v:
            mon[d[:7]].append(v)
    monthly = [{"ym": k.replace("-", ""), "avg": round(sum(v) / len(v))}
               for k, v in sorted(mon.items())]

    kw_latest = {x["name"]: x for x in delta(by_kw, prev30)}
    series_kw = [k for g in KW_GROUPS if g["type"] == "series" for k in g["kw"]]

    return {
        "dates": dates,
        "total": series,
        "ma7": moving_avg(series, MA),
        "index": [round(v / base * 100, 1) for v in series],
        "index_base_date": dates[0],
        "monthly_avg": monthly,
        "by_gu": delta(by_gu),
        "by_job": delta(by_job),
        "kw_groups": [{k: g[k] for k in ("id", "title", "type", "kw")} for g in KW_GROUPS],
        "kw_latest": kw_latest,
        "kw_daily": {k: [by_kw.get(d, {}).get(k) for d in dates] for k in series_kw},
        "kw_base_date": prev30,
        "latest_date": last,
    }


def build_work24():
    opia = read(os.path.join(DATA, "work24_opia.csv"))
    opib = read(os.path.join(DATA, "work24_opib.csv"))
    if not opia:
        return None
    num = ["신규구인", "신규구직", "취업건수", "유효구인"]
    tot = defaultdict(lambda: defaultdict(int))
    for r in opia:
        for k in num:
            tot[r["ym"]][k] += int(r[k] or 0)
    yms = sorted(tot)
    out = {"yms": yms, **{k: [tot[y][k] for y in yms] for k in num}}

    if opib:
        ip = defaultdict(int)
        for r in opib:
            ip[r["ym"]] += int(r["피보험자수"] or 0)
        out["피보험자_yms"] = sorted(ip)
        out["피보험자수"] = [ip[y] for y in sorted(ip)]

    last = yms[-1]
    out["by_gu_latest"] = sorted(
        [{"name": r["gu_name"], **{k: int(r[k] or 0) for k in num}}
         for r in opia if r["ym"] == last],
        key=lambda x: -x["신규구직"])
    out["latest_ym"] = last
    return out


def build_context(sa, w2):
    """Q&A 근거용 압축본. 숫자는 반드시 여기서만 나온다."""
    ctx = {
        "생성시각": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "데이터정의": {
            "사람인_공고수": "사람인 채용정보 오픈API의 검색결과 총 건수. "
                          "공고 '건수'이며 실제 채용 인원수가 아님. 한 공고에 여러 명을 뽑을 수 있고, "
                          "공고가 마감되면 집계에서 빠짐. 매일 수집한 시점 스냅샷임.",
            "지역기준": "사람인은 공고에 표기된 근무지 기준, work24는 rsdAreaCd(구직자 거주지) 기준. 둘의 지역 정의가 다름.",
            "work24_신규구인": "이 대시보드에는 없음. 구인은 사업체가 내는 것이라 구직자 거주지·성별·연령으로 분해되지 않아 API가 항상 0을 반환함.",
            "work24_신규구직": "워크넷 신규구직 건수. 구직자 거주지 기준. 월 단위 마감치.",
            "work24_취업건수": "워크넷을 통한 취업 건수. 구직자 거주지 기준. 월 단위 마감치.",
            "work24_피보험자수": "고용보험 피보험자 수(스톡). 월 단위.",
        },
        "수집못하는것": [
            "연령대별(청년/중장년/고령) 채용공고 — 사람인 API에서 연령 필터를 쓰지 않으므로 없음",
            "실제 채용 인원수 / 채용 성사 여부 — 공고 건수만 있음",
            "임금·근속·고용형태별 분해 — 수집 대상에 없음",
            "구 × 직무 교차 집계 — API 일일 호출 한도(500회) 때문에 지역별·직무별 '각각의 합계'만 수집",
            "work24 신규구인(구인 수요) — 거주지 기준 조회로는 항상 0. 채용 수요는 사람인 공고수로만 봐야 함",
        ],
    }
    if sa:
        ctx["사람인"] = {
            "기간": f"{sa['dates'][0]} ~ {sa['latest_date']}",
            "최근일자": sa["latest_date"],
            "서울전체_최근": sa["total"][-1],
            "서울전체_7일평균": sa["ma7"][-1],
            "지수_기준일": sa["index_base_date"],
            "지수_최근": sa["index"][-1],
            "월평균추이": sa["monthly_avg"],
            "구별_최근": [{"구": x["name"], "공고수": x["count"], "7일전대비%": x["delta"]}
                        for x in sa["by_gu"]],
            "직무별_최근": [{"직무": x["name"], "공고수": x["count"], "7일전대비%": x["delta"]}
                         for x in sa["by_job"]],
            "트렌드키워드": [
                {"그룹": g["title"],
                 "항목": [{"키워드": k,
                          "공고수": sa["kw_latest"].get(k, {}).get("count"),
                          "30일전대비%": sa["kw_latest"].get(k, {}).get("delta")}
                         for k in g["kw"]]}
                for g in sa["kw_groups"]],
            "키워드주의": "키워드는 공고명·기업명·업직종 통합검색 결과라 동음이의어가 섞일 수 있음. "
                        "키워드 간 합계는 중복되므로 더하면 안 됨. "
                        "'청년'·'고령자'처럼 대상을 뜻하는 키워드도 그 단어가 공고에 적혀 있는 건수일 뿐, "
                        "해당 연령대를 실제로 채용한 규모가 아님.",
        }
    if w2:
        ctx["work24"] = {
            "최근마감월": w2["latest_ym"],
            "월별": [{"ym": y, "신규구직": b, "취업건수": c}
                    for y, b, c in zip(w2["yms"], w2["신규구직"], w2["취업건수"])],
            "구별_최근": w2["by_gu_latest"],
        }
        if "피보험자수" in w2:
            ctx["work24"]["피보험자_월별"] = [
                {"ym": y, "수": v} for y, v in zip(w2["피보험자_yms"], w2["피보험자수"])]
    return ctx


def main():
    sa, w2 = build_saramin(), build_work24()
    data = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mock": os.path.exists(os.path.join(DATA, ".mock")),
            "saramin": sa, "work24": w2}
    for name, obj in (("data.json", data), ("context.json", build_context(sa, w2))):
        p = os.path.join(DOCS, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{name}  {os.path.getsize(p)/1024:.0f} KB")


if __name__ == "__main__":
    main()
