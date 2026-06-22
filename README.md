# 증권사 리포트 가치 매기기 Streamlit 앱

텔레그램에서 내가 저장한 투자 글과 반도체/조선 섹터 데일리 클리핑을 누적 관리하는 Streamlit 앱입니다.

## 주요 기능

- `저장함`: 내가 하트 표시한 글 또는 저장용 채널로 전달한 글을 PDF와 함께 보관합니다.
- 저장한 글마다 웹페이지에서 관련 섹터, 관련 기업명, 태그, 메모를 직접 입력해 카테고리화할 수 있습니다.
- `데일리 클리핑`: 반도체/조선 섹터 관련 텔레그램 글을 날짜별로 모아 GPT 코멘트가 포함된 Markdown 데일리 노트로 누적 저장합니다.
- `반도체 스팟가격 현황`: 키움 반도체 채널의 DRAMeXchange 스팟가격 게시글과 이미지 표를 별도 카테고리로 저장하고 조회합니다. 과거 데이터는 Telegram Desktop export ZIP/JSON으로 한 번에 가져오고, 이후에는 GitHub Actions가 최신 글을 자동 수집합니다.

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
- `SEMICON_CHANNELS`에는 반도체 클리핑에 사용할 텔레그램 채널을 쉼표로 지정합니다. 예: `lupang_channel,kaie_channel`
- `SHIPBUILDING_CHANNELS`에는 조선 클리핑에 추가로 볼 텔레그램 채널을 지정합니다. 비워두면 조선은 업계 뉴스 RSS 중심으로 수집합니다.
- `SHIPBUILDING_NEWS_QUERIES`에는 조선 업계 뉴스 검색어를 쉼표로 지정합니다. LNG 프로젝트뿐 아니라 가스선, 탱커, 컨테이너선, 벌크선, 특수선, 지정학, 에너지 안보, 운임/선가, 미국/인도 조선업 육성, 해군/MRO 이슈를 함께 넣는 것이 좋습니다.
- `SPOT_PRICE_CHANNEL`에는 반도체 스팟가격 게시글을 올리는 텔레그램 채널명을 지정합니다. 기본값은 `kiwoom_semibat`입니다.
- `SPOT_PRICE_DAILY_LIMIT`에는 매일 자동으로 확인할 스팟가격 최신 글 수를 지정합니다. 기본값은 `30`입니다.
- `WATCH_CHANNELS`는 저장함/기본 fallback 채널입니다.
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
SEMICON_CHANNELS=
SHIPBUILDING_CHANNELS=
SHIPBUILDING_NEWS_QUERIES=LNG carrier order Korea shipyard,LPG carrier VLGC order,VLAC ammonia carrier order,tanker newbuilding order,container ship newbuilding order,bulk carrier order,offshore wind vessel order,FSRU FLNG FPSO order,Clarksons newbuilding price,shipping rates vessel order,geopolitical shipping route tanker LNG carrier,energy security LNG shipping,US shipbuilding policy Navy MRO,India shipbuilding policy,Make in India shipbuilding,commercial shipbuilding revival United States,naval shipbuilding Korea MRO,HD한국조선해양 수주,HD현대중공업 수주,삼성중공업 수주,한화오션 수주,현대미포조선 수주,대한조선 수주,HJ중공업 수주,LNG선 발주 VLGC 탱커 컨테이너선,해운 운임 선박 발주,홍해 수에즈 파나마 운하 해운 조선,에너지 안보 LNG 운반선 조선,미국 조선업 재건 해군 MRO,인도 조선업 육성
SPOT_PRICE_CHANNEL=kiwoom_semibat
SPOT_PRICE_DAILY_LIMIT=30
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

GitHub Actions를 사용할 때는 `SEMICON_CHANNELS`에 루팡/카이에 채널의 실제 텔레그램 username을 넣고, 조선은 `SHIPBUILDING_NEWS_QUERIES` 검색어를 통해 선종별 발주 신호와 업계 뉴스를 수집합니다.

## 다음 단계로 개선할 수 있는 부분

- 관심 종목/섹터 기준 개인화 점수화
- 백그라운드 스케줄러로 주기적 자동 수집
- Streamlit Cloud 배포용 secrets 설정 정리
