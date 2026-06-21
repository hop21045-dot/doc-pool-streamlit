# 증권사 리포트 가치 매기기 Streamlit 앱

텔레그램에서 내가 저장한 투자 글과 반도체/조선 섹터 데일리 클리핑을 누적 관리하는 Streamlit 앱입니다.

## 주요 기능

- `저장함`: 내가 하트 표시한 글 또는 저장용 채널로 전달한 글을 PDF와 함께 보관합니다.
- 저장한 글마다 웹페이지에서 관련 섹터, 관련 기업명, 태그, 메모를 직접 입력해 카테고리화할 수 있습니다.
- `데일리 클리핑`: 반도체/조선 섹터 관련 텔레그램 글을 날짜별로 모아 GPT 코멘트가 포함된 Markdown 데일리 노트로 누적 저장합니다.

## 실행

```powershell
pip install -r requirements.txt
streamlit run app.py
```

텔레그램 수집을 쓰기 전에 로컬에서 Telegram 세션을 먼저 생성하세요.

```powershell
python make_telegram_session.py
```

전화번호는 `+8210...` 형식으로 입력합니다. 인증이 끝나면 `doc_pool.session` 파일이 생성되고, 이후 Streamlit 앱에서 하트/저장 글과 데일리 클리핑을 수집할 수 있습니다.

## 동작 방식

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, 인증된 `doc_pool.session` 또는 `TELEGRAM_STRING_SESSION`으로 Telethon 수집을 사용합니다.
- 안정적으로 운영하려면 Telegram API 설정을 권장합니다.
  - `TELEGRAM_API_ID`
  - `TELEGRAM_API_HASH`
  - `TELEGRAM_SESSION` 선택값, 기본값은 `doc_pool.session`
  - `TELEGRAM_STRING_SESSION` 선택값, Streamlit Cloud 같은 배포 환경에서 파일 세션 대신 사용
- `WATCH_CHANNELS`에는 데일리 클리핑을 감시할 텔레그램 채널을 쉼표로 지정합니다. 예: `DOC_POOL,다른채널명`
- `SAVED_SOURCE_CHANNELS`를 지정하면 저장함은 해당 채널의 글을 저장합니다. 비워두면 `WATCH_CHANNELS`에서 하트 반응을 찾습니다.
- 하트 반응 수집은 Telegram API가 내 반응 정보를 노출하는 경우에만 안정적으로 동작합니다. 가장 확실한 방식은 읽고 싶은 글을 별도 저장용 채널이나 Saved Messages에 전달하고 `SAVED_SOURCE_CHANNELS`에 그 채널을 지정하는 것입니다.
- 다운로드한 PDF 파일은 `data/pdfs/{pdf_hash}.pdf`에 저장되고, 메타/분석 결과는 `data/reports.sqlite3`에 저장됩니다.
- Streamlit 앱 안에서는 Telegram 전화번호 인증을 받지 않습니다. `make_telegram_session.py`로 세션을 먼저 만든 뒤 앱을 실행하세요.
- 동일 PDF는 SHA-256 해시로 중복 체크합니다.
- `OPENAI_API_KEY`가 있으면 데일리 클리핑 생성 시 GPT가 검증/요약/투자 코멘트를 포함한 Markdown 노트를 작성합니다.

## 환경변수

```powershell
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...
WATCH_CHANNELS=DOC_POOL
SAVED_SOURCE_CHANNELS=
HEART_REACTIONS=❤️,❤,♥️,♥
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
MAX_PDF_TEXT_CHARS=120000
```

`GEMINI_MODEL`과 `OPENAI_MODEL`은 필요에 따라 바꿀 수 있습니다.

## 매일 08:30 자동 실행

Streamlit 앱 자체는 사용자가 열 때 실행되는 웹앱이므로, 매일 08:30 자동 수집은 별도 스케줄러에서 `run_daily_clipping.py`를 호출하는 방식이 안정적입니다.

```powershell
python run_daily_clipping.py --sectors 반도체,조선 --max-items 15
```

GitHub Actions, Windows 작업 스케줄러, 개인 서버 cron 등에 위 명령을 매일 08:30 KST로 등록하면 `data/reports.sqlite3`에 날짜별 데일리 클리핑이 누적 저장됩니다.

## 다음 단계로 개선할 수 있는 부분

- 관심 종목/섹터 기준 개인화 점수화
- 백그라운드 스케줄러로 주기적 자동 수집
- Streamlit Cloud 배포용 secrets 설정 정리
