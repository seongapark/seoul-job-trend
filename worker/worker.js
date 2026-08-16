/**
 * Cloudflare Worker — 대시보드 Q&A 프록시
 *
 * 왜 필요한가: GitHub Pages는 정적 호스팅이라 API 키를 둘 곳이 없다.
 * 저장소가 공개면 키가 그대로 노출되므로, 키는 이 Worker의 시크릿에만 둔다.
 *   브라우저 → Worker(키 보관) → Claude API
 *
 * 배포:
 *   1) npm i -g wrangler && wrangler login
 *   2) wrangler deploy
 *   3) wrangler secret put ANTHROPIC_API_KEY
 *   4) 발급된 주소를 docs/index.html 의 QA_ENDPOINT 에 적는다
 */

const CONTEXT_URL = "https://seongapark.github.io/seoul-job-trend/context.json";
const ALLOW_ORIGIN = "https://seongapark.github.io";
const MODEL = "claude-haiku-4-5";

const SYSTEM = `너는 서울 채용트렌드 대시보드의 데이터 안내자다.

절대 규칙:
1. 답변에 등장하는 모든 숫자는 아래 CONTEXT JSON에서 그대로 가져온다. 계산은 CONTEXT의 값끼리만 한다.
   CONTEXT에 없는 수치는 절대 지어내지 않는다. 일반 상식이나 외부 통계를 끌어오지 않는다.
2. 질문이 CONTEXT로 답할 수 없는 것이면 먼저 "그건 이 데이터로 알 수 없다"고 분명히 말한다.
   그 다음 "대신 볼 수 있는 것"으로 CONTEXT 안의 가장 가까운 대리지표를 제시하고,
   그 대리지표가 왜 완전한 답이 아닌지 한 줄로 덧붙인다. 그냥 거절만 하지 않는다.
3. 사람인 공고수는 '공고 건수'이지 채용 인원수가 아니다. 채용 성사 여부도 알 수 없다.
   증감을 좋다/나쁘다로 단정하지 말고, 계절성·주말효과·마감시점 영향을 짚는다.
4. 사람인(근무지 표기 기준, 일 단위)과 work24(사업장 소재지 기준, 월 단위)는 모집단과 기준이 다르다.
   둘을 비교할 때는 이 차이를 반드시 언급한다.
5. 여러 지표를 엮어 해석해도 좋지만, 어디까지가 데이터이고 어디부터가 추론인지 문장에서 구분한다.

형식: 한국어 대화체. 3~6문장 또는 짧은 목록. 숫자는 천단위 쉼표. 서론 없이 바로 답한다.`;

export default {
  async fetch(req, env) {
    const cors = {
      "Access-Control-Allow-Origin": ALLOW_ORIGIN,
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST") return new Response("POST only", { status: 405, headers: cors });

    const { question } = await req.json();
    if (!question || question.length > 500)
      return Response.json({ answer: "질문이 비었거나 너무 깁니다." }, { headers: cors });

    // 컨텍스트는 서버에서 직접 받아온다 (클라이언트가 바꿔치기 못하도록)
    const ctx = await (await fetch(CONTEXT_URL, { cf: { cacheTtl: 600 } })).text();

    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 700,
        system: SYSTEM + "\n\n<CONTEXT>\n" + ctx + "\n</CONTEXT>",
        messages: [{ role: "user", content: question }],
      }),
    });

    if (!r.ok)
      return Response.json({ answer: "AI 응답 실패: " + r.status }, { headers: cors });
    const j = await r.json();
    return Response.json({ answer: j.content?.[0]?.text ?? "(빈 응답)" }, { headers: cors });
  },
};
