# NH PLUG 공식 공개 예제 fixture

이 fixture는 공식 API 문서의 `resExample`이며 줄바꿈만 LF로 통일했습니다. 실계좌 응답이나 실제 인증·조회 증거가 아닙니다. `ACCOUNT NUMBER`와 `TOKEN`은 공식 문서의 placeholder입니다.

출처: https://www.nhplug.com/apiservice (2026-11-06 공개 문서 캡처). 각 원본 API metadata: `https://www.nhplug.com/api/apis/public/<api_id>`.

| Fixture | API ID | Path |
| --- | --- | --- |
| token.json | dba721ee-1584-4fde-8164-92c028dc760c | /oauth2/token |
| accounts.json | 60ede1bb-ae2e-4a93-8a96-4980478a45c7 | /n2/acctinfo |
| kr_balance.json | 29b936b9-dbcd-45a9-8b1b-aa56e7e6f7df | /krstock/inquiry/v1/balance |
| us_balance.json | a96709e0-23ce-4252-9dd2-fb0f9eed2cb3 | /gbstock/inquiry/v1/balance |
| kr_executions.json | ac080b4d-1c7a-4ae8-af9d-afab86520910 | /krstock/inquiry/v1/dailyOrderExecution |
| us_history.json | fade3a9b-24f1-4adf-afbf-1ae2ae627425 | /gbstock/inquiry/v1/dailyTransaction |

응답 header는 공식 body 예제에 포함되어 있지 않습니다. 테스트 transport의 `cts_flag=N`은 합성 header이며 paging/error 변형 사례 역시 합성입니다.

정규화 계약: KR `rsdl_qty`는 `itg_bnc_qty`와 미결제 수량을 포함한 잔량입니다. US `cns_bse_bnc_qty`는 체결기준잔고이고 `fc_phs_uit_pr`는 외화매입단가입니다. `fc_sec_end_pr`는 외화증권종가이며 실제 거래일은 이 API가 제공하지 않습니다. 외화/KRW 평가손익을 각각 보존합니다.

KR 주문체결 예제에서 응답 필드는 `cfd_lon_cd`인 반면 field metadata는 `cfd_lon_cd_nm`입니다. 둘 다 신용구분 값으로 수용하되 누락/불일치는 오류로 처리합니다.

정상 업무코드는 공개 예제의 계좌 `00000`, 조회 `00166`을 허용합니다. 실제 거래 조회에서 확인한 무내역 `11512`는 거래 API에서 `Output_0=[]`이며 마지막 페이지인 경우에만 허용합니다. 이 무내역 경계의 테스트는 합성 응답이며 개인 raw 응답은 보존하지 않습니다. 알려지지 않은 코드는 빈 성공으로 간주하지 않습니다.

US 거래 전·후 잔고(`trd_bf_bnc_qty`, `trd_af_bnc_qty`)는 제공되면 Decimal로 보존합니다. 수집한 매매와 이 수량이 맞지 않거나 시작 전 보유가 확인되면 일지를 불완전으로 표시합니다. source 잔고는 해당 거래 당시 사실이며 현재 실계좌 잔고를 뜻하지 않습니다.
