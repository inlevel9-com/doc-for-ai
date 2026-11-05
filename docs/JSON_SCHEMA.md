# 출력 JSON 구조 (`docforai/1.0`)

어떤 원본(HWP, DOCX, PPTX, XLSX, PDF…)이든 같은 모양으로 나옵니다. AI 학습·검색 파이프라인은 이 한 가지 구조만 알면 됩니다.

```jsonc
{
  "schema": "docforai/1.0",
  "source": {
    "file_name": "2026년 업무계획.hwp",
    "format": "hwp",                       // hwp | hwpx | docx | pptx | xlsx | xls | pdf | …
    "size_bytes": 184320,
    "sha256": "3ea41d…",                   // 중복 제거·출처 추적용
    "modified": "2026-03-02T01:12:00+00:00",
    "converted_at": "2026-11-05T07:52:33+00:00",
    "engine": "<변환 엔진 이름과 버전>"
  },
  "metadata": { "title": "…", "author": "…", "created": "…", "modified": "…", "format_version": "5.0" },
  "markdown": "# 2026년 업무계획\n\n가. 추진 배경 …",   // .md 파일과 같은 본문(프런트매터 제외)
  "blocks": [                               // 본문을 순서대로 쪼갠 것
    { "type": "heading",   "level": 1, "text": "2026년 업무계획" },
    { "type": "paragraph", "text": "가. 추진 배경 …" },
    { "type": "table",     "header": ["구분", "예산"], "rows": [["홍보", "1,000"]] },
    { "type": "list",      "ordered": false, "items": ["항목1", "항목2"] },
    { "type": "image",     "alt": "image", "path": "2026년 업무계획_files/BIN0001.png" },
    { "type": "slide",     "number": 2 }    // PPTX 에서만: 슬라이드 경계
  ],
  "tables": [ /* blocks 중 table 만 모은 것 */ ],
  "chunks": [                               // RAG·파인튜닝 입력 단위 (제목 경로 기준, 기본 최대 1,500자)
    { "id": 1, "heading_path": ["2026년 업무계획", "1. 추진 배경"], "text": "…" }
  ],
  "sheets": [                               // 엑셀에서만 제공되는 시트별 레코드
    { "name": "예산", "header": ["부서", "항목", "금액"],
      "records": [ { "부서": "총무과", "항목": "사무용품", "금액": 120000 } ] }
  ],
  "warnings": [ "스캔 PDF 이면 OCR 이 필요합니다." ]
}
```

## 설계 원칙

- **원문 보존 우선**: `markdown` 은 가공하지 않은 전체 본문. `blocks`·`chunks` 는 거기서 파생되므로 언제든 다시 만들 수 있다.
- **표는 두 번**: Markdown 표(사람·LLM 용)와 `header/rows`(프로그램 용). 병합 셀은 왼쪽 위 칸에 값을 두고 나머지는 빈 문자열.
- **청크는 의미 단위**: 글자 수가 아니라 제목 구조를 따라 자르고, 너무 길 때만 문단 단위로 나눈다. 각 청크에 `heading_path` 가 있어 문맥 없이도 "어느 문서의 어느 절"인지 안다.
- **숫자는 숫자로**: 엑셀 레코드에서 `120000.0` 은 `120000` 으로, 날짜는 ISO 문자열로.
- **PDF**: 표의 내용은 텍스트로 추출합니다. 구조화된 `tables`는 Markdown 표가 생성된 문서에서 제공됩니다.

## Markdown 파일 머리(프런트매터)

```yaml
---
source_file: "2026년 업무계획.hwp"
format: hwp
title: "2026년 업무계획"
author: "기획조정실"
converted_at: 2026-11-05T07:52:33+00:00
sha256: 3ea41d…
---
```
