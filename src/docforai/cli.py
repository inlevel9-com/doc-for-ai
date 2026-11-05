"""숨은 명령줄 인터페이스. 일반 사용자는 GUI(app.py)를 쓰고, 일괄 처리·자동화용으로만 둔다.

    docforai 보고서.hwp 자료실/ -o 결과폴더 --no-json
    docforai to-excel 변환결과/보고서.json -o 결과폴더      # JSON → 엑셀 역변환
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import DESIGNED_BY, __version__
from .engine import ConvertOptions, ConvertResult, convert_many, excel_from_json_many

SUBCOMMANDS = {"to-excel"}


def _report_factory() -> tuple[callable, list[int]]:
    fails = [0]

    def report(i: int, n: int, r: ConvertResult) -> None:
        mark = "O" if r.ok else "X"
        print(f"[{i}/{n}] {mark} {r.source.name}: {r.message}")
        for w in r.warnings:
            if r.ok:
                print(f"       주의: {w}")
        if not r.ok:
            fails[0] += 1

    return report, fails


def _to_excel(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="docforai to-excel", description="이 프로그램이 만든 JSON 을 엑셀(.xlsx)로 되돌림")
    ap.add_argument("paths", nargs="+", type=Path, help="변환결과의 .json 파일 또는 폴더")
    ap.add_argument("-o", "--out", type=Path, help="결과 폴더 (기본: JSON 파일 옆)")
    args = ap.parse_args(argv)
    report, fails = _report_factory()
    excel_from_json_many(args.paths, ConvertOptions(out_dir=args.out), report)
    return 1 if fails[0] else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "to-excel":
        return _to_excel(argv[1:])

    ap = argparse.ArgumentParser(
        prog="docforai", description="문서를 AI 학습용 Markdown/JSON 으로 변환",
        epilog="역변환: docforai to-excel 파일.json [-o 폴더]",
    )
    ap.add_argument("paths", nargs="*", type=Path, help="파일 또는 폴더 (폴더는 하위까지)")
    ap.add_argument("-o", "--out", type=Path, help="결과 폴더 (기본: 원본 옆 '변환결과')")
    ap.add_argument("--no-md", action="store_true", help="Markdown 을 만들지 않음")
    ap.add_argument("--no-json", action="store_true", help="JSON 을 만들지 않음")
    ap.add_argument("--no-images", action="store_true", help="그림을 저장하지 않음")
    ap.add_argument("--hwpx", action="store_true", help=".hwp 를 .hwpx 로도 저장 (Windows + 한컴오피스 한글 필요)")
    ap.add_argument("--gui", action="store_true", help="그래픽 창 열기")
    ap.add_argument("-V", "--version", action="version", version=f"docforai {__version__} | {DESIGNED_BY}")
    args = ap.parse_args(argv)

    if args.gui or not args.paths:
        from .app import main as gui_main

        gui_main()
        return 0

    opts = ConvertOptions(write_markdown=not args.no_md, write_json=not args.no_json,
                          save_images=not args.no_images, out_dir=args.out, save_hwpx=args.hwpx)
    report, fails = _report_factory()
    convert_many(args.paths, opts, report)
    return 1 if fails[0] else 0


if __name__ == "__main__":
    sys.exit(main())
