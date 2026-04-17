import asyncio
import json
import os
import sys


# 프로젝트 루트 경로를 sys.path에 추가 (임포트 에러 방지)
# scripts/test_complex_map_prompt.py -> scripts -> root (2 levels)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import MappedIssueList


load_dotenv()

# ==============================================================================
# 샘플 텍스트: 매크로, 개별 기업 악재, 수주 계약, 산업 전반이 한 메시지에 섞인 케이스
# ==============================================================================
COMPLEX_MESSAGE = """
[💡4월 15일 데일리 모닝 브리핑]
간밤 뉴욕 증시는 이스라엘 지정학적 리스크 완화에도 혼조세로 마감했습니다. 3월 미 소매판매가 전월비 0.7% 급증하며 예상치(0.3%)를 크게 상회해 다시 한번 인플레이션 고착화 우려를 자극했습니다. 이 여파로 미 국채 10년물 금리가 4.6%를 넘어서며 시장 압박을 키웠습니다.

기업 단에서는 희비가 엇갈렸습니다. 테슬라는 글로벌 수요 부진으로 전 세계 인력의 10% 이상을 감축하겠다고 발표하며 주가가 5.6% 급락했습니다. 반면 오라클은 폭증하는 데이터센터 전력 수요를 감당하기 위해 블룸에너지와 연료전지 공급 계약을 체결했다는 소식이 전해지며 AI 전력 부족 사태의 피크아웃 우려를 종식시켰습니다.

국내 증시는 견조한 흐름이 기대됩니다. 어제 관세청이 발표한 데이터에 따르면, 삼양식품 트래픽으로 대변되는 라면 3월 수출액이 1,620억 원으로 전년 동기 대비 49% 폭증하며 역대 최대치를 경신했습니다. AI 업계에서도 삼성전자가 HBM 메모리의 주도권을 되찾기 위해 6세대 HBM(HBM4) 양산을 예정보다 앞당길 것이라 시사해 반도체 소부장 밸류체인 전반의 투심이 뜨거워질 전망입니다.
"""

COMPLEX_MESSAGE1 = """
**[종목 토론실 언급 증가 기업] 10시 30분**

💬 **라닉스** | 현재가 2,745 | +29.79% |
라닉스는 엔비디아의 AI 모델 '아이징' 발표와 AI 해킹 공포로 인한 보안 관련주 급등세에 포함되어 긍정적인 영향을 받고 있습니다. 또한, 양자암호 기술과 보안 위협 대응 관련주로서 시장에서 주목받고 있으며, 양자컴퓨터 관련 테마주로서 투자심리를 자극하고 있습니다.

💬 **OCI홀딩스** | 현재가 226,500 | +20.41% |
OCI홀딩스의 자회사가 스페이스X와 폴리실리콘 장기 공급 계약을 체결하여 긍정적인 영향을 받았습니다. 또한, OCI홀딩스는 재생에너지 관련 시장에서 중국 의존도를 낮추는 데 기여할 수 있는 잠재력을 가진 기업으로 평가받고 있습니다.

💬 **엑스게이트** | 현재가 12,980 | +29.93% |
엑스게이트는 양자 보안 VPN 기술을 보유하고 있어 AI 보안 위협 대안으로 주목받고 있으며, 미국 양자컴퓨터 관련 기술 소식과 엔비디아의 양자컴퓨터 AI 공개 소식에 힘입어 긍정적인 영향을 받았습니다. 또한 AI 해킹 우려로 인한 보안주 급등세에 따라 시장에서 긍정적인 반응을 얻고 있습니다.

💬 **케이씨에스** | 현재가 13,680 | +29.91% |
케이씨에스는 엔비디아의 양자컴퓨터 AI 공개 소식과 AI 해킹 공포로 인한 보안 관련주 상승세에 힘입어 주목받고 있습니다. 양자암호 및 보안 기술 관련주로서 시장에서 긍정적인 영향을 받고 있으며, 이러한 요인들로 인해 투자심리가 자극되었습니다.

💬 **드림시큐리티** | 현재가 2,730 | +30.0% |
드림시큐리티는 엔비디아의 양자컴퓨터 AI 공개 소식과 AI 해킹 우려로 인한 보안 관련주 상한가 행진에 포함되면서 긍정적인 영향을 받고 있습니다. 또한, 양자암호 및 보안 기술 관련주로서 시장에서 주목받고 있으며, 정부와 보안업계의 대응 방안 논의에 간접적으로 연관되어 투자자들의 관심이 증가할 가능성이 있습니다.

💬 **삼성에스디에스** | 현재가 180,700 | +19.27% |
삼성에스디에스는 KKR과의 전략적 협력을 위해 1조 2000억 원 규모의 전환사채 발행을 결의했으며, 이를 통해 AI 인프라 투자와 AI 전환 사업 경쟁력 강화를 위한 자금을 확보할 계획입니다. 또한, AI 관련 사업 확장과 공공 부문의 클라우드·AI 전환 사업 수주를 통해 매출처 다변화와 실적 성장에 긍정적인 영향을 받을 것으로 보입니다. 국회 빅데이터 플랫폼 구축 1단계 사업을 성공적으로 완료하고 국회AI의정지원플랫폼을 공식 오픈하여 기술적 성과를 보였습니다.

💬 **아이씨티케이** | 현재가 22,950 | +29.95% |
아이씨티케이는 엔비디아의 양자컴퓨터 관련 오픈 소스 AI 모델 공개 소식과 AI 해킹 우려로 인한 보안 관련주 상승세에 따라 긍정적인 영향을 받았습니다. 또한, 양자컴퓨터 상용화 기대감이 투자심리를 자극하며 긍정적인 영향을 미쳤습니다. 아이씨티케이는 양자암호 및 보안 기술 관련주로 시장에서 주목받고 있으며, 정부와 보안업계의 대응 방안 논의와 맞물려 단기적으로 주가 변동성이 클 수 있습니다.

💬 **큐라티스** | 현재가 786 | -13.82% |
큐라티스가 9대1 주식병합 방식의 무상감자를 결정하여 재무구조 개선을 추진하고 있습니다.

💬 **압타바이오** | 현재가 7,240 | +3.13% |
압타바이오는 FDA로부터 조영제 유발 급성신손상 치료제 임상 2상 계획 변경 승인을 받아 임상 절차가 마무리 단계에 접어들었습니다. 또한 하반기 탑라인 결과 도출을 통해 글로벌 빅파마와의 기술수출 및 공동개발 논의를 본격화할 계획입니다. 암연관섬유아세포 저해 기전의 차세대 면역항암제 연구 성과 발표도 예정되어 있어 연구개발 활동에 긍정적인 영향을 미칠 수 있습니다.
"""

COMPLEX_MESSAGE2 = """
**✅ 중국 태양광 장비 대미 규제, 한국 업체에 기회 될까**

**📌 산업 관점: 한국 장비업체에 열릴 수 있는 기회**

**1. 공급망 다변화 수요 확대**
미국은 태양광 제조 공급망의 탈중국화(De-risking)를 지속적으로 추진하고 있음.

중국의 수출 제한이 현실화될 경우, ☀️**한국·유럽·일본 장비 업체로 대체 수요가 이동할 가능성이 높음**.

**2. 정책 수혜 기대**
미국 내 태양광 생산 확대 기조와 맞물려,  ☀️**비중국 장비 업체에 대한 선호가 더욱 강화**될 수 있음.

**3. 한국 업체의 기술 경쟁력**
일부 한국 장비 업체들은 자동화, 정밀 공정, 검사 장비 등에서 경쟁력을 확보하고 있어, 

 ☀️**특정 공정 중심의 수혜가 가능**할 것으로 예상됨.

**📌 주목 포인트: 어디서 수혜가 발생할까**

**✔️ 관심 분야**
• PECVD / PVD 장비
• 셀·모듈 자동화 장비
• 검사·측정 장비
• 레이저 가공 장비

**✔️ 차세대 태양광으로의 확산 가능성**
실리콘 중심 시장 외에도 
💥**페로브스카이트 등 차세대 태양광 기술 도입 논의**가 빨라질 가능성이 있음.

이 과정에서 💥**페로브스카이트 관련 장비 업체들 역시 시장의 관심**을 받을 수 있음.

**📌 관심 기업: 직접 수혜 가능 업체들**

🌞 **1. 주성엔지니어링**
HJT용 PECVD, 페로브스카이트용 ALD/CVD·PVD 등 태양전지 제조장비 개발.

**HJT 셀과 페로브스카이트 셀을 결합한 탠덤 장비 개발**도 진행 중.

중국산 첨단 태양광 장비의 대체 공급처로 💥**가장 직접적인 후보로 평가** 가능.

**🌞**** 2. 선익시스템**
**페로브스카이트 증착 장비 관련 레퍼런스를** 보유한 업체.

OLED 증착 공정과 페로브스카이트 증착 공정 간 기술적 접점이 존재함.

OLED 증착 장비 시장에서 독점 구도를 뚫어낸 높은 기술력을 바탕으로, 
💥**향후 페로브스카이트 증착 장비 분야에서도 선도 업체로 부각**될 가능성이 있음.

**✅독립리서치 그로쓰리서치**
https://t.me/growthresearch
"""

COMPLEX_MESSAGE3 = """

▶ CCL price hikes to extend through 2026 with rising glass fiber and copper foil costs

- AI 서버·스위치 수요 확대 영향으로 고급 PCB 수요 급증하며 업스트림 소재 공급 불균형 심화, CCL 가격 상승 공급망 전반으로 확산되며 PCB 업체들도 가격 조정 단행

- CCL 가격 인상은 유리섬유 직물과 동박 비용 상승으로 2026년 연말까지 지속 전망, M6~M8 전 제품군에서 두 자릿수 인상 시작 및 연간 누적 인상 확대

- 대만 EMC, TUC, ITEQ, Nan Ya Plastics, Ventec 등은 생산 비용 상승을 반영한 단계적 가격 인상 진행 예정

- 핵심 원인은 유리섬유 직물 쇼티지로, E-glass·저유전율 소재·T-glass 전반 가격 상승하며 생산 효율 및 수율 문제로 고급 소재 가격은 연간 20~30% 상승 예상

- Nittobo, Asahi Kasei, Taiwan Glass, Taishan Fiberglass 등 주요 공급사 수혜, Fu Chiao, Hong Ho 등 2차 공급사도 출하 확대 기회

- 특히 Thin E-glass는 주요 업체 캐파 집중 영향으로 공급 부족 심화되며 2025년 30% 상승에 이어 2026년 100% 이상 상승 예상

- 동박 역시 국제 구리 가격 상승과 HVLP 공급 부족 심화로 가격 상승, HVLP 공급 부족은 2026년 48%, 2027년 43% 수준 예상

- Mitsui, Furukawa, Co-Tech, Circuit Foil 등 주요 업체들이 가격 인상 주도, 평균 가격은 kg당 2달러 상승했으며 추가 인상 전망

- Panasonic은 2026년 5월부터 15~30% 가격 인상 시행 예정, TUC도 4월 25일부터 20~40% 인상 발표

- Resonac과 Mitsubishi Gas Chemical도 30% 수준의 추가 인상을 단행하며 소재 가격 상승이 글로벌하게 확산

https://buly.kr/6tdlAj0 (Digitimes Asia)
"""

COMPLEX_MESSAGE4 = """

'3월 ESS Battery : 유럽 Grid ESS 증가'

자료 링크: https://vo.la/FlbTVBx

▶ ESS 신규 설치 현황

- 3월 글로벌 ESS 신규 설치량: 24.2GWh(YoY +32.9%)

▶ ESS 연계 유형별 누적 설치 현황(3월)

- 독립형: 12.6GWh(YoY +62.0%)
- 풍력+태양광 연계: 0.8GWh(YoY N/A)
- 풍력 연계: 0.3GWh(YoY +79.7%)
- 태양광 연계: 3.8GWh(YoY -13.5%)

▶ 시사점 및 의견: 장주기 ESS 설치 확대 전망

- 3월 글로벌 ESS 신규 설치량(Grid+BTM)은 24.2GWh로, 전년 대비 +33% 증가했다. 2026년 1분기 기준으로는 68.5GWh의 신규 ESS가 설치되며 전년 동기 대비 +29% 증가했으며, 오세아니아 지역의 대형 프로젝트 가동과 유럽의 견조한 수요 증가 등이 맞물린 영향으로 분석된다.

- 신규 설치량의 76%를 차지하는 전력망(Grid) ESS의 경우, 3월에 18.4GWh(YoY +49%) 규모의 ESS가 새로 설치돼 가동을 시작했다. 지역별로 보면, 3월 신규 설치량은 미국을 제외한 모든 지역에서 성장을 보였다. 다만, 누적 기준으로는 모든 지역에서 설치량이 증가했고, 특히 유럽의 증가폭이 컸다(+110%). 이는 재생에너지 확대에 따른 ESS 수요 증가와 지연됐던 전력 프로젝트의 상업운전(COD) 집중에 기인한 것으로 판단된다.

- 설치량 중 24%를 차지하는 BTM(Behind The Meter) 시장에서는 3월에 글로벌 5.9GWh(YoY Flat)의 ESS가 신규 설치돼 가동을 시작했다. 모든 지역(미국, 유럽, 중국, 기타)에서 신규 설치량은 전년 대비 Flat 수준이었다. 

- 전력망(Grid) 시장 내 연계유형별 설치량을 살펴보면, 송전망에 직접 연결돼 전력 상황에 따라 충·방전을 하는 독립형 BESS(Stand-alone BESS)의 경우 3월 12.6GWh가 신규 설치되며 전년 대비 +62% 증가했다. 3월 풍력 연계 ESS 설치량은 전년 0.3GWh로 전년 대비 +80% 증가했으나, 태양광 연계 ESS는 3.8GWh로 -14% 감소하면서, 전체 재생에너지(풍력·태양광·하이브리드(풍력+태양광) 합산) ESS 합산 설치량은 3월 4.9GWh로, 전년 대비 -21% 감소했다. 다만 재생에너지 프로젝트는 입찰·인허가 일정이 특정 시점에 집중되는 특성이 있어, 2026년 3월의 YoY 감소는 수요 둔화에 기인하기보다 입찰·가동 스케줄에 따른 영향이라고 해석된다.

- 최근 중동 지역의 지정학적 리스크 확대에 따른 에너지 안보 중요성 부각으로 재생에너지 확대 기조가 강화되는 가운데, 전력 수급 안정성 확보를 위한 ESS 수요 또한 동반 증가할 것으로 예상된다. 특히 간헐성이 높은 재생에너지 비중 확대에 대응하기 위해, 장시간 전력 공급이 가능한 장주기 ESS의 필요성이 부각되고 있다. 2024년 캘리포니아 공공유틸리티위원회(CPUC)는 2029~2032년까지 6GW 규모의 청정에너지 전력 조달을 의무화하고, 이 중 최소 25%를 확정용량(firm capacity, 전력 수요 피크 시 안정적으로 공급 가능한 용량)으로 확보하도록 요구한 바 있다. 이후 2026년 3월 조달 방식 결정에서는 해당 6GW를 단순 설비의 총용량이 아닌, 실제 전력 수요 시 공급 가능한 수준(인정용량, NQC)을 기준으로 평가하는 방향으로 강화했다. 이러한 기준 변화에 따라 실제 공급 가능한 용량을 충족하기 위해 장주기 ESS 중심의 시장 성장세 가속화될 것으로 판단된다. 이처럼 ESS는 단순 저장 수단을 넘어 전력 공급 자원으로서의 역할이 강화되고 있으며, 향후 장주기 ESS 중심의 설치 확대가 본격화될 것으로 판단한다.
"""


# ==============================================================================
# 테스트할 시스템 프롬프트 (5번 '복합 메시지 분할' 지침 추가버전)
# ==============================================================================
TEST_SYSTEM_PROMPT = """
당신은 한국 금융 시장 전문 애널리스트이자 투자 전략가입니다.
메시지를 분석하여 '투자 가치가 있는 이슈'로 압축하세요.

**⚠️ 절대 금지**: 중복된 내용이 반복 생성되지 않게 필수 핵심 이슈들만 묶어서 한 번씩 추출하세요.

**핵심 지침 (Core Instructions)**:
1. **데이터 보존 (Data Integrity)**: 원문에 등장하는 모든 숫자(%, 금액, 날짜, 목표주가 변동 등)는 요약문에 반드시 포함하세요. 
2. **의미론적 클러스터링**: 단순 기업별 나열이 아니라 '현상' 위주로 묶으세요.
3. **테마 작명법**: 섹터 명칭(반도체, 음식료) 대신 '투자 내러티브'가 담긴 테마를 부여하세요.
   - 추천: ["AI 전력 병목 해소"], ["K-푸드 글로벌 수주 모멘텀"], ["HBM 선단공정 속도전"]
4. **Takeaway 추출**: 이 뉴스가 오늘 왜 중요한지, 어떤 변수를 건드리는지(P, Q, C 관점) 요약 마지막에 한 문장으로 정리하세요.

5. **복합 메시지 분할(디커플링)**: 하나의 긴 메시지(아침 시황 등)에 매크로, 반도체, 소비재 등 전혀 다른 여러 주제가 섞여 있다면 절대 1개로 뭉뚱그리지 마세요. 반드시 '상호 독립적인 투자 테마' 단위로 분리하여 여러 개의 개별 JSON 객체로 쪼개서 추출하세요. (서로 다른 테마라면 원본 출처 ID가 동일해도 개별 이슈로 생성해야 합니다.)
"""


async def run_test(
    model_name: str, temperature: float, provider: str = "openai", use_bedrock: bool = True
):
    # Bedrock 사용 여부 명시적 설정
    if not use_bedrock:
        os.environ["CLAUDE_CODE_USE_BEDROCK"] = "0"

    # 모델 정의
    llm = LLMProvider.create(provider=provider, model=model_name, temperature=temperature)

    message = (
        COMPLEX_MESSAGE + COMPLEX_MESSAGE1 + COMPLEX_MESSAGE2 + COMPLEX_MESSAGE3 + COMPLEX_MESSAGE4
    )

    # 채널명-메시지ID 형태로 가상 포맷팅
    formatted_msg = f"[MorningBrief-101] {message.strip()}"
    user_prompt = f"**입력 (1개 메시지)**:\n{formatted_msg}"

    messages = [
        SystemMessage(content=TEST_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    print(f"\n🚀 테스트 시작... (Model: {model_name}, Temp: {temperature})")

    try:
        # Structured Output 강제 추출
        llm_with_output = llm.with_structured_output(MappedIssueList)

        # LangSmith 트래킹을 위한 태그 및 이름 설정
        config = {
            "tags": [model_name, f"temp-{temperature}", "complex_map_test"],
            "run_name": f"TestComplexMapPrompt-{model_name}-T{temperature}",
        }

        response = await llm_with_output.ainvoke(messages, config=config)

        # 결과 파일 저장
        output_dir = os.path.join(PROJECT_ROOT, "scripts", "test_outputs")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"map_result_{model_name}_T{temperature}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(response.model_dump(), f, ensure_ascii=False, indent=2)

        print(f"✅ 테스트 완료! 결과 저장됨: {filepath}")
        print(f"  - 분할된 이슈 개수: {len(response.issues)}")

        for idx, issue in enumerate(response.issues, 1):
            print(f"  [{idx}] {issue.title} ({issue.sentiment.upper()})")

    except Exception as e:
        print(f"⚠️ 에러 발생 ({model_name}, T={temperature}): {e}")


if __name__ == "__main__":
    # 테스트할 조합 설정
    target_models = [
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ]
    target_temperatures = [0.1]

    async def main():
        for model in target_models:
            for temp in target_temperatures:
                await run_test(model, temp, provider="anthropic")

    asyncio.run(main())

    # async def main2():
    #     for temp in [0.0, 0.1, 0.2]:
    #         await run_test(
    #             "us.anthropic.claude-sonnet-4-5-20250929-v1:0", temp, provider="claude"
    #         )

    # asyncio.run(main2())
