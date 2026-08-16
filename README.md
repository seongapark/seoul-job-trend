# 서울 채용트렌드 대시보드

사람인 채용공고(일 단위)와 고용행정통계 work24 구인구직·피보험자(월 단위)를
한 화면에서 비교하는 대시보드. 수집·빌드·배포가 GitHub Actions로 자동화되어 있다.

## 구조

```
scripts/collect_saramin.py   매일  사람인 API로 서울 공고 '건수'만 수집 → data/saramin_daily.csv
scripts/collect_work24.py    매일  새 마감월이 나왔을 때만 work24 수집 → data/work24_*.csv
scripts/build_data.py        CSV → docs/data.json (차트용) + docs/context.json (Q&A 근거용)
docs/index.html              대시보드 본체. data.json만 읽으므로 호스팅을 바꿔도 수정 불필요
worker/                      Q&A에 AI를 붙일 때 쓰는 Cloudflare Worker (선택)
```

## 시작 전 설정

1. **Secrets** → Settings ▸ Secrets and variables ▸ Actions ▸ New repository secret
   - `SARAMIN_KEY` : 사람인 오픈API access-key
2. **Pages** → Settings ▸ Pages ▸ Source `Deploy from a branch`, Branch `main` / `/docs`
   - 무료 플랜은 **공개 저장소**에서만 Pages가 동작한다
3. **첫 실행** → Actions ▸ daily collect ▸ Run workflow

## 호출 예산

사람인 API는 1일 500회 제한. 이 저장소는 하루 **47회**만 쓴다.

| 대상 | 호출 수 |
|---|---|
| 서울 전체 | 1 |
| 자치구 25개 | 25 |
| 직무 대분류 21개 | 21 |

개별 공고를 받지 않고 `count=1`로 응답의 `total` 값만 읽는다.
구 × 직무 교차(525회)는 한도를 넘으므로 각각의 합계만 수집한다.

## 알아둘 것

- **공고 건수 ≠ 채용 인원수.** 한 공고에 여러 명을 뽑을 수 있고, 마감된 공고는 빠진다.
- 사람인 지역은 공고에 표기된 근무지, work24는 사업장 소재지 기준이라 모집단이 다르다.
- work24는 10회에 1회꼴로 무응답 타임아웃이 난다. `common.http_get`이 4회까지 재시도한다.
- 일별 데이터는 놓친 날을 소급할 수 없다. Actions 실패 알림 메일을 꺼두지 말 것.
- `docs/data.json`에 `"mock": true`가 있으면 화면 상단에 샘플 데이터 경고가 뜬다.
  실수집이 시작되면 자동으로 사라진다.
