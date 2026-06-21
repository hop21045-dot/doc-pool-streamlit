from __future__ import annotations

import asyncio
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from report_store import (
    get_detailed_analysis,
    get_cached_classification,
    get_stored_report,
    hash_pdf_bytes,
    list_daily_clippings,
    list_saved_items,
    register_pdf,
    save_daily_clipping,
    save_classification,
    save_detailed_analysis,
    save_extracted_text,
    save_saved_item,
    update_saved_item_metadata,
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
WATCH_CHANNELS = [
    item.strip().lstrip("@")
    for item in os.getenv("WATCH_CHANNELS", CHANNEL).split(",")
    if item.strip()
]
SAVED_SOURCE_CHANNELS = [
    item.strip().lstrip("@")
    for item in os.getenv("SAVED_SOURCE_CHANNELS", "").split(",")
    if item.strip()
]
HEART_REACTIONS = {
    item.strip()
    for item in os.getenv("HEART_REACTIONS", "❤️,❤,♥️,♥").split(",")
    if item.strip()
}
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_CLASSIFIER_VERSION = "yonikuni-compact-v4"
MAX_PDF_TEXT_CHARS = int(os.getenv("MAX_PDF_TEXT_CHARS", "120000"))
DETAIL_TARGET_SECTORS = [
    item.strip()
    for item in os.getenv("DETAIL_TARGET_SECTORS", "").split(",")
    if item.strip()
]
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
PDF_DIR = Path("data/pdfs")

RATING_ORDER = {"C": 1, "B": 2, "B+": 3, "A": 4, "A+": 5}
READING_VALUE_ORDER = {
    "스킵 가능": 1,
    "참고": 2,
    "무난": 3,
    "권장": 4,
    "필독": 5,
}


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

DAILY_KEYWORDS: dict[str, list[str]] = {
    "반도체": [
        "반도체",
        "hbm",
        "dram",
        "nand",
        "파운드리",
        "tsmc",
        "삼성전자",
        "sk하이닉스",
        "엔비디아",
        "nvidia",
        "ai",
        "데이터센터",
        "datacenter",
        "전력",
        "전력인프라",
        "인프라",
        "네오클라우드",
        "hyperscaler",
        "capex",
        "컨퍼런스콜",
        "수출",
        "gpu",
        "asic",
        "cpo",
        "npo",
        "패키징",
    ],
    "조선": [
        "조선",
        "선박",
        "수주",
        "lng선",
        "lng",
        "탱커",
        "컨테이너선",
        "벌크선",
        "해양플랜트",
        "해운",
        "운임",
        "신조선가",
        "클락슨",
        "Clarksons",
        "HD현대중공업",
        "HD한국조선해양",
        "삼성중공업",
        "한화오션",
        "현대미포",
        "조선업",
    ],
}

COMPANY_NAME_REPLACEMENTS = {
    "대우조선해양": "한화오션(구 대우조선해양)",
}


@dataclass(frozen=True)
class ReportPost:
    message_id: str
    channel: str
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


def save_pdf_bytes(pdf_hash: str, pdf_bytes: bytes) -> Path:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / f"{pdf_hash}.pdf"
    if not path.exists():
        path.write_bytes(pdf_bytes)
    return path


def fetch_channel_posts(
    limit: int,
    classify_pdfs: bool,
    start_date_text: str = "",
    end_date_text: str = "",
) -> list[ReportPost]:
    if should_use_telethon():
        return asyncio.run(
            fetch_channel_posts_with_telethon(limit, classify_pdfs, start_date_text, end_date_text)
        )
    posts = fetch_channel_posts_from_preview(limit)
    return filter_posts_by_date(posts, start_date_text, end_date_text)


def should_use_telethon() -> bool:
    if not (os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH")):
        return False
    if os.getenv("TELEGRAM_STRING_SESSION"):
        return True
    session = os.getenv("TELEGRAM_SESSION", "doc_pool.session")
    candidates = [session, f"{session}.session"]
    return any(os.path.exists(candidate) for candidate in candidates)


def get_telegram_session_arg() -> object:
    from telethon.sessions import StringSession

    session = os.getenv("TELEGRAM_SESSION", "doc_pool.session")
    string_session = os.getenv("TELEGRAM_STRING_SESSION")
    return StringSession(string_session) if string_session else session


async def collect_saved_messages_with_telethon(limit: int, include_heart_reactions: bool) -> int:
    from telethon import TelegramClient

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    channels = SAVED_SOURCE_CHANNELS or WATCH_CHANNELS
    saved_count = 0

    client = TelegramClient(get_telegram_session_arg(), api_id, api_hash)
    async with client:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram 세션 인증이 필요합니다. make_telegram_session.py를 먼저 실행하세요.")
        for channel in channels:
            async for message in client.iter_messages(channel, limit=limit):
                if include_heart_reactions and not message_has_own_heart_reaction(message):
                    continue
                saved_count += await persist_message_as_saved_item(client, channel, message)
    return saved_count


def collect_saved_messages(limit: int = 200, include_heart_reactions: bool = True) -> int:
    if not should_use_telethon():
        raise RuntimeError("하트/저장 글 수집은 Telegram API 세션이 필요합니다.")
    return asyncio.run(collect_saved_messages_with_telethon(limit, include_heart_reactions))


def collect_sector_posts(
    sector: str,
    clip_date: date,
    limit_per_channel: int = 300,
) -> list[ReportPost]:
    if not should_use_telethon():
        raise RuntimeError("데일리 클리핑은 Telegram API 세션이 필요합니다.")
    return asyncio.run(collect_sector_posts_with_telethon(sector, clip_date, limit_per_channel))


async def collect_sector_posts_with_telethon(
    sector: str,
    clip_date: date,
    limit_per_channel: int,
) -> list[ReportPost]:
    from telethon import TelegramClient

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    kst = ZoneInfo("Asia/Seoul")
    start_dt = datetime.combine(clip_date, time.min, tzinfo=kst)
    end_dt = start_dt + timedelta(days=1)
    keywords = [kw.lower() for kw in DAILY_KEYWORDS[sector]]
    posts: list[ReportPost] = []

    client = TelegramClient(get_telegram_session_arg(), api_id, api_hash)
    async with client:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram 세션 인증이 필요합니다. make_telegram_session.py를 먼저 실행하세요.")
        for channel in WATCH_CHANNELS:
            try:
                async for message in client.iter_messages(
                    channel,
                    limit=None,
                    offset_date=end_dt.astimezone(timezone.utc),
                ):
                    message_dt = message.date.astimezone(kst) if message.date else None
                    if message_dt and message_dt < start_dt:
                        break
                    if message_dt and message_dt >= end_dt:
                        continue
                    text_parts = [message.message or ""]
                    document_name = get_telethon_document_name(message)
                    if document_name:
                        text_parts.append(document_name)
                    raw_text = normalize_text(" ".join(text_parts))
                    if not raw_text:
                        continue
                    lowered = raw_text.lower()
                    if not any(keyword in lowered for keyword in keywords):
                        continue
                    posts.append(
                        ReportPost(
                            message_id=str(message.id),
                            channel=channel,
                            posted_at=message.date.isoformat() if message.date else "",
                            title=extract_title(raw_text),
                            text=raw_text,
                            link=f"https://t.me/{channel}/{message.id}",
                            views=str(message.views or ""),
                            file_name=document_name,
                        )
                    )
                    if len([post for post in posts if post.channel == channel]) >= limit_per_channel:
                        break
            except Exception as exc:
                st.warning(f"텔레그램 채널을 건너뜁니다: @{channel} ({exc})")
                continue
    return dedupe_posts(posts)


def dedupe_posts(posts: list[ReportPost]) -> list[ReportPost]:
    seen: set[str] = set()
    unique: list[ReportPost] = []
    for post in posts:
        key = normalize_text(re.sub(r"https?://\S+", "", post.text))[:240]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def generate_daily_clipping(sector: str, clip_date: date, max_items: int = 15) -> str:
    posts = collect_sector_posts(sector, clip_date)
    if not posts:
        summary = f"# {clip_date.isoformat()} {sector} 데일리 클리핑\n\n수집된 관련 글이 없습니다."
        save_daily_clipping(clip_date.isoformat(), sector, f"{clip_date.isoformat()} {sector} 클리핑", summary, 0)
        return summary

    posts = posts[:max_items]
    source_block = "\n\n".join(
        [
            f"[{idx}] {post.title}\n"
            f"- 채널: {post.channel}\n"
            f"- 시간: {format_datetime(post.posted_at)}\n"
            f"- 링크: {post.link}\n"
            f"- 본문: {post.text[:1200]}"
            for idx, post in enumerate(posts, start=1)
        ]
    )
    if os.getenv("OPENAI_API_KEY"):
        summary = summarize_daily_with_openai(sector, clip_date, source_block, max_items)
    else:
        summary = build_heuristic_daily_summary(sector, clip_date, posts)
    summary = normalize_company_names(summary)
    save_daily_clipping(
        clip_date.isoformat(),
        sector,
        f"{clip_date.isoformat()} {sector} 클리핑",
        summary,
        len(posts),
    )
    return summary


def normalize_company_names(text: str) -> str:
    normalized = text
    for old_name, new_name in COMPANY_NAME_REPLACEMENTS.items():
        normalized = normalized.replace(old_name, new_name)
    return normalized


def build_heuristic_daily_summary(sector: str, clip_date: date, posts: list[ReportPost]) -> str:
    lines = [f"# {clip_date.isoformat()} {sector} 데일리 클리핑", ""]
    lines.append("OPENAI_API_KEY가 없어 원문 기반 목록형 요약만 생성했습니다.")
    lines.append("")
    for idx, post in enumerate(posts, start=1):
        lines.extend(
            [
                f"## {idx}. {post.title}",
                f"- 출처: {post.link}",
                f"- 시간: {format_datetime(post.posted_at)}",
                f"- 요약: {heuristic_summary(post.text)}",
                "- 검증 코멘트: 원문 링크 확인 필요",
                "",
            ]
        )
    return "\n".join(lines)


def summarize_daily_with_openai(sector: str, clip_date: date, source_block: str, max_items: int) -> str:
    from openai import OpenAI

    client = OpenAI()
    if sector == "반도체":
        focus = (
            "AI 데이터센터, 전력/인프라, HBM/메모리, 파운드리, 빅테크 CAPEX, "
            "네오클라우드, 컨퍼런스콜, 한국 반도체 수출 관련 신호를 우선 정리"
        )
    else:
        focus = (
            "국내 조선사 공시/수주, 조선 섹터 뉴스, 해외 조선/해운/선가/운임 이슈를 "
            "10~15개 안팎으로 묶어 정리"
        )
    company_rule = ""
    if sector == "조선":
        company_rule = (
            "회사명 검증 규칙: 현재 존재하는 사명 기준으로 써라. "
            "대우조선해양이라는 현재 사명은 사용하지 말고, 과거 사명 맥락이 필요할 때만 "
            "'한화오션(구 대우조선해양)'이라고 써라. "
            "국내 주요 조선사는 HD한국조선해양/HD현대중공업/현대미포조선/삼성중공업/한화오션 등을 기준으로 확인해라.\n"
        )
    prompt = (
        f"너는 {sector} 섹터 투자자를 위한 데일리 리서치 애널리스트다.\n"
        f"날짜: {clip_date.isoformat()}\n"
        f"중점: {focus}\n\n"
        "아래 텔레그램 원문 묶음만 근거로 Markdown 데일리 노트를 작성해라. "
        f"{company_rule}"
        "확인되지 않은 내용은 단정하지 말고 '확인 필요'로 표시해라. "
        "중복 이슈는 하나로 묶고, 각 항목에는 출처 번호와 링크를 남겨라. "
        "각 항목은 '무슨 일', '투자적 의미', '검증/추적 포인트'를 포함해라. "
        f"중요도 기준으로 최대 {max_items}개만 선별해라.\n\n"
        "출력 형식:\n"
        f"# {clip_date.isoformat()} {sector} 데일리 클리핑\n"
        "## 핵심 요약\n"
        "## 주요 클리핑\n"
        "## 오늘의 투자 체크포인트\n"
        "## 확인 필요\n\n"
        f"[원문]\n{source_block}"
    )
    result = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
        max_output_tokens=3500,
    )
    return result.output_text.strip()


def message_has_own_heart_reaction(message: object) -> bool:
    reactions = getattr(message, "reactions", None)
    for result in getattr(reactions, "results", []) or []:
        reaction = getattr(result, "reaction", None)
        emoticon = getattr(reaction, "emoticon", "")
        chosen_order = getattr(result, "chosen_order", None)
        if emoticon in HEART_REACTIONS and chosen_order is not None:
            return True
    return False


async def persist_message_as_saved_item(client: object, channel: str, message: object) -> int:
    text_parts = [message.message or ""]
    document_name = get_telethon_document_name(message)
    if document_name:
        text_parts.append(document_name)
    raw_text = normalize_text(" ".join(text_parts))
    if not raw_text and not document_name:
        return 0

    message_id = str(message.id)
    link = f"https://t.me/{channel}/{message_id}"
    pdf_hash = ""
    if document_name.lower().endswith(".pdf"):
        try:
            pdf_bytes = await client.download_media(message, file=bytes)
            if pdf_bytes:
                pdf_hash = hash_pdf_bytes(pdf_bytes)
                save_pdf_bytes(pdf_hash, pdf_bytes)
                register_pdf(
                    pdf_hash=pdf_hash,
                    message_id=message_id,
                    file_name=document_name,
                    file_size=len(pdf_bytes),
                    telegram_link=link,
                )
                stored = get_stored_report(pdf_hash)
                if not stored or not stored.extracted_text:
                    extracted_text = extract_pdf_text(pdf_bytes)
                    if extracted_text:
                        save_extracted_text(pdf_hash, extracted_text)
        except Exception:
            pdf_hash = ""

    save_saved_item(
        message_id=message_id,
        channel=channel,
        posted_at=message.date.isoformat() if message.date else "",
        title=extract_title(raw_text),
        text=raw_text,
        telegram_link=link,
        file_name=document_name,
        pdf_hash=pdf_hash,
    )
    return 1


async def fetch_channel_posts_with_telethon(
    limit: int,
    classify_pdfs: bool,
    start_date_text: str = "",
    end_date_text: str = "",
) -> list[ReportPost]:
    from telethon import TelegramClient

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    posts: list[ReportPost] = []
    start_day = parse_date_text(start_date_text)
    end_day = parse_date_text(end_date_text)
    kst = ZoneInfo("Asia/Seoul")
    offset_date = None
    if end_day:
        end_exclusive = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=kst)
        offset_date = end_exclusive.astimezone(timezone.utc)

    client = TelegramClient(get_telegram_session_arg(), api_id, api_hash)
    async with client:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram 세션 인증이 필요합니다. Streamlit을 끄고 "
                "`python make_telegram_session.py`를 먼저 실행해 doc_pool.session을 생성하세요."
            )
        effective_limit = limit
        if effective_limit <= 0:
            return []

        async for message in client.iter_messages(CHANNEL, limit=None, offset_date=offset_date):
            message_day = message.date.astimezone(kst).date() if message.date else None
            if start_day and message_day and message_day < start_day:
                break
            if end_day and message_day and message_day > end_day:
                continue
            if len(posts) >= effective_limit:
                break
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
                        save_pdf_bytes(pdf_hash, pdf_bytes)
                        duplicate_pdf = not register_pdf(
                            pdf_hash=pdf_hash,
                            message_id=message_id,
                            file_name=document_name,
                            file_size=len(pdf_bytes),
                            telegram_link=link,
                        )
                        cached = get_cached_classification(pdf_hash)
                        if cached:
                            if cached.result.get("classifier_version") == GEMINI_CLASSIFIER_VERSION:
                                classification = cached.result
                                classification_model = cached.model
                                processing_note = "중복 PDF: 기존 분류 재사용" if duplicate_pdf else "기존 분류 재사용"
                            else:
                                cached = None
                        if not cached:
                            stored = get_stored_report(pdf_hash)
                            extracted_text = stored.extracted_text if stored and stored.extracted_text else ""
                            if not extracted_text:
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
                                classification["classifier_version"] = GEMINI_CLASSIFIER_VERSION
                                classification_model = GEMINI_MODEL
                                save_classification(
                                    pdf_hash=pdf_hash,
                                    source_message_id=message_id,
                                    file_name=document_name,
                                    model=GEMINI_MODEL,
                                    result=classification,
                                )
                                processing_note = "Gemini 신규 분류" if not duplicate_pdf else "중복 PDF: 새 기준으로 재분류"
                except Exception as exc:
                    processing_note = f"PDF 처리 실패: {exc}"

            posts.append(
                ReportPost(
                    message_id=message_id,
                    channel=CHANNEL,
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
    legacy_value_map = {
        "강력 권장": "권장",
        "낮음": "스킵 가능",
        "매우 낮음": "스킵 가능",
    }
    if result.get("reading_value") in legacy_value_map:
        result["reading_value"] = legacy_value_map[result["reading_value"]]
    allowed_values = {"필독", "권장", "무난", "참고", "스킵 가능"}
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
    result.setdefault("rating_reason", "")
    result.setdefault("one_line_summary", "")
    result.setdefault("investment_idea", [])
    result.setdefault("industry_business", "N/A")
    result.setdefault("earnings_signal", "N/A")
    result.setdefault("financial_quality", "N/A")
    result.setdefault("valuation_view", "N/A")
    result.setdefault("momentum_risks", "N/A")
    result.setdefault("key_risks", [])
    result.setdefault("why_read", "")
    result.setdefault("needs_check", [])
    return result


def is_detail_candidate(sector: str, rating: str, reading_value: str) -> bool:
    if not rating or not reading_value:
        return False
    if DETAIL_TARGET_SECTORS and sector not in DETAIL_TARGET_SECTORS:
        return False
    rating_score = RATING_ORDER.get(rating, 0)
    value_score = READING_VALUE_ORDER.get(reading_value, 0)
    return (
        rating == "A+"
        or reading_value == "필독"
        or (rating_score >= RATING_ORDER["B+"] and value_score >= READING_VALUE_ORDER["권장"])
    )


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
                channel=CHANNEL,
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
        return "무난", "읽을 정보는 충분하지만 투자판단을 바꿀 정도의 신호는 제한적입니다."
    return "스킵 가능", "제목/짧은 코멘트 중심이라 우선순위는 낮게 봅니다."


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
        value = "미분류"
        reason = "Gemini PDF 분류 전입니다. 게시글/파일명만으로는 요니쿠니봇식 읽을 가치 판단을 하지 않습니다."
        summary = heuristic_summary(text_for_fallback)
        rating = ""
        stock_name = ""
        stock_code = ""
        title = post.title
        rating_reason = ""
        detail = ""
        industry_business = ""
        earnings_signal = ""
        financial_quality = ""
        valuation_view = ""
        momentum_risks = ""
        risks = ""
        needs_check = ""

        if post.classification:
            result = post.classification
            sector = str(result.get("sector") or sector)
            value = str(result.get("reading_value") or value)
            rating = str(result.get("rating") or "")
            rating_reason = str(result.get("rating_reason") or "")
            stock_name = str(result.get("stock_name") or "")
            stock_code = str(result.get("stock_code") or "")
            title = str(result.get("report_title") or post.title)
            summary = str(result.get("one_line_summary") or summary)
            reason = str(result.get("why_read") or reason)
            detail = list_to_text(result.get("investment_idea"))
            industry_business = str(result.get("industry_business") or "")
            earnings_signal = str(result.get("earnings_signal") or "")
            financial_quality = str(result.get("financial_quality") or "")
            valuation_view = str(result.get("valuation_view") or "")
            momentum_risks = str(result.get("momentum_risks") or "")
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
                "레이팅 근거": rating_reason,
                "읽을 가치": value,
                "상세분석 후보": "Y" if is_detail_candidate(sector, rating, value) else "",
                "종목명": stock_name,
                "종목코드": stock_code,
                "제목": title,
                "요약": summary,
                "판단 근거": reason,
                "핵심 아이디어": detail,
                "산업/비즈니스": industry_business,
                "실적 변화 신호": earnings_signal,
                "재무/수익성": financial_quality,
                "밸류에이션": valuation_view,
                "모멘텀/리스크": momentum_risks,
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


def parse_date_text(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def post_date_kst(value: str) -> date | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Seoul")).date()
    except ValueError:
        return None


def filter_posts_by_date(
    posts: list[ReportPost],
    start_date_text: str = "",
    end_date_text: str = "",
) -> list[ReportPost]:
    start_day = parse_date_text(start_date_text)
    end_day = parse_date_text(end_date_text)
    if not start_day and not end_day:
        return posts

    filtered = []
    for post in posts:
        posted_day = post_date_kst(post.posted_at)
        if not posted_day:
            continue
        if start_day and posted_day < start_day:
            continue
        if end_day and posted_day > end_day:
            continue
        filtered.append(post)
    return filtered


def safe_file_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value or "report")
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
    return cleaned[:80] or "report"


def build_wiki_text(row: pd.Series, analysis: str) -> str:
    meta_lines = [
        f"- 출처: {row['링크']}",
        f"- 게시시각: {row['게시시각'] or '미상'}",
        f"- 섹터: {row['섹터'] or '미분류'}",
        f"- 레이팅: {row['레이팅'] or '등급 없음'}",
        f"- 읽을 가치: {row['읽을 가치'] or '미분류'}",
    ]
    if row["레이팅 근거"]:
        meta_lines.append(f"- 레이팅 근거: {row['레이팅 근거']}")
    if row["파일명"]:
        meta_lines.append(f"- 파일명: {row['파일명']}")

    return "\n".join(
        [
            f"# {row['제목']}",
            "",
            "## 메타",
            *meta_lines,
            "",
            "## GPT 상세분석",
            analysis.strip(),
            "",
        ]
    )


def render_clipboard_button(text: str, key: str) -> None:
    payload = html.escape(json.dumps(text, ensure_ascii=False), quote=True)
    status_id = f"copy-status-{key}"
    components.html(
        f"""
        <button
          style="border:1px solid #d0d5dd;border-radius:8px;padding:8px 12px;background:white;cursor:pointer;"
          data-copy="{payload}"
          onclick="navigator.clipboard.writeText(JSON.parse(this.dataset.copy)).then(
            () => document.getElementById('{status_id}').innerText = '복사 완료',
            () => document.getElementById('{status_id}').innerText = '복사 실패: 아래 텍스트를 직접 복사하세요'
          )"
        >
          클립보드에 복사
        </button>
        <span id="{status_id}" style="margin-left:10px;color:#667085;font-size:14px;"></span>
        """,
        height=44,
    )


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
                    f"레이팅 근거: {row['레이팅 근거']}" if row["레이팅 근거"] else "",
                    row["판단 근거"],
                    row["핵심 아이디어"],
                    row["처리 상태"],
                    row["조회"],
                ]
                if part
            )
            if meta:
                st.caption(meta)
            if row["상세분석 후보"]:
                st.caption("상세분석 후보: 설정 조건을 충족했습니다.")
            if row["PDF 해시"]:
                button_key = f"gpt-detail-{row['PDF 해시']}"
                result_key = f"gpt-detail-result-{row['PDF 해시']}"
                if st.button("요니쿠니식 GPT 상세분석", key=button_key):
                    with st.spinner("GPT가 PDF 상세분석을 작성하는 중..."):
                        st.session_state[result_key] = analyze_report_with_openai(row["PDF 해시"])
                if st.session_state.get(result_key):
                    analysis = st.session_state[result_key]
                    st.markdown(analysis)
                    wiki_text = build_wiki_text(row, analysis)
                    with st.expander("요쿠위키 복사용", expanded=False):
                        copy_key = safe_file_name(row["PDF 해시"] or row["제목"])
                        render_clipboard_button(wiki_text, copy_key)
                        st.text_area(
                            "복사용 Markdown",
                            value=wiki_text,
                            height=320,
                            key=f"wiki-copy-text-{copy_key}",
                            help="복사 버튼이 동작하지 않으면 이 텍스트를 직접 선택해 복사하세요.",
                        )
                        st.download_button(
                            "Markdown 파일로 받기",
                            data=wiki_text,
                            file_name=f"{safe_file_name(row['제목'])}.md",
                            mime="text/markdown",
                            key=f"wiki-download-{copy_key}",
                        )
            with st.expander("원문 보기"):
                st.write(row["본문"])
                if row["산업/비즈니스"]:
                    st.markdown("**산업과 비즈니스 모델**")
                    st.write(row["산업/비즈니스"])
                if row["실적 변화 신호"]:
                    st.markdown("**실적 변화 신호**")
                    st.write(row["실적 변화 신호"])
                if row["재무/수익성"]:
                    st.markdown("**재무 건전성 및 수익성**")
                    st.write(row["재무/수익성"])
                if row["밸류에이션"]:
                    st.markdown("**밸류에이션**")
                    st.write(row["밸류에이션"])
                if row["모멘텀/리스크"]:
                    st.markdown("**모멘텀과 리스크**")
                    st.write(row["모멘텀/리스크"])
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


def render_saved_library() -> None:
    st.subheader("하트/저장 글 보관함")
    st.caption(
        "하트 반응 수집은 Telegram API에서 내 반응 정보가 보일 때만 동작합니다. "
        "안정적으로 쓰려면 저장용 채널 또는 Saved Messages에 글을 전달하고 SAVED_SOURCE_CHANNELS에 지정하세요."
    )
    cols = st.columns([1, 1, 2])
    limit = cols[0].number_input("확인할 글 수", min_value=10, max_value=2000, value=200, step=10)
    source_mode = cols[1].selectbox("수집 방식", ["하트 반응만", "저장용 채널 전체"])
    if cols[2].button("보관함 수집/갱신", type="primary"):
        with st.spinner("Telegram에서 저장할 글을 찾는 중..."):
            count = collect_saved_messages(
                limit=int(limit),
                include_heart_reactions=(source_mode == "하트 반응만"),
            )
        st.success(f"{count}개 글을 보관함에 저장/갱신했습니다.")

    saved_items = list_saved_items()
    if not saved_items:
        st.info("아직 저장된 글이 없습니다.")
        return

    rows = [
        {
            "메시지ID": item.message_id,
            "저장시각": item.saved_at,
            "게시시각": format_datetime(item.posted_at),
            "채널": item.channel,
            "사용자 섹터": item.user_sector,
            "기업명": item.company_names,
            "태그": item.user_tags,
            "제목": item.title,
            "파일명": item.file_name,
            "PDF": "Y" if item.pdf_hash else "",
            "링크": item.telegram_link,
            "본문": item.text,
            "PDF 해시": item.pdf_hash,
            "메모": item.user_note,
        }
        for item in saved_items
    ]
    df = pd.DataFrame(rows)
    filter_cols = st.columns([1, 1, 2])
    sector_options = ["전체"] + sorted([value for value in df["사용자 섹터"].dropna().unique().tolist() if value])
    selected_sector = filter_cols[0].selectbox("사용자 섹터 필터", sector_options)
    company_query = filter_cols[1].text_input("기업명 검색")
    text_query = filter_cols[2].text_input("본문/제목/태그 검색")
    filtered = df.copy()
    if selected_sector != "전체":
        filtered = filtered[filtered["사용자 섹터"] == selected_sector]
    if company_query:
        filtered = filtered[filtered["기업명"].str.contains(company_query, case=False, na=False)]
    if text_query:
        mask = filtered.apply(lambda row: text_query.lower() in " ".join(map(str, row)).lower(), axis=1)
        filtered = filtered[mask]

    st.dataframe(
        filtered.drop(columns=["본문", "PDF 해시", "메시지ID", "메모"]),
        use_container_width=True,
        hide_index=True,
        column_config={"링크": st.column_config.LinkColumn("링크")},
    )
    for _, row in filtered.head(50).iterrows():
        with st.expander(f"{row['게시시각']} | {row['제목']}"):
            st.markdown(f"[원문 링크 열기]({row['링크']})")
            st.write(row["본문"])
            if row["PDF 해시"]:
                st.caption(f"PDF 해시: {row['PDF 해시']}")
            with st.form(f"saved-meta-{row['채널']}-{row['메시지ID']}"):
                form_cols = st.columns([1, 1, 1])
                user_sector = form_cols[0].text_input("관련 섹터", value=row["사용자 섹터"])
                company_names = form_cols[1].text_input("관련 기업명", value=row["기업명"])
                user_tags = form_cols[2].text_input("태그", value=row["태그"])
                user_note = st.text_area("메모", value=row["메모"], height=100)
                if st.form_submit_button("카테고리 저장"):
                    update_saved_item_metadata(
                        message_id=row["메시지ID"],
                        channel=row["채널"],
                        user_sector=user_sector,
                        company_names=company_names,
                        user_tags=user_tags,
                        user_note=user_note,
                    )
                    st.success("저장했습니다. 새로고침하면 표에 반영됩니다.")


def render_daily_clipping() -> None:
    st.subheader("섹터 데일리 클리핑")
    st.caption(
        "매일 08:30 자동 실행은 GitHub Actions/Windows 작업 스케줄러 같은 별도 스케줄러에 연결하는 구조가 좋습니다. "
        "여기서는 같은 로직을 수동 생성하고 누적 조회합니다."
    )
    st.caption(f"현재 감시 채널: {', '.join('@' + channel for channel in WATCH_CHANNELS)}")
    cols = st.columns([1, 1, 1, 1])
    sector = cols[0].selectbox("섹터", ["반도체", "조선"])
    clip_day = cols[1].date_input("클리핑 날짜", value=datetime.now(ZoneInfo("Asia/Seoul")).date())
    max_items = cols[2].number_input("최대 항목 수", min_value=5, max_value=30, value=15, step=1)
    if cols[3].button("데일리 생성/갱신", type="primary"):
        with st.spinner(f"{sector} 데일리 클리핑을 생성하는 중..."):
            summary = generate_daily_clipping(sector, clip_day, int(max_items))
        st.success("데일리 클리핑을 저장했습니다.")
        st.markdown(summary)

    st.divider()
    selected_history_sector = st.selectbox("누적 조회 섹터", ["전체", "반도체", "조선"])
    history = list_daily_clippings(None if selected_history_sector == "전체" else selected_history_sector)
    if not history:
        st.info("아직 누적된 데일리 클리핑이 없습니다.")
        return
    for clip in history:
        with st.expander(f"{clip.clip_date} | {clip.sector} | 소스 {clip.source_count}개"):
            st.markdown(clip.summary_md)
            render_clipboard_button(clip.summary_md, safe_file_name(f"{clip.clip_date}-{clip.sector}"))
            st.download_button(
                "Markdown 파일로 받기",
                data=clip.summary_md,
                file_name=f"{clip.clip_date}_{clip.sector}_daily.md",
                mime="text/markdown",
                key=f"daily-download-{clip.clip_date}-{clip.sector}",
            )


def render_report_classifier() -> None:
    st.subheader("DOC_POOL 리포트 분류")
    st.caption("텔레그램 공개 채널 게시글을 섹터별로 분류하고 읽어볼 우선순위와 요약을 보여줍니다.")

    with st.sidebar:
        st.divider()
        st.header("리포트 분류 설정")
        st.caption("채널에 올라온 최신 글 기준으로 수집")
        st.caption(
            "상세분석 후보: "
            f"{', '.join(DETAIL_TARGET_SECTORS) if DETAIL_TARGET_SECTORS else '전체 섹터'} / "
            "A+ 또는 필독 또는 B+ 이상이면서 권장/필독"
        )
        limit = st.slider("가져올 최신 게시글 수", min_value=10, max_value=2000, value=100, step=10)
        use_date_range = st.toggle(
            "기간 지정",
            value=False,
            help="Telegram API 사용 시 지정 기간의 글을 직접 수집합니다. 공개 미리보기 모드에서는 가져온 최신 글 안에서만 필터링됩니다.",
        )
        start_date_text = ""
        end_date_text = ""
        if use_date_range:
            today = datetime.now(ZoneInfo("Asia/Seoul")).date()
            date_cols = st.columns(2)
            start_day = date_cols[0].date_input("시작일", value=today - timedelta(days=7), key="report-start")
            end_day = date_cols[1].date_input("종료일", value=today, key="report-end")
            start_date_text = start_day.isoformat()
            end_date_text = end_day.isoformat()
            if start_day > end_day:
                st.error("시작일은 종료일보다 늦을 수 없습니다.")
                st.stop()
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
        posts = cached_fetch_channel_posts(limit, classify_pdfs, start_date_text, end_date_text)
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
    values = ["전체", "필독", "권장", "무난", "참고", "스킵 가능", "미분류"]
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

    unique_pdf_count = filtered["PDF 해시"].replace("", pd.NA).dropna().nunique()
    duplicate_pdf_count = int((filtered["중복 PDF"] == "Y").sum())

    metric_cols = st.columns(6)
    metric_cols[0].metric("전체 글", len(df))
    metric_cols[1].metric("필독", int((df["읽을 가치"] == "필독").sum()))
    metric_cols[2].metric("권장+", int(df["읽을 가치"].isin(["필독", "권장"]).sum()))
    metric_cols[3].metric("상세 후보", int((df["상세분석 후보"] == "Y").sum()))
    metric_cols[4].metric("고유 PDF", unique_pdf_count)
    metric_cols[5].metric("중복 PDF", duplicate_pdf_count)

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


def main() -> None:
    st.set_page_config(page_title="증권사 리포트 가치 매기기", page_icon="📄", layout="wide")
    st.title("증권사 리포트 가치 매기기")
    st.caption("하트/저장 글과 섹터별 데일리 클리핑을 누적 관리합니다.")

    with st.sidebar:
        page = st.radio("화면", ["저장함", "데일리 클리핑"], index=0)

    if page == "저장함":
        render_saved_library()
    elif page == "데일리 클리핑":
        render_daily_clipping()


@st.cache_data(ttl=300, show_spinner="텔레그램 채널을 읽는 중...")
def cached_fetch_channel_posts(
    limit: int,
    classify_pdfs: bool,
    start_date_text: str = "",
    end_date_text: str = "",
) -> list[ReportPost]:
    return fetch_channel_posts(limit, classify_pdfs, start_date_text, end_date_text)


if __name__ == "__main__":
    main()
