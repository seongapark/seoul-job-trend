# -*- coding: utf-8 -*-
"""실데이터 오기 전 화면 확인용 가짜 데이터 생성. 실수집 시작하면 지워도 됨."""
import csv, math, os, random
from datetime import date, timedelta
from common import DATA, GU, JOB, KEYWORD

# 키워드별 (비중, 180일 성장배수)
KWPAR = {
    "신입":(0.130,1.00), "경력무관":(0.070,0.72), "학력무관":(0.055,1.05),
    "인턴":(0.012,1.10), "채용전환":(0.020,1.30), "수시채용":(0.030,1.40),
    "청년":(0.035,0.78), "시니어":(0.006,1.55), "고령자":(0.005,1.35),
    "장애인":(0.008,1.20), "경력단절":(0.003,1.65),
    "재택근무":(0.045,0.88), "하이브리드근무":(0.005,2.20), "유연근무":(0.018,1.25),
    "주4일":(0.004,2.40), "시차출퇴근":(0.004,1.30),
    "AI":(0.024,3.20), "인공지능":(0.016,2.80), "챗GPT":(0.002,3.00),
    "데이터분석":(0.014,1.50), "클라우드":(0.011,1.60), "보안":(0.010,1.35),
    "반도체":(0.009,1.20), "2차전지":(0.002,0.85), "바이오":(0.007,1.15),
    "로봇":(0.006,2.00), "자동화":(0.013,1.45), "플랫폼":(0.028,1.05),
    "친환경":(0.005,1.10), "스마트팩토리":(0.002,1.70), "디지털전환":(0.003,1.90),
}

random.seed(7)
END = date(2026, 8, 14)
DAYS = 180

# ---- 사람인 일별 ----
rows = []
for i in range(DAYS):
    d = END - timedelta(days=DAYS - 1 - i)
    season = 1 + 0.10 * math.sin(i / 30)
    weekday = 0.55 if d.weekday() >= 5 else 1.0
    base = 41000 * season * weekday * (1 + 0.0004 * i) * random.uniform(0.97, 1.03)
    rows.append([d.isoformat(), "all", "101000", "서울전체", round(base)])
    # GU 순서(종로~강동)에 맞춘 가중치 — 강남·서초·영등포·마포가 큼
    w = [0.05, 0.05, 0.03, 0.03, 0.02, 0.02, 0.01, 0.02, 0.01, 0.01,
         0.02, 0.02, 0.02, 0.05, 0.02, 0.04, 0.04, 0.03, 0.06, 0.02,
         0.02, 0.07, 0.20, 0.05, 0.02]
    for (name, _c, cd), ww in zip(GU, w):
        rows.append([d.isoformat(), "gu", cd, name, round(base * ww * random.uniform(0.9, 1.1))])
    jw = [0.05, 0.06, 0.04, 0.03, 0.09, 0.11, 0.04, 0.12, 0.05, 0.04,
          0.02, 0.05, 0.08, 0.07, 0.05, 0.04, 0.02, 0.03, 0.02, 0.03, 0.02]
    for (cd, name), ww in zip(JOB, jw):
        drift = 1 - 0.0012 * i if name == "총무·법무·사무" else 1 + 0.0005 * i
        rows.append([d.isoformat(), "job", cd, name,
                     round(base * ww * drift * random.uniform(0.9, 1.1))])
    for kw in KEYWORD:
        wb, gr = KWPAR[kw]
        f = 1 + (gr - 1) * i / DAYS
        rows.append([d.isoformat(), "kw", kw, kw,
                     round(base * wb * f * random.uniform(0.93, 1.07))])

with open(os.path.join(DATA, "saramin_daily.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["date", "dim", "code", "name", "count"])
    w.writerows(rows)

# ---- work24 월별 ----
yms = []
y, m = 2024, 7
for _ in range(24):
    yms.append(f"{y}{m:02d}")
    m += 1
    if m == 13:
        y, m = y + 1, 1
r2 = []
for k, ym in enumerate(yms):
    for j, (name, cd, _s) in enumerate(GU):
        s = 1 + 0.12 * math.sin(k / 6)
        b = (1400 - j * 40) * s * random.uniform(0.9, 1.1)
        r2.append([ym, cd, name, round(b), round(b * 1.7), round(b * 0.33), round(b * 1.4)])
with open(os.path.join(DATA, "work24_opia.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ym", "gu_code", "gu_name", "신규구인", "신규구직", "취업건수", "유효구인"])
    w.writerows(r2)

r3 = []
for k, ym in enumerate(yms):
    for j, (name, cd, _s) in enumerate(GU):
        b = (95000 - j * 3000) * (1 + 0.002 * k) * random.uniform(0.99, 1.01)
        r3.append([ym, cd, name, round(b), round(b * 0.03), round(b * 0.028)])
with open(os.path.join(DATA, "work24_opib.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ym", "gu_code", "gu_name", "피보험자수", "취득자수", "상실자수"])
    w.writerows(r3)

open(os.path.join(DATA, ".mock"), "w").close()
print("mock 생성 완료")
