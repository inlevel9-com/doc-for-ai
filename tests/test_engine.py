"""엔진 통합 테스트. 네트워크 없이 돌아야 한다(에어갭 요건의 1차 검증)."""
from __future__ import annotations

import json
import socket
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from docforai.engine import ConvertOptions, convert_file, detect_format, iter_documents
from docforai.engine.schema import build_chunks, markdown_to_blocks

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """변환 중 소켓이 열리면 바로 실패시킨다."""

    def guard(*a, **k):
        raise AssertionError("네트워크 접근 시도")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)


@pytest.fixture
def samples(tmp_path: Path) -> Path:
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation

    d = tmp_path / "원본 문서"
    d.mkdir()
    doc = Document()
    doc.add_heading("2026년 업무계획", 1)
    doc.add_paragraph("가. 추진 배경")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "구분", "예산"
    t.cell(1, 0).text, t.cell(1, 1).text = "홍보", "1,000"
    doc.save(d / "업무계획.docx")

    wb = Workbook()
    ws = wb.active
    ws.title = "예산"
    ws.append(["부서", "항목", "금액"])
    ws.append(["총무과", "사무용품", 120000])
    ws.append(["기획과", "출장비", 340000])
    wb.save(d / "예산.xlsx")

    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = "주민설명회"
    s.placeholders[1].text = "일시: 11월 20일\n장소: 구청 대강당"
    p.save(d / "설명회.pptx")

    (d / "메모.txt").write_text("그냥 텍스트", encoding="utf-8")
    (d / "사진.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # 지원 안 하는 형식
    return d


def test_markdown_to_blocks_and_chunks():
    md = "# 제목\n\n문단 하나\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n- 항목1\n- 항목2\n\n![그림](x_files/1.png)\n"
    blocks = markdown_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert types == ["heading", "paragraph", "table", "list", "image"]
    assert blocks[2]["header"] == ["a", "b"] and blocks[2]["rows"] == [["1", "2"]]
    chunks = build_chunks(blocks)
    assert chunks and chunks[0]["heading_path"] == ["제목"]


def test_detect_format_by_magic(tmp_path: Path):
    f = tmp_path / "이름만hwp.hwp"
    f.write_bytes(b"PK\x03\x04" + b"\0" * 20)
    assert detect_format(f) == "hwpx"


def test_iter_documents_skips_output_and_temp(samples: Path):
    (samples / "변환결과").mkdir()
    (samples / "변환결과" / "x.docx").write_bytes(b"")
    (samples / "~$잠금.docx").write_bytes(b"")
    names = sorted(p.name for p in iter_documents([samples]))
    assert names == ["메모.txt", "설명회.pptx", "업무계획.docx", "예산.xlsx"]


def test_convert_office_formats(samples: Path):
    for name in ("업무계획.docx", "예산.xlsx", "설명회.pptx"):
        r = convert_file(samples / name, ConvertOptions())
        assert r.ok, (name, r.message, r.warnings)
        md = (samples / "변환결과" / f"{Path(name).stem}.md").read_text(encoding="utf-8")
        js = json.loads((samples / "변환결과" / f"{Path(name).stem}.json").read_text(encoding="utf-8"))
        assert md.startswith("---\nsource_file:")
        assert js["schema"] == "docforai/1.0" and js["blocks"]
    js = json.loads((samples / "변환결과" / "예산.json").read_text(encoding="utf-8"))
    assert js["sheets"][0]["records"][0] == {"부서": "총무과", "항목": "사무용품", "금액": 120000}
    assert js["tables"][0]["header"] == ["부서", "항목", "금액"]
    js = json.loads((samples / "변환결과" / "설명회.json").read_text(encoding="utf-8"))
    assert js["blocks"][0] == {"type": "slide", "number": 1}
    assert "주민설명회" in js["markdown"]


def test_convert_hwpx_fixture(tmp_path: Path):
    source = tmp_path / "sample.hwpx"
    with ZipFile(source, "w") as archive:
        archive.writestr("Contents/content.hpf", """
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:manifest>
    <opf:item id="body" href="Contents/section0.xml" media-type="application/xml"/>
    <opf:item id="appendix" href="Contents/section1.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine><opf:itemref idref="body"/><opf:itemref idref="appendix"/></opf:spine>
</opf:package>
""".strip())
        archive.writestr("Contents/header.xml", """
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:refList/>
</hh:head>
""".strip())
        for index, text in enumerate(("Local conversion sample", "Appendix content")):
            archive.writestr(f"Contents/section{index}.xml", f"""
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>
</hs:sec>
""".strip())

    r = convert_file(source, ConvertOptions(out_dir=tmp_path))
    assert r.ok, (r.message, r.warnings)
    js = json.loads((tmp_path / "sample.json").read_text(encoding="utf-8"))
    assert js["source"]["format"] == "hwpx"
    assert js["source"]["engine"]
    assert "Local conversion sample" in js["markdown"]
    assert "Appendix content" in js["markdown"]


def test_workbook_preserves_dates_blanks_and_repeated_headers(tmp_path: Path):
    from openpyxl import Workbook

    path = tmp_path / "workbook.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Workbook title"])
    sheet.append(["Value", "Value", None, "Date"])
    sheet.append([1, 2.5, None, datetime(2026, 11, 5, 9)])
    workbook.create_sheet("Empty")
    workbook.save(path)

    result = convert_file(path)
    assert result.ok, result.warnings
    document = json.loads(result.outputs[1].read_text(encoding="utf-8"))
    assert document["sheets"] == [
        {
            "name": "Sheet",
            "header": ["Value", "Value_2", "열3", "Date"],
            "records": [{"Value": 1, "Value_2": 2.5, "열3": None, "Date": "2026-11-05T09:00:00"}],
        },
        {"name": "Empty", "header": [], "records": []},
    ]
    assert "Workbook title" in document["markdown"]


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("memo.txt", "한글 메모".encode("utf-16"), "한글 메모"),
        ("memo.md", b"# Markdown heading", "# Markdown heading"),
        ("list.csv", "\ufeff이름,메모\n가,한|글\n".encode(), r"| 가 | 한\|글 |"),
        ("page.html", b"<title>Local</title><h1>Heading</h1><script>private()</script>", "# Heading"),
    ],
)
def test_convert_local_text(tmp_path: Path, filename: str, content: bytes, expected: str):
    source = tmp_path / filename
    source.write_bytes(content)
    result = convert_file(source)
    assert result.ok, result.warnings
    document = json.loads(result.outputs[1].read_text(encoding="utf-8"))
    assert expected in document["markdown"]
    assert "private()" not in document["markdown"]


def test_epub_uses_spine_order(tmp_path: Path):
    source = tmp_path / "book.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="book/content.opf"/></rootfiles></container>')
        archive.writestr("book/content.opf", """
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata><title>Sample book</title></metadata>
  <manifest><item id="b" href="chapter%20b.xhtml"/><item id="a" href="a.xhtml"/></manifest>
  <spine><itemref idref="a"/><itemref idref="b"/></spine>
</package>
""".strip())
        archive.writestr("book/chapter b.xhtml", "<h1>Second chapter</h1>")
        archive.writestr("book/a.xhtml", "<h1>First chapter</h1>")
    result = convert_file(source)
    assert result.ok, result.warnings
    document = json.loads(result.outputs[1].read_text(encoding="utf-8"))
    assert document["markdown"] == "# First chapter\n\n# Second chapter"
    assert document["metadata"]["title"] == "Sample book"


def test_pdf_extracts_korean_cid_font(tmp_path: Path):
    source = tmp_path / "korean.pdf"
    korean = "한글 문서 변환"
    content = f"BT /F1 12 Tf 20 60 Td <{korean.encode('cp949').hex()}> Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 4 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /HYSMyeongJo-Medium /Encoding /KSCms-UHC-H /DescendantFonts [5 0 R] >>",
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HYSMyeongJo-Medium /CIDSystemInfo << /Registry (Adobe) /Ordering (Korea1) /Supplement 1 >> >>",
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    source.write_bytes(data)

    result = convert_file(source)
    assert result.ok, result.warnings
    document = json.loads(result.outputs[1].read_text(encoding="utf-8"))
    assert korean in document["markdown"]


def test_unsupported_and_missing(tmp_path: Path):
    bad = tmp_path / "사진.png"
    bad.write_bytes(b"x")
    assert not convert_file(bad).ok
    r = convert_file(tmp_path / "없음.docx")
    assert not r.ok and "찾을 수 없" in r.message


def test_legacy_without_pack_gives_guidance(tmp_path: Path, monkeypatch):
    import docforai.engine.legacy as legacy

    monkeypatch.setattr(legacy, "find_soffice", lambda: None)
    f = tmp_path / "옛날문서.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0" + b"\0" * 100)
    r = convert_file(f, ConvertOptions(out_dir=tmp_path))
    assert not r.ok and "확장팩" in r.message
