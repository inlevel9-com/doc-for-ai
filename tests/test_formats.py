"""새 입력 형식(JSON·XML·ZIP·그림·소리)과 JSON → 엑셀 역변환 테스트. 네트워크 없이 돌아야 한다."""
from __future__ import annotations

import io
import json
import socket
import wave
import zipfile
from pathlib import Path

import pytest

from docforai.engine import ConvertOptions, convert_file, excel_from_json, excel_from_json_many
from docforai.engine.schema import build_chunks, markdown_to_blocks


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise AssertionError("네트워크 접근 시도")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)


def _document(result) -> dict:  # noqa: ANN001
    assert result.ok, (result.message, result.warnings)
    return json.loads(next(o for o in result.outputs if o.suffix == ".json").read_text(encoding="utf-8"))


def _sheet_rows(path: Path, name: str) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(path)
    return list(wb[name].iter_rows(values_only=True))


# ---------- 코드 블록 ----------

def test_markdown_code_fence_becomes_code_block():
    md = "# 제목\n\n```json\n{\n  \"a\": 1\n}\n```\n\n문단\n"
    blocks = markdown_to_blocks(md)
    assert [b["type"] for b in blocks] == ["heading", "code", "paragraph"]
    assert blocks[1] == {"type": "code", "language": "json", "text": '{\n  "a": 1\n}'}
    assert build_chunks(blocks)[0]["text"].startswith("{")


# ---------- JSON / XML ----------

def test_json_records_become_table_and_sheet(tmp_path: Path):
    source = tmp_path / "명단.json"
    source.write_text(json.dumps({"rows": [{"이름": "가", "점수": 1}, {"이름": "나", "점수": 2, "비고": "x"}]}, ensure_ascii=False), encoding="utf-8")
    doc = _document(convert_file(source))
    assert doc["tables"][0]["header"] == ["이름", "점수", "비고"]
    assert doc["sheets"] == [{"name": "rows", "header": ["이름", "점수", "비고"],
                              "records": [{"이름": "가", "점수": 1, "비고": None}, {"이름": "나", "점수": 2, "비고": "x"}]}]


def test_json_object_is_pretty_printed_code(tmp_path: Path):
    source = tmp_path / "설정.json"
    source.write_bytes('{"a":{"b":[1,2]},"이름":"값"}'.encode("utf-8"))
    doc = _document(convert_file(source))
    assert doc["blocks"] == [{"type": "code", "language": "json", "text": '{\n  "a": {\n    "b": [\n      1,\n      2\n    ]\n  },\n  "이름": "값"\n}'}]


def test_broken_json_keeps_text_with_warning(tmp_path: Path):
    source = tmp_path / "깨짐.json"
    source.write_text("{오류", encoding="utf-8")
    result = convert_file(source)
    doc = _document(result)
    assert "{오류" in doc["markdown"] and any("문법" in w for w in result.warnings)


def test_xml_feed_and_plain_xml(tmp_path: Path):
    feed = tmp_path / "소식.xml"
    feed.write_text('<rss><channel><title>구청 소식</title><item><title>첫 글</title><pubDate>Mon, 03 Nov 2026</pubDate>'
                    '<description>&lt;p&gt;본문 &lt;b&gt;강조&lt;/b&gt;&lt;/p&gt;</description></item></channel></rss>', encoding="utf-8")
    doc = _document(convert_file(feed))
    assert doc["markdown"] == "# 구청 소식\n\n## 첫 글\n\n날짜: Mon, 03 Nov 2026\n\n본문 **강조**"

    plain = tmp_path / "자료.xml"
    plain.write_text('<root><item id="1">값</item></root>', encoding="utf-8")
    doc = _document(convert_file(plain))
    assert doc["blocks"] == [{"type": "code", "language": "xml", "text": '<root>\n  <item id="1">값</item>\n</root>'}]


def test_xml_entities_are_not_expanded(tmp_path: Path):
    bomb = tmp_path / "폭탄.xml"
    bomb.write_text('<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><x>&b;</x>', encoding="utf-8")
    result = convert_file(bomb)
    assert result.ok and "aaaa" * 3 not in _document(result)["markdown"]
    assert any("원문 그대로" in w for w in result.warnings)


# ---------- 그림 / 소리 ----------

def _photo(path: Path) -> None:
    from PIL import ExifTags, Image

    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Canon"
    exif[ExifTags.Base.Artist] = "Hong Gildong"
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = "2026:01:02 03:04:05"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitude], gps[ExifTags.GPS.GPSLatitudeRef] = (37.0, 33.0, 36.0), "N"
    gps[ExifTags.GPS.GPSLongitude], gps[ExifTags.GPS.GPSLongitudeRef] = (126.0, 58.0, 0.0), "E"
    Image.new("RGB", (4, 3), "red").save(path, exif=exif.tobytes())


def test_image_metadata_only(tmp_path: Path):
    source = tmp_path / "사진.jpg"
    _photo(source)
    result = convert_file(source)
    doc = _document(result)
    table = dict(doc["tables"][0]["rows"])
    assert table["크기(픽셀)"] == "4 × 3" and table["카메라 제조사"] == "Canon"
    assert table["촬영 일시"] == "2026-01-02T03:04:05" and table["위치(위도, 경도)"] == "37.560000, 126.966667"
    assert doc["metadata"] == {"author": "Hong Gildong", "created": "2026-01-02T03:04:05"}
    assert doc["blocks"][-1] == {"type": "image", "alt": "사진.jpg", "path": "사진_files/사진.jpg"}
    assert (tmp_path / "변환결과" / "사진_files" / "사진.jpg").read_bytes() == source.read_bytes()
    assert any("OCR" in w for w in result.warnings)


def test_png_text_chunks(tmp_path: Path):
    from PIL import Image, PngImagePlugin

    source = tmp_path / "그림.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("Title", "조직도")
    Image.new("L", (2, 2)).save(source, pnginfo=info)
    doc = _document(convert_file(source, ConvertOptions(save_images=False)))
    assert doc["metadata"]["title"] == "조직도" and ["Title", "조직도"] in doc["tables"][0]["rows"]


def test_audio_metadata_only(tmp_path: Path):
    source = tmp_path / "녹음.wav"
    with wave.open(str(source), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0\0\0" * 16000)
    result = convert_file(source)
    doc = _document(result)
    table = dict(doc["tables"][0]["rows"])
    assert table["길이"] == "0:01" and table["샘플레이트"] == "16000 Hz" and table["채널"] == "2"
    assert any("음성 인식" in w for w in result.warnings)


# ---------- ZIP ----------

def test_zip_converts_each_entry(tmp_path: Path):
    from openpyxl import Workbook

    photo = tmp_path / "photo.jpg"
    _photo(photo)
    wb = Workbook()
    wb.active.append(["부서", "금액"])
    wb.active.append(["총무과", 10])
    xlsx = io.BytesIO()
    wb.save(xlsx)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("속/안내.md", "# 속 제목\n\n본문")

    source = tmp_path / "자료.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("문서/메모.txt", "안녕")
        z.writestr("문서/예산.xlsx", xlsx.getvalue())
        z.write(photo, "사진/photo.jpg")
        z.writestr("기타/설치.exe", b"MZ")
        z.writestr("__MACOSX/._메모.txt", b"junk")
        z.writestr("속.zip", inner.getvalue())
        z.writestr("구형.doc", b"\xd0\xcf\x11\xe0")  # 확장팩 없으면 건너뛰고 계속

    result = convert_file(source)
    doc = _document(result)
    assert doc["metadata"]["entries"] == ["문서/메모.txt", "문서/예산.xlsx", "사진/photo.jpg", "속.zip"]
    headings = [(b["level"], b["text"]) for b in doc["blocks"] if b["type"] == "heading"]
    assert (1, "문서/메모.txt") in headings and (3, "Sheet") in headings and (3, "속 제목") in headings
    assert doc["sheets"][0]["name"] == "예산/Sheet" and doc["sheets"][0]["records"] == [{"부서": "총무과", "금액": 10}]
    assert [c["heading_path"] for c in doc["chunks"]][-1] == ["속.zip", "속/안내.md", "속 제목"]
    assert (tmp_path / "변환결과" / "자료_files" / "photo.jpg").exists()
    assert any("설치.exe" in w and "건너뜀" in w for w in result.warnings)
    assert any("구형.doc" in w for w in result.warnings)
    assert "문서 4개" in result.message


def test_bad_zip_fails_cleanly(tmp_path: Path):
    source = tmp_path / "손상.zip"
    source.write_bytes(b"PK\x03\x04 broken")
    result = convert_file(source)
    assert not result.ok and "압축" in result.message


# ---------- JSON → 엑셀 ----------

def test_excel_from_document_blocks(tmp_path: Path):
    source = tmp_path / "보고서.md"
    source.write_text("# 계획\n\n문단 =SUM(1)\n\n| 구분 | 예산 |\n| --- | --- |\n| 홍보 | 1,000 |\n\n- 항목1\n- 항목2\n\n```python\nprint(1)\n```\n", encoding="utf-8")
    js = next(o for o in convert_file(source).outputs if o.suffix == ".json")

    result = excel_from_json(js, ConvertOptions(out_dir=tmp_path / "엑셀"))
    assert result.ok, result.message
    target = tmp_path / "엑셀" / "보고서.xlsx"
    assert result.outputs == [target]
    import openpyxl

    assert openpyxl.load_workbook(target).sheetnames == ["정보", "본문", "표1"]
    body = _sheet_rows(target, "본문")
    assert body[0] == ("순번", "종류", "수준·번호", "내용")
    assert body[1:] == [
        (1, "제목", 1, "계획"),
        (2, "문단", None, "문단 =SUM(1)"),
        (3, "표", "표1", "1행 × 2열 → 시트 '표1'"),
        (4, "글머리목록", 1, "항목1"),
        (5, "글머리목록", 2, "항목2"),
        (6, "코드", "python", "print(1)"),
    ]
    assert _sheet_rows(target, "표1") == [("구분", "예산"), ("홍보", "1,000")]
    info = dict(_sheet_rows(target, "정보")[1:])
    assert info["schema"] == "docforai/1.0" and info["source.file_name"] == "보고서.md"


def test_excel_restores_sheets_and_keeps_formula_text(tmp_path: Path):
    from openpyxl import Workbook

    source = tmp_path / "예산.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "예산"
    ws.append(["부서", "금액", "비고"])
    ws.append(["총무과", 120000, "비고"])
    wb.create_sheet("예산")  # 같은 이름은 엑셀이 알아서 '예산1'로 바꾼다
    wb.save(source)
    js = next(o for o in convert_file(source).outputs if o.suffix == ".json")
    doc = json.loads(js.read_text(encoding="utf-8"))
    doc["sheets"][0]["records"][0]["비고"] = "=합계"  # '=' 로 시작하는 글이 수식으로 바뀌면 안 된다
    js.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    result = excel_from_json(js)  # 기본 저장 위치: JSON 옆
    assert result.ok and result.outputs[0] == tmp_path / "변환결과" / "예산.xlsx"
    import openpyxl

    restored = openpyxl.load_workbook(result.outputs[0])
    assert restored.sheetnames == ["정보", "예산", "예산1"]
    assert _sheet_rows(result.outputs[0], "예산") == [("부서", "금액", "비고"), ("총무과", 120000, "=합계")]
    assert restored["예산"]["C2"].data_type == "s"


def test_excel_rejects_foreign_json(tmp_path: Path):
    other = tmp_path / "기타.json"
    other.write_text('{"hello": 1}', encoding="utf-8")
    result = excel_from_json(other)
    assert not result.ok and "docforai" in result.message
    results = excel_from_json_many([tmp_path])
    assert [r.ok for r in results] == [False]


def test_cli_to_excel(tmp_path: Path, capsys):
    from docforai.cli import main

    source = tmp_path / "메모.txt"
    source.write_text("한 줄", encoding="utf-8")
    assert main([str(source), "-o", str(tmp_path / "out")]) == 0
    assert main(["to-excel", str(tmp_path / "out" / "메모.json"), "-o", str(tmp_path / "xl")]) == 0
    assert (tmp_path / "xl" / "메모.xlsx").exists()
    assert "메모.xlsx" in capsys.readouterr().out
    assert main(["to-excel", str(tmp_path / "없음.json")]) == 1
