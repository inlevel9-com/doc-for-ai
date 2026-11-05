"""Describe image and audio files by their embedded metadata (no OCR, no speech recognition).

그림은 EXIF·PNG 텍스트 조각을, 소리 파일은 태그와 길이를 표로 적는다.
글자 인식(OCR)과 음성 인식은 모델 파일을 따로 받아야 하므로 폐쇄망 배포본에는 넣지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .schema import Converted, markdown_table

IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp"}
AUDIO_FORMATS = {"mp3", "wav", "flac", "ogg", "oga", "opus", "m4a", "m4b", "aac", "wma", "aiff", "aif"}

# 사람이 보는 이름: EXIF 태그 이름
_EXIF_LABELS = [
    ("제목", "XPTitle"), ("제목", "ImageDescription"), ("설명", "XPComment"), ("주제", "XPSubject"),
    ("키워드", "XPKeywords"), ("작성자", "Artist"), ("작성자", "XPAuthor"), ("저작권", "Copyright"),
    ("촬영 일시", "DateTimeOriginal"), ("디지털화 일시", "DateTimeDigitized"), ("수정 일시", "DateTime"),
    ("카메라 제조사", "Make"), ("카메라 모델", "Model"), ("렌즈", "LensModel"), ("소프트웨어", "Software"),
    ("방향", "Orientation"), ("노출 시간", "ExposureTime"), ("조리개", "FNumber"), ("ISO", "ISOSpeedRatings"),
    ("초점 거리", "FocalLength"), ("플래시", "Flash"), ("해상도(가로)", "XResolution"), ("해상도(세로)", "YResolution"),
]
_PNG_TEXT = ["Title", "Author", "Description", "Copyright", "Creation Time", "Software", "Source", "Comment"]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-16-le") if len(value) % 2 == 0 and b"\x00" in value else value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, (tuple, list)):
        value = ", ".join(str(v) for v in value)
    s = str(value)
    # EXIF ASCII 태그에 UTF-8 로 적힌 한글은 latin-1 로 잘못 읽히므로 되돌려 본다
    if s and all(ord(ch) < 256 for ch in s) and any(ord(ch) >= 128 for ch in s):
        try:
            s = s.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    s = _CONTROL.sub("", s).strip().strip("\x00")
    return s[:500] if s else None


def _exif_datetime(value: str | None) -> str | None:
    """EXIF 'YYYY:MM:DD HH:MM:SS' → ISO 8601."""
    if not value:
        return None
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}:\d{2}:\d{2})", value)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}" if m else value


def _gps(gps: dict[int, Any]) -> str | None:
    from PIL import ExifTags

    def to_degrees(values: Any, ref: Any) -> float | None:
        try:
            d, m, s = (float(v) for v in values)
        except (TypeError, ValueError):
            return None
        deg = d + m / 60 + s / 3600
        return -deg if str(ref).upper() in {"S", "W"} else deg

    lat = to_degrees(gps.get(ExifTags.GPS.GPSLatitude), gps.get(ExifTags.GPS.GPSLatitudeRef))
    lon = to_degrees(gps.get(ExifTags.GPS.GPSLongitude), gps.get(ExifTags.GPS.GPSLongitudeRef))
    if lat is None or lon is None:
        return None
    return f"{lat:.6f}, {lon:.6f}"


def convert_image(path: Path, image_prefix: str) -> Converted:
    import PIL
    from PIL import ExifTags, Image

    rows: list[list[Any]] = [["항목", "값"]]
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    with Image.open(path) as im:
        rows.append(["파일 형식", im.format or path.suffix.lstrip(".").upper()])
        rows.append(["크기(픽셀)", f"{im.width} × {im.height}"])
        rows.append(["색상 모드", im.mode])
        frames = getattr(im, "n_frames", 1)
        if frames > 1:
            rows.append(["프레임 수", frames])

        tags: dict[str, Any] = {}
        try:
            exif = im.getexif()
            for tag_id, value in exif.items():
                tags.setdefault(ExifTags.TAGS.get(tag_id, str(tag_id)), value)
            for tag_id, value in exif.get_ifd(ExifTags.IFD.Exif).items():
                tags.setdefault(ExifTags.TAGS.get(tag_id, str(tag_id)), value)
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except Exception as e:  # noqa: BLE001 - 손상된 EXIF 는 건너뛰고 나머지는 계속
            gps = {}
            warnings.append(f"EXIF 를 읽지 못했습니다: {str(e)[:120]}")

        seen: set[str] = set()
        for label, tag in _EXIF_LABELS:
            value = _text(tags.get(tag))
            if value and label not in seen:
                if "일시" in label:
                    value = _exif_datetime(value) or value
                rows.append([label, value])
                seen.add(label)
        if gps:
            location = _gps(gps)
            if location:
                rows.append(["위치(위도, 경도)", location])
        for key in _PNG_TEXT:  # PNG tEXt 조각(Pillow 가 im.info 에 넣어 준다)
            value = _text(im.info.get(key))
            if value and key not in seen:
                rows.append([key, value])
                seen.add(key)

    found = {row[0]: row[1] for row in rows[1:]}
    for meta_key, labels in (("title", ("제목", "Title")), ("author", ("작성자", "Author")),
                             ("created", ("촬영 일시", "Creation Time")), ("modified", ("수정 일시",))):
        for label in labels:
            if label in found:
                metadata[meta_key] = found[label]
                break

    name = path.name
    markdown = "\n\n".join([markdown_table(rows), f"![{name}]({image_prefix}{name})"])
    warnings.append("그림 속 글자는 읽지 않습니다(OCR 미지원). 메타데이터만 기록했습니다.")
    return Converted(markdown, f"Pillow {PIL.__version__}", metadata=metadata,
                     images=[(name, path.read_bytes())], warnings=warnings)


def _duration(seconds: float | None) -> str | None:
    if not seconds:
        return None
    total = int(round(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def convert_audio(path: Path) -> Converted:
    import tinytag
    from tinytag import TinyTag

    tag = TinyTag.get(str(path))
    rows: list[list[Any]] = [["항목", "값"]]
    fields = [
        ("제목", "title"), ("아티스트", "artist"), ("앨범", "album"), ("앨범 아티스트", "albumartist"),
        ("작곡", "composer"), ("장르", "genre"), ("연도", "year"), ("트랙", "track"), ("설명", "comment"),
    ]
    metadata: dict[str, Any] = {}
    for label, attr in fields:
        value = _text(getattr(tag, attr, None))
        if value:
            rows.append([label, value])
    if _text(tag.title):
        metadata["title"] = _text(tag.title)
    if _text(tag.artist):
        metadata["author"] = _text(tag.artist)

    duration = _duration(tag.duration)
    if duration:
        rows.append(["길이", duration])
    if tag.samplerate:
        rows.append(["샘플레이트", f"{tag.samplerate} Hz"])
    if tag.channels:
        rows.append(["채널", tag.channels])
    if tag.bitrate:
        rows.append(["비트레이트", f"{tag.bitrate:.0f} kbps"])
    rows.append(["파일 크기", f"{path.stat().st_size:,} 바이트"])

    engine = f"tinytag {getattr(tinytag, '__version__', '')}".strip()
    return Converted(markdown_table(rows), engine, metadata=metadata,
                     warnings=["음성은 글자로 옮기지 않습니다(음성 인식 미지원). 태그와 길이만 기록했습니다."])
