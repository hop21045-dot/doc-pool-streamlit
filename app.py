from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from report_store import (
    get_detailed_analysis,
    get_cached_classification,
    get_stored_report,
    hash_pdf_bytes,
    register_pdf,
    save_classification,
    save_detailed_analysis,
    save_extracted_text,
)


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

CHANNEL = "DOC_POOL"
TELEGRAM_PREVIEW_URL = f"https://t.me/s/{CHANNEL}"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
MAX_PDF_TEXT_CHARS = int(os.getenv("MAX_PDF_TEXT_CHARS", "120000"))
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")


SECTOR_KEYWORDS: dict[str, list[str]] = {
    "매크로/거시경제": [
        "macro",
        "매크로",
        "거시",
        "경제",
        "금리",
        "환율",
        "연준",
        "fed",
        "fomc",
        "물가",
        "cpi",
        "pce",
        "gdp",
        "수출",
        "무역",
        "달러",
        "채권",
    ],
    "반도체": [
        "반도체",
        "삼성전자",
        "sk하이닉스",
        "하이닉스",
        "hbm",
        "dram",
        "낸드",
        "nand",
        "파운드리",
        "tsmc",
        "엔비디아",
        "nvidia",
        "asic",
        "memory",
    ],
    "디스플레이": [
        "디스플레이",
        "oled",
        "lcd",
        "패널",
        "lg디스플레이",
        "qd-oled",
        "마이크로led",
    ],
    "2차전지": [
        "2차전지",
        "이차전지",
        "배터리",
        "battery",
        "양극재",
        "음극재",
        "전해액",
        "분리막",
        "리튬",
        "lg에너지솔루션",
        "에코프로",
        "포스코퓨처엠",
    ],
    "자동차/모빌리티": [
        "자동차",
        "현대차",
        "기아",
        "전기차",
        "ev",
        "테슬라",
        "tesla",
        "모빌리티",
        "자율주행",
    ],
    "바이오/헬스케어": [
        "바이오",
        "헬스케어",
        "제약",
        "신약",
        "임상",
        "셀트리온",
        "삼성바이오",
        "의료기기",
    ],
    "인터넷/게임/미디어": [
        "인터넷",
        "게임",
        "미디어",
        "엔터",
        "광고",
        "네이버",
        "카카오",
        "크래프톤",
        "넷마블",
        "콘텐츠",
    ],
    "금융": [
        "은행",
        "증권",
        "보험",
        "금융",
        "카드",
        "지주",
        "kb금융",
        "신한지주",
        "하나금융",
    ],
    "조선/기계/방산": [
        "조선",
        "선박",
        "lng",
        "방산",
        "기계",
        "한화에어로",
        "현대로템",
        "hd현대",
    ],
    "에너지/화학": [
        "정유",
        "화학",
        "태양광",
        "에너지",
        "석유",
        "가스",
        "수소",
        "효성",
        "롯데케미칼",
    ],
    "음식료/소비재": [
        "음식료",
        "소비재",
        "화장품",
        "유통",
        "면세",
        "의류",
        "cj제일제당",
        "아모레",
    ],
    "통신": ["통신", "통신서비스", "sk텔레콤", "kt", "lg유플러스", "5g", "6g"],
    "부동산/리츠": ["부동산", "리츠", "건설", "주택", "오피스", "물류센터"],
}

VALUE_KEYWORDS = {
    "high": [
        "initiation",
        "신규",
        "개시",
        "탑픽",
        "top pick",
        "전망",
        "outlook",
        "산업분석",
        "deep dive",
        "인뎁스",
        "실적 프리뷰",
        "실적 리뷰",
        "컨퍼런스",
        "리포트",
    ],
    "medium": [
        "update",
        "업데이트",
        "comment",
        "코멘트",
        "daily",
        "weekly",
        "월보",
        "주간",
    ],
}


@dataclass(frozen=True)
class ReportPost:
    message_id: str
    posted_at: str
    title: str
    text: str
    link: str
    views: str
    file_name: str = ""
    pdf_hash: str = ""
    duplicate_pdf: bool = False
    classification: dict[str, Any] | None = None
    classification_model: str = ""
    processing_note: str = ""


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def fetch_channel_posts(limit: int, classify_pdfs: bool) -> list[ReportPost]:
    if classify_pdfs and os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"):
        return asyncio.run(fetch_channel_posts_with_telethon(limit, classify_pdfs))
    return fetch_channel_posts_from_preview(limit)


async def fetch_channel_posts_with_telethon(limit: int, classify_pdfs: bool) -> list[ReportPost]:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.getenv("TELEGRAM_SESSION", "doc_pool.session")
    string_session = os.getenv("TELEGRAM_STRING_SESSION")
    session_arg = StringSession(string_session) if string_session else session
    posts: list[ReportPost] = []

    client = TelegramClient(session_arg, api_id, api_hash)
    async with client:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram 세션 인증이 필요합니다. Streamlit을 끄고 "
                "`python make_telegram_session.py`를 먼저 실행해 doc_pool.session을 생성하세요."
            )
        async for message in client.iter_messages(CHANNEL, limit=limit):
            text_parts = [message.message or ""]
            document_name = get_telethon_document_name(message)
            if document_name:
                text_parts.append(document_name)
            raw_text = normalize_text(" ".join(text_parts))
            if not raw_text and not document_name:
                continue
            message_id = str(message.id)
            link = f"https://t.me/{CHANNEL}/{message_id}"
            pdf_hash = ""
            duplicate_pdf = False
            classification = None
            classification_model = ""
            processing_note = ""

            if document_name.lower().endswith(".pdf") and classify_pdfs:
                try:
                    pdf_bytes = await client.download_media(message, file=bytes)
                    if not pdf_bytes:
                        processing_note = "PDF 다운로드 실패"
                    else:
                        pdf_hash = hash_pdf_bytes(pdf_bytes)
                        duplicate_pdf = not register_pdf(
                            pdf_hash=pdf_hash,
                            message_id=message_id,
                            file_name=document_name,
                            file_size=len(pdf_bytes),
                            telegram_link=link,
                        )
                        cached = get_cached_classification(pdf_hash)
                        if cached:
                            classification = cached.result
                            classification_model = cached.model
                            processing_note = "중복 PDF: 기존 분류 재사용" if duplicate_pdf else "기존 분류 재사용"
                        else:
                            extracted_text = extract_pdf_text(pdf_bytes)
                            save_extracted_text(pdf_hash, extracted_text)
                            if not extracted_text:
                                processing_note = "PDF 텍스트 추출 실패"
                            elif not os.getenv("GEMINI_API_KEY"):
                                processing_note = "GEMINI_API_KEY 미설정"
                            else:
                                classification = classify_report_with_gemini(
                                    extracted_text=extracted_text,
                                    file_name=document_name,
                                    message_text=message.message or "",
                                )
                                classification_model = GEMINI_MODEL
                                save_classification(
                                    pdf_hash=pdf_hash,
                                    source_message_id=message_id,
                                    file_name=document_name,
                                    model=GEMINI_MODEL,
                                    result=classification,
                                )
                                processing_note = "Gemini 신규 분류"
                except Exception as exc:
                    processing_note = f"PDF 처리 실패: {exc}"

            posts.append(
                ReportPost(
                    message_id=message_id,
                    posted_at=message.date.isoformat() if message.date else "",
                    title=extract_title(raw_text),
                    text=raw_text,
                    link=link,
                    views=str(message.views or ""),
                    file_name=document_name,
                    pdf_hash=pdf_hash,
                    duplicate_pdf=duplicate_pdf,
                    classification=classification,
                    classification_model=classification_model,
                    processing_note=processing_note,
                )
            )

    return posts


def get_telethon_document_name(message: object) -> str:
    document = getattr(message, "document", None)
    if not document:
        return ""
    for attr in getattr(document, "attributes", []) or []:
        file_name = getattr(attr, "file_name", "")
        if file_name:
            return file_name
    return ""


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import fitz
    except ImportError:
        return ""

    text_parts: list[str] = []
    total_chars = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_index, page in enumerate(doc, start=1):
            page_text = normalize_text(page.get_text("text"))
            if not page_text:
                continue
            chunk = f"[page {page_index}]\n{page_text}"
            text_parts.append(chunk)
            total_chars += len(chunk)
            if total_chars >= MAX_PDF_TEXT_CHARS:
                break
    return "\n\n".join(text_parts)[:MAX_PDF_TEXT_CHARS]


def load_prompt(name: str) -> str:
    path = os.path.join(PROMPT_DIR, name)
    with open(path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read().strip()


def classify_report_with_gemini(
    extracted_text: str,
    file_name: str,
    message_text: str,
) -> dict[str, Any]:
    prompt = load_prompt("report_classifier.md")
    user_text = (
        f"[파일명]\n{file_name}\n\n"
        f"[텔레그램 게시글]\n{message_text or 'N/A'}\n\n"
        f"[PDF 본문]\n{extracted_text}"
    )
    raw = call_gemini_json(prompt, user_text)
    return normalize_classification(raw)


def call_gemini_json(system_prompt: str, user_text: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{system_prompt}\n\n분석 대상:\n{user_text}",
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 3000,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_json_object(text)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_classification(result: dict[str, Any]) -> dict[str, Any]:
    allowed_values = {"필독", "권장", "참고", "낮음", "스킵 가능"}
    allowed_ratings = {"A+", "A", "B+", "B", "C"}
    result = dict(result)
    if result.get("reading_value") not in allowed_values:
        result["reading_value"] = "참고"
    if result.get("rating") not in allowed_ratings:
        result["rating"] = "B"
    result.setdefault("sector", "기타")
    result.setdefault("stock_name", "미상")
    result.setdefault("stock_code", "000000")
    result.setdefault("report_title", "")
    result.setdefault("one_line_summary", "")
    result.setdefault("investment_idea", [])
    result.setdefault("earnings_signal", "N/A")
    result.setdefault("valuation_view", "N/A")
    result.setdefault("key_risks", [])
    result.setdefault("why_read", "")
    result.setdefault("needs_check", [])
    return result


def fetch_channel_posts_from_preview(limit: int) -> list[ReportPost]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    response = requests.get(TELEGRAM_PREVIEW_URL, headers=headers, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    posts: list[ReportPost] = []

    for message in soup.select(".tgme_widget_message"):
        message_id = message.get("data-post", "").split("/")[-1]
        text_node = message.select_one(".tgme_widget_message_text")
        if not text_node:
            continue

        raw_text = normalize_text(text_node.get_text(" ", strip=True))
        if not raw_text:
            continue

        date_node = message.select_one("time")
        posted_at = date_node.get("datetime", "") if date_node else ""
        link_node = message.select_one("a.tgme_widget_message_date")
        link = link_node.get("href", "") if link_node else f"https://t.me/{CHANNEL}/{message_id}"
        views_node = message.select_one(".tgme_widget_message_views")
        views = normalize_text(views_node.get_text(" ", strip=True)) if views_node else ""

        title = extract_title(raw_text)
        posts.append(
            ReportPost(
                message_id=message_id,
                posted_at=posted_at,
                title=title,
                text=raw_text,
                link=link,
                views=views,
            )
        )

    return posts[-limit:][::-1]


def extract_title(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", text).strip()
    parts = re.split(r"[|\n]| - | / ", cleaned)
    title = next((part.strip(" #[]") for part in parts if len(part.strip()) >= 4), cleaned)
    return title[:90]


def classify_sector(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    scored: list[tuple[str, int, list[str]]] = []

    for sector, keywords in SECTOR_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in lowered]
        if hits:
            scored.append((sector, len(hits), hits[:5]))

    if not scored:
        return "기타", []

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[0][0], scored[0][2]


def rate_reading_value(text: str, sector: str) -> tuple[str, str]:
    lowered = text.lower()
    high_hits = [kw for kw in VALUE_KEYWORDS["high"] if kw.lower() in lowered]
    medium_hits = [kw for kw in VALUE_KEYWORDS["medium"] if kw.lower() in lowered]

    if sector == "매크로/거시경제" and any(
        kw in lowered for kw in ["fomc", "cpi", "pce", "금리", "환율", "전망"]
    ):
        return "필독", "시장 방향성에 영향을 줄 수 있는 거시 변수입니다."
    if high_hits:
        return "필독", f"깊이 있는 리포트 신호({', '.join(high_hits[:3])})가 있습니다."
    if medium_hits:
        return "참고", f"업데이트성 자료 신호({', '.join(medium_hits[:3])})가 있습니다."
    if len(text) >= 180:
        return "권장", "본문 정보량이 충분해 빠르게 확인할 가치가 있습니다."
    return "낮음", "제목/짧은 코멘트 중심이라 우선순위는 낮게 봅니다."


def heuristic_summary(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    sentences = re.split(r"(?<=[.!?。])\s+| [•·] | #", text)
    sentences = [normalize_text(sentence) for sentence in sentences if normalize_text(sentence)]
    summary = " ".join(sentences[:2]) if sentences else normalize_text(text)
    return summary[:220] + ("..." if len(summary) > 220 else "")


def summarize_with_openai(text: str, sector: str, value: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    prompt = (
        "다음은 텔레그램 증권사 리포트 게시글입니다. "
        "투자 조언이 아니라 리포트 독서 우선순위 판단용으로만, 한국어로 2문장 이내 요약을 작성하세요. "
        f"분류 섹터: {sector}, 읽을 가치: {value}\n\n{text}"
    )
    result = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
        max_output_tokens=220,
    )
    return result.output_text.strip()


def analyze_report_with_openai(pdf_hash: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return "OPENAI_API_KEY가 설정되지 않았습니다."
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    cache_model = f"{model}:gemini-crosscheck-v1"
    cached = get_detailed_analysis(pdf_hash, cache_model)
    if cached:
        return cached

    stored = get_stored_report(pdf_hash)
    if not stored or not stored.extracted_text:
        return "저장된 PDF 본문이 없습니다. 먼저 Gemini PDF 분류를 실행해야 합니다."
    gemini = get_cached_classification(pdf_hash)
    gemini_result = (
        json.dumps(gemini.result, ensure_ascii=False, indent=2)
        if gemini
        else "Gemini 1차 분석 결과가 없습니다. PDF 본문만 근거로 분석하고, 교차검증 항목은 '확인 불가'로 표시하세요."
    )
    analysis_input = (
        "[Gemini 1차 분석 JSON]\n"
        f"{gemini_result}\n\n"
        "[PDF 리포트 본문]\n"
        f"{stored.extracted_text[:MAX_PDF_TEXT_CHARS]}"
    )

    from openai import OpenAI

    client = OpenAI()
    prompt = load_prompt("report_detail.md")
    result = client.responses.create(
        model=model,
        instructions=prompt,
        input=analysis_input,
        max_output_tokens=4000,
    )
    analysis = result.output_text.strip()
    save_detailed_analysis(pdf_hash, cache_model, analysis)
    return analysis


def build_rows(posts: Iterable[ReportPost], use_ai_summary: bool) -> list[dict[str, str]]:
    rows = []
    for post in posts:
        text_for_fallback = " ".join(part for part in [post.text, post.file_name] if part)
        sector, hits = classify_sector(text_for_fallback)
        value, reason = rate_reading_value(text_for_fallback, sector)
        summary = heuristic_summary(text_for_fallback)
        rating = ""
        stock_name = ""
        stock_code = ""
        title = post.title
        detail = ""
        risks = ""
        needs_check = ""

        if post.classification:
            result = post.classification
            sector = str(result.get("sector") or sector)
            value = str(result.get("reading_value") or value)
            rating = str(result.get("rating") or "")
            stock_name = str(result.get("stock_name") or "")
            stock_code = str(result.get("stock_code") or "")
            title = str(result.get("report_title") or post.title)
            summary = str(result.get("one_line_summary") or summary)
            reason = str(result.get("why_read") or reason)
            detail = list_to_text(result.get("investment_idea"))
            risks = list_to_text(result.get("key_risks"))
            needs_check = list_to_text(result.get("needs_check"))

        if use_ai_summary and os.getenv("OPENAI_API_KEY"):
            try:
                summary = summarize_with_openai(text_for_fallback, sector, value)
            except Exception as exc:  # Keep the app usable if one summary fails.
                summary = f"{summary} (AI 요약 실패: {exc})"

        rows.append(
            {
                "게시시각": format_datetime(post.posted_at),
                "섹터": sector,
                "레이팅": rating,
                "읽을 가치": value,
                "종목명": stock_name,
                "종목코드": stock_code,
                "제목": title,
                "요약": summary,
                "판단 근거": reason,
                "핵심 아이디어": detail,
                "핵심 리스크": risks,
                "확인 필요": needs_check,
                "키워드": ", ".join(hits),
                "조회": post.views,
                "파일명": post.file_name,
                "PDF 해시": post.pdf_hash,
                "중복 PDF": "Y" if post.duplicate_pdf else "",
                "분류 모델": post.classification_model,
                "처리 상태": post.processing_note,
                "링크": post.link,
                "본문": post.text,
            }
        )
    return rows


def list_to_text(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(str(item) for item in value if item)
    return str(value or "")


def format_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return value


def render_cards(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        with st.container(border=True):
            top = st.columns([1.2, 0.8, 1, 1, 5])
            top[0].markdown(value_label(row["읽을 가치"]), unsafe_allow_html=True)
            top[1].caption(row["레이팅"] or "등급 없음")
            top[2].caption(row["섹터"])
            top[3].caption(row["게시시각"] or "시간 없음")
            top[4].markdown(f"**[{row['제목']}]({row['링크']})**")
            st.write(row["요약"])
            meta = " | ".join(
                part
                for part in [
                    row["종목명"],
                    row["판단 근거"],
                    row["핵심 아이디어"],
                    row["처리 상태"],
                    row["조회"],
                ]
                if part
            )
            if meta:
                st.caption(meta)
            if row["PDF 해시"]:
                button_key = f"gpt-detail-{row['PDF 해시']}"
                if st.button("GPT 상세분석", key=button_key):
                    with st.spinner("GPT가 PDF 상세분석을 작성하는 중..."):
                        st.session_state[button_key] = analyze_report_with_openai(row["PDF 해시"])
                if st.session_state.get(button_key):
                    st.markdown(st.session_state[button_key])
            with st.expander("원문 보기"):
                st.write(row["본문"])
                if row["핵심 리스크"]:
                    st.write("핵심 리스크:", row["핵심 리스크"])
                if row["확인 필요"]:
                    st.write("확인 필요:", row["확인 필요"])


def value_label(value: str) -> str:
    if value == "필독":
        color = "#b42318"
        background = "#fee4e2"
    elif value == "권장":
        color = "#027a48"
        background = "#d1fadf"
    elif value == "참고":
        color = "#175cd3"
        background = "#dbeafe"
    else:
        color = "#344054"
        background = "#eaecf0"
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"font-size:0.85rem;font-weight:700;color:{color};background:{background};'>"
        f"{value}</span>"
    )


def main() -> None:
    st.set_page_config(page_title="DOC_POOL 리포트 분류", page_icon="📄", layout="wide")
    st.title("DOC_POOL 리포트 분류")
    st.caption("텔레그램 공개 채널 게시글을 섹터별로 분류하고 읽어볼 우선순위와 요약을 보여줍니다.")

    with st.sidebar:
        st.header("수집 설정")
        limit = st.slider("가져올 게시글 수", min_value=10, max_value=500, value=100, step=10)
        classify_pdfs = st.toggle(
            "Gemini PDF 분류 실행",
            value=False,
            help="PDF를 다운로드해 해시 중복 체크 후, 처음 보는 PDF만 Gemini로 분류합니다. API 과금이 발생할 수 있습니다.",
        )
        use_ai_summary = st.toggle(
            "게시글 GPT 요약 사용",
            value=False,
            help="OPENAI_API_KEY 환경 변수가 있을 때만 동작합니다.",
        )
        refresh = st.button("새로고침", type="primary")

    if refresh:
        cached_fetch_channel_posts.clear()

    if classify_pdfs and not (os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH")):
        st.warning("PDF 분류는 Telegram API 설정이 있을 때만 동작합니다. 공개 미리보기 파싱은 PDF를 다운로드할 수 없습니다.")
    if classify_pdfs and not os.getenv("GEMINI_API_KEY"):
        st.warning("GEMINI_API_KEY가 없어서 PDF 텍스트 추출/중복 등록까지만 가능하고 Gemini 분류는 실행되지 않습니다.")

    try:
        posts = cached_fetch_channel_posts(limit, classify_pdfs)
    except Exception as exc:
        st.error(f"텔레그램 채널을 읽지 못했습니다: {exc}")
        st.stop()

    rows = build_rows(posts, use_ai_summary)
    df = pd.DataFrame(rows)

    if df.empty:
        st.warning(
            "표시할 게시글이 없습니다. 공개 미리보기에서 게시글을 받지 못한 경우 "
            "TELEGRAM_API_ID와 TELEGRAM_API_HASH를 설정해 Telethon 수집을 사용하세요."
        )
        st.stop()

    sectors = ["전체"] + sorted(df["섹터"].unique().tolist())
    values = ["전체", "필독", "권장", "참고", "낮음", "스킵 가능"]
    ratings = ["전체", "A+", "A", "B+", "B", "C", "등급 없음"]

    filters = st.columns([1.2, 1.2, 1.2, 2])
    selected_sector = filters[0].selectbox("섹터", sectors)
    selected_rating = filters[1].selectbox("레이팅", ratings)
    selected_value = filters[2].selectbox("읽을 가치", values)
    query = filters[3].text_input("검색", placeholder="종목명, 키워드, 증권사 등")

    filtered = df.copy()
    if selected_sector != "전체":
        filtered = filtered[filtered["섹터"] == selected_sector]
    if selected_rating == "등급 없음":
        filtered = filtered[filtered["레이팅"] == ""]
    elif selected_rating != "전체":
        filtered = filtered[filtered["레이팅"] == selected_rating]
    if selected_value != "전체":
        filtered = filtered[filtered["읽을 가치"] == selected_value]
    if query:
        mask = filtered.apply(lambda row: query.lower() in " ".join(map(str, row)).lower(), axis=1)
        filtered = filtered[mask]

    metric_cols = st.columns(4)
    metric_cols[0].metric("전체", len(df))
    metric_cols[1].metric("필독", int((df["읽을 가치"] == "필독").sum()))
    metric_cols[2].metric("권장", int((df["읽을 가치"] == "권장").sum()))
    metric_cols[3].metric("PDF 분류", int((df["분류 모델"] != "").sum()))

    tab_cards, tab_table, tab_stats = st.tabs(["리포트", "표", "섹터 통계"])
    with tab_cards:
        render_cards(filtered)
    with tab_table:
        st.dataframe(
            filtered.drop(columns=["본문"]),
            use_container_width=True,
            hide_index=True,
            column_config={"링크": st.column_config.LinkColumn("링크")},
        )
    with tab_stats:
        stats = (
            df.groupby(["섹터", "읽을 가치"], as_index=False)
            .size()
            .sort_values(["섹터", "size"], ascending=[True, False])
        )
        st.dataframe(stats, use_container_width=True, hide_index=True)
        st.bar_chart(df["섹터"].value_counts())


@st.cache_data(ttl=300, show_spinner="텔레그램 채널을 읽는 중...")
def cached_fetch_channel_posts(limit: int, classify_pdfs: bool) -> list[ReportPost]:
    return fetch_channel_posts(limit, classify_pdfs)


if __name__ == "__main__":
    main()
