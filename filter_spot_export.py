from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def text_to_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return " ".join(parts)
    return str(value)


def load_export(source: Path) -> tuple[dict[str, Any], Path | None, zipfile.ZipFile | None]:
    if source.is_dir():
        result_path = source / "result.json"
        with result_path.open("r", encoding="utf-8") as file:
            return json.load(file), source, None

    archive = zipfile.ZipFile(source)
    with archive.open("result.json") as file:
        return json.load(file), None, archive


def read_photo(source_dir: Path | None, archive: zipfile.ZipFile | None, photo_ref: str) -> bytes | None:
    normalized = photo_ref.replace("\\", "/")
    candidates = [normalized, normalized.lstrip("/"), f"photos/{Path(normalized).name}"]
    if source_dir is not None:
        for candidate in candidates:
            path = source_dir / candidate
            if path.exists():
                return path.read_bytes()
        return None

    if archive is None:
        return None
    names = {name.replace("\\", "/"): name for name in archive.namelist()}
    for candidate in candidates:
        key = candidate.replace("\\", "/")
        if key in names:
            return archive.read(names[key])
    return None


def is_kiwoom_spot_price_post(text: str) -> bool:
    normalized = " ".join(text.split()).strip()
    return (
        normalized.startswith("키움 반도체 박유악입니다.")
        and "출처: DRAMeXchange" in normalized
        and normalized.endswith("[박유악 키움 반도체]")
    )


def build_filtered_export(source: Path, output: Path) -> tuple[int, int]:
    data, source_dir, archive = load_export(source)
    try:
        messages = data.get("messages", [])
        filtered_messages: list[dict[str, Any]] = []
        photo_refs: set[str] = set()

        for message in messages:
            text = text_to_string(message.get("text"))
            if not is_kiwoom_spot_price_post(text):
                continue
            filtered_messages.append(message)
            photo_ref = message.get("photo")
            if photo_ref:
                photo_refs.add(str(photo_ref).replace("\\", "/"))

        data["messages"] = filtered_messages

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as out:
            out.writestr("result.json", json.dumps(data, ensure_ascii=False, indent=2))
            for photo_ref in sorted(photo_refs):
                content = read_photo(source_dir, archive, photo_ref)
                if content is None:
                    continue
                out.writestr(photo_ref, content)

        return len(filtered_messages), len(photo_refs)
    finally:
        if archive is not None:
            archive.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small Telegram export ZIP that only keeps DRAMeXchange spot-price posts."
    )
    parser.add_argument("source", help="Telegram export folder or ZIP containing result.json")
    parser.add_argument(
        "-o",
        "--output",
        default="data/dramexchange_spot_export.zip",
        help="Output ZIP path. Default: data/dramexchange_spot_export.zip",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        output.unlink()

    kept_messages, photo_count = build_filtered_export(source, output)
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"created: {output}")
    print(f"kept messages: {kept_messages}")
    print(f"linked photos: {photo_count}")
    print(f"zip size: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
