# 증권사 리포트 가치 매기기 Streamlit 앱

텔레그램 공개 채널 `https://t.me/DOC_POOL`에 올라오는 증권사 리포트 게시글을 읽어 섹터별로 분류하고, 읽어볼 가치와 짧은 요약을 보여주는 Streamlit 앱입니다.

## 실행

```powershell
pip install -r requirements.txt
streamlit run app.py
```

PDF 분류를 쓰기 전에 로컬에서 Telegram 세션을 먼저 생성하세요.

```powershell
python make_telegram_session.py
```

전화번호는 `+8210...` 형식으로 입력합니다. 인증이 끝나면 `doc_pool.session` 파일이 생성되고, 이후 Streamlit 앱에서 PDF 분류를 실행할 수 있습니다.

## 동작 방식

- 기본 수집 방식은 텔레그램 공개 미리보기 페이지(`https://t.me/s/DOC_POOL`) 파싱입니다.
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, 인증된 `doc_pool.session` 또는 `TELEGRAM_STRING_SESSION`이 있으면 게시글 수집은 Telethon을 우선 사용합니다.
- 로그인이나 Telegram API 키 없이도 일부 동작할 수 있지만, 텔레그램이 공개 미리보기를 제한하면 게시글이 비어 보일 수 있습니다.
- 안정적으로 운영하려면 Telegram API 설정을 권장합니다.
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`
  - `TELEGRAM_SESSION` 선택값, 기본값은 `doc_pool.session`
  - `TELEGRAM_STRING_SESSION` 선택값, Streamlit Cloud 같은 배포 환경에서 파일 세션 대신 사용
- Telegram API 설정이 있고 앱에서 `Gemini PDF 분류 실행`을 켜면 PDF를 다운로드해 본문을 추출하고 Gemini로 요니쿠니봇식 7개 항목 축약 분석을 수행합니다.
- Streamlit 앱 안에서는 Telegram 전화번호 인증을 받지 않습니다. `make_telegram_session.py`로 세션을 먼저 만든 뒤 앱을 실행하세요.
- 동일 PDF는 SHA-256 해시로 중복 체크합니다. 한 번 분류된 PDF는 다시 올라와도 기존 결과를 재사용합니다.
- `GEMINI_API_KEY`가 없으면 PDF 다운로드/중복 등록까지만 가능하고 Gemini 분류는 실행되지 않습니다.
- `OPENAI_API_KEY`가 있으면 원하는 리포트 카드에서 `GPT 상세분석`을 눌러 해당 PDF만 심층 분석할 수 있습니다. GPT는 Gemini 1차 분석 JSON과 PDF 본문을 함께 받아 교차검증, 레이팅/읽어볼 가치 재판정, 심층 보완 분석을 수행합니다.
- GPT 상세분석 결과도 SQLite에 저장되어 같은 모델/프롬프트 방식으로 다시 누르면 재사용됩니다.
- GPT 상세분석은 `prompts/report_detail.md`의 Gemini 교차검증 + 7개 목차 프롬프트를 따릅니다. 현재 앱은 저장된 PDF 본문을 기반으로 분석하며, DART/뉴스/IR 웹 검색은 자동 수집하지 않으므로 PDF에 없는 최신 외부 데이터는 `확인 필요`로 표시하게 했습니다.
- Gemini PDF 분류를 실행하지 않으면 읽을 가치는 `미분류`로 표시됩니다. 요니쿠니봇식 판단은 PDF 본문 분석 후에만 표시됩니다.
- 요니쿠니봇의 기존 분석 기준은 `PROMPT.md`에 정리했고, 실제 분류용 프롬프트는 `prompts/report_classifier.md`에 분리했습니다.
- PDF 중복 분석 방지를 위해 `report_store.py`에 SHA-256 해시 기반 SQLite 캐시 구조를 준비했습니다. 같은 PDF는 한 번만 분류하고, 이후 동일 파일은 기존 분류 결과를 재사용하는 방식입니다.

## 환경변수

```powershell
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
MAX_PDF_TEXT_CHARS=120000
DETAIL_TARGET_SECTORS=
```

`GEMINI_MODEL`과 `OPENAI_MODEL`은 필요에 따라 바꿀 수 있습니다.

앱의 `가져올 최신 게시글 수`는 텔레그램 채널에 올라온 최신 게시글 N개를 의미합니다. 텔레그램 앱에 표시되는 읽지 않은 글 수와는 무관합니다.

상세분석 후보 조건은 다음 환경변수로 조정합니다.

- `DETAIL_TARGET_SECTORS=`: 비워두면 전체 섹터를 대상으로 상세분석 후보를 표시합니다. 특정 섹터만 보려면 `반도체,AI/전력인프라`처럼 쉼표로 구분합니다.
- 상세분석 후보는 다음 조건 중 하나를 만족하면 표시됩니다.
  - 레이팅 `A+`
  - 읽을 가치 `필독`
  - 레이팅 `B+` 이상이면서 읽을 가치 `권장` 또는 `필독`

Gemini PDF 분류는 모든 수집 PDF에 대해 1차 JSON 분류를 수행하고, 상세분석 후보 조건은 화면에서 우선적으로 눈여겨볼 리포트를 표시하는 용도입니다. GPT 상세분석 버튼은 PDF 본문이 저장된 리포트라면 레이팅/읽을 가치와 무관하게 직접 실행할 수 있습니다. 버튼을 누르기 전에는 GPT 비용이 발생하지 않습니다.

Gemini PDF 분류는 다음 7개 축약 항목을 JSON으로 저장합니다.

1. 핵심 투자 아이디어
2. 산업과 비즈니스 모델
3. 실적 변화 신호
4. 재무 건전성 및 수익성
5. 밸류에이션
6. 모멘텀과 리스크
7. 종합판단

읽을 가치는 5단계입니다.

- `필독`: 투자판단을 바꿀 수 있는 핵심 변화, 큰 실적 서프라이즈, 투자의견/목표가 대폭 변경, 구조적 변곡점
- `권장`: 신규 성장 논리, 의미 있는 실적 추정 변화, 중요한 리스크/기회 발견
- `무난`: 읽을 정보는 충분하지만 필독/권장만큼 투자판단을 바꾸는 수준은 아님
- `참고`: 기존 논리 보강, 소폭 추정치 변경, 일반 업데이트
- `스킵 가능`: 새 정보가 적거나, 제목/자료 저장 이상의 의미가 작거나, 반복적/홍보성/형식적 내용으로 실질 정보가 거의 없음

레이팅은 투자 아이디어 자체의 매력도이고, 읽을 가치는 리포트를 읽을 우선순위입니다. Gemini는 `rating_reason`에 레이팅을 부여한 이유를 1~2문장으로 저장합니다.

## 분류 섹터

- 매크로/거시경제
- 반도체
- 디스플레이
- 2차전지
- 자동차/모빌리티
- 바이오/헬스케어
- 인터넷/게임/미디어
- 금융
- 조선/기계/방산
- 에너지/화학
- 음식료/소비재
- 통신
- 부동산/리츠
- 기타

## 다음 단계로 개선할 수 있는 부분

- 관심 종목/섹터 기준 개인화 점수화
- 백그라운드 스케줄러로 주기적 자동 수집
- Streamlit Cloud 배포용 secrets 설정 정리
