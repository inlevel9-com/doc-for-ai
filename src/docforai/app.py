"""Desktop interface for selecting and converting local documents."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, DESIGNED_BY, __version__
from .engine.hancom import unavailable_reason as hancom_unavailable_reason
from .paths import asset_path
from .engine import (
    AUDIO_FORMATS,
    FORMAT_LABEL,
    IMAGE_FORMATS,
    OUTPUT_DIR_NAME,
    SUPPORTED,
    ConvertOptions,
    ConvertResult,
    convert_many,
    excel_from_json_many,
    iter_documents,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

FONT_FAMILY = "맑은 고딕" if sys.platform == "win32" else ("Apple SD Gothic Neo" if sys.platform == "darwin" else "Noto Sans CJK KR")
FILETYPES = [
    ("변환 가능한 문서", " ".join(f"*.{e}" for e in sorted(SUPPORTED))),
    ("한글 문서", "*.hwp *.hwpx *.hwt *.hml"),
    ("워드/파워포인트/엑셀", "*.docx *.doc *.pptx *.ppt *.xlsx *.xls"),
    ("PDF", "*.pdf"),
    ("텍스트·웹·전자책", "*.txt *.md *.csv *.html *.htm *.json *.xml *.epub"),
    ("압축 파일", "*.zip"),
    ("그림(메타데이터만)", " ".join(f"*.{e}" for e in sorted(IMAGE_FORMATS))),
    ("소리(메타데이터만)", " ".join(f"*.{e}" for e in sorted(AUDIO_FORMATS))),
    ("모든 파일", "*.*"),
]
JSON_FILETYPES = [("변환결과 JSON", "*.json"), ("모든 파일", "*.*")]


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.has_dnd = False
        if TkinterDnD is not None:
            try:
                TkinterDnD.require(self.root)
                self.has_dnd = True
            except RuntimeError:
                pass
        self.root.title(f"{APP_NAME} {__version__} | {DESIGNED_BY}")
        self._set_icon()
        self.root.geometry("760x620")
        self.root.minsize(640, 520)
        self.files: list[Path] = []
        self.results: list[ConvertResult] = []
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_out_dirs: list[Path] = []

        self.root.option_add("*Font", (FONT_FAMILY, 11))
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else style.theme_use())
        except tk.TclError:
            pass
        style.configure("Big.TButton", font=(FONT_FAMILY, 14, "bold"), padding=10)
        style.configure("Drop.TLabel", font=(FONT_FAMILY, 13), foreground="#334155", background="#eef2ff")

        self._build()
        self.root.after(150, self._poll)

    def _set_icon(self) -> None:
        """창과 작업 표시줄에 서비스 아이콘을 표시한다. 아이콘이 없어도 실행은 계속된다."""
        try:
            if sys.platform == "win32":
                self.root.iconbitmap(default=str(asset_path("icon.ico")))
            self._icon_image = tk.PhotoImage(file=str(asset_path("icon.png")))
            self.root.iconphoto(True, self._icon_image)
        except (tk.TclError, OSError):
            pass

    # ---------- 화면 구성 ----------
    def _build(self) -> None:
        pad = {"padx": 14, "pady": 6}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="① 문서를 아래 상자에 끌어다 놓거나 버튼으로 고르세요", font=(FONT_FAMILY, 12, "bold")).pack(anchor="w")

        drop = tk.Frame(self.root, bg="#eef2ff", bd=2, relief="groove", height=120)
        drop.pack(fill="x", padx=14, pady=4)
        drop.pack_propagate(False)
        hint = "여기에 파일이나 폴더를 끌어다 놓으세요" if self.has_dnd else "아래 버튼으로 파일이나 폴더를 고르세요"
        self.drop_label = ttk.Label(drop, text=f"{hint}\n(한글 HWP·HWPX, 워드, 파워포인트, 엑셀, PDF, 텍스트·웹·전자책, ZIP, 그림·소리 정보)", style="Drop.TLabel", anchor="center", justify="center")
        self.drop_label.pack(expand=True, fill="both")
        if self.has_dnd:
            for w in (drop, self.drop_label):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="파일 선택…", command=self._pick_files).pack(side="left")
        ttk.Button(btns, text="폴더 선택…", command=self._pick_folder).pack(side="left", padx=6)
        ttk.Button(btns, text="목록 비우기", command=self._clear).pack(side="left", padx=6)
        self.count_label = ttk.Label(btns, text="선택된 문서: 0개")
        self.count_label.pack(side="right")

        opt = ttk.LabelFrame(self.root, text="② 어떻게 바꿀까요?")
        opt.pack(fill="x", **pad)
        self.v_md = tk.BooleanVar(value=True)
        self.v_json = tk.BooleanVar(value=True)
        self.v_img = tk.BooleanVar(value=True)
        row = ttk.Frame(opt)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(row, text="Markdown (.md) — 사람이 읽기 좋고 AI 에 바로 넣기 좋음", variable=self.v_md).pack(anchor="w")
        ttk.Checkbutton(row, text="JSON (.json) — 표·문단·메타데이터가 구조화된 학습용", variable=self.v_json).pack(anchor="w")
        ttk.Checkbutton(row, text="문서 안의 그림도 함께 저장", variable=self.v_img).pack(anchor="w")
        self.v_hwpx = tk.BooleanVar(value=False)
        hwpx_reason = hancom_unavailable_reason()
        hwpx_text = "한글 .hwp 를 .hwpx 로도 저장 (한컴오피스 한글이 설치된 Windows PC)"
        if hwpx_reason:
            hwpx_text = f"한글 .hwp 를 .hwpx 로도 저장 — 사용 불가: {hwpx_reason}"
        ttk.Checkbutton(row, text=hwpx_text, variable=self.v_hwpx, state="normal" if not hwpx_reason else "disabled").pack(anchor="w")

        out = ttk.Frame(opt)
        out.pack(fill="x", padx=8, pady=(2, 8))
        self.v_outmode = tk.StringVar(value="beside")
        ttk.Radiobutton(out, text=f"원본 파일 옆 '{OUTPUT_DIR_NAME}' 폴더에 저장 (권장)", variable=self.v_outmode, value="beside").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(out, text="다른 폴더에 저장:", variable=self.v_outmode, value="custom").grid(row=1, column=0, sticky="w")
        self.v_outdir = tk.StringVar()
        ttk.Entry(out, textvariable=self.v_outdir, width=46).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Button(out, text="찾아보기…", command=self._pick_outdir).grid(row=1, column=2)
        out.columnconfigure(1, weight=1)

        act = ttk.Frame(self.root)
        act.pack(fill="x", **pad)
        self.btn_go = ttk.Button(act, text="③ 변환 시작", style="Big.TButton", command=self._start)
        self.btn_go.pack(side="left")
        self.btn_open = ttk.Button(act, text="결과 폴더 열기", command=self._open_out, state="disabled")
        self.btn_open.pack(side="left", padx=8)
        self.btn_excel = ttk.Button(act, text="JSON → 엑셀로 되돌리기…", command=self._json_to_excel)
        self.btn_excel.pack(side="left")
        self.progress = ttk.Progressbar(act, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)

        cols = ("file", "kind", "status")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=10)
        self.tree.heading("file", text="문서")
        self.tree.heading("kind", text="종류")
        self.tree.heading("status", text="상태")
        self.tree.column("file", width=300)
        self.tree.column("kind", width=110, anchor="center")
        self.tree.column("status", width=300)
        self.tree.pack(fill="both", expand=True, padx=14, pady=4)
        self.tree.tag_configure("ok", foreground="#15803d")
        self.tree.tag_configure("fail", foreground="#b91c1c")
        self.tree.tag_configure("warn", foreground="#b45309")
        self.tree.bind("<Double-1>", self._show_detail)

        self.status = ttk.Label(self.root, text="준비됨 · 인터넷 연결 없이 이 PC 안에서만 처리합니다", anchor="w", foreground="#475569")
        self.status.pack(fill="x", padx=14, pady=(0, 8))

    # ---------- 파일 담기 ----------
    def _on_drop(self, event) -> None:  # noqa: ANN001
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        self._add(paths)

    def _pick_files(self) -> None:
        sel = filedialog.askopenfilenames(title="변환할 문서 선택", filetypes=FILETYPES)
        self._add([Path(p) for p in sel])

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(title="문서가 들어 있는 폴더 선택 (하위 폴더 포함)")
        if d:
            self._add([Path(d)])

    def _pick_outdir(self) -> None:
        d = filedialog.askdirectory(title="결과를 저장할 폴더")
        if d:
            self.v_outdir.set(d)
            self.v_outmode.set("custom")

    def _add(self, paths: list[Path]) -> None:
        docs = iter_documents(paths)
        skipped = [p for p in paths if p.is_file() and p.suffix.lower().lstrip(".") not in SUPPORTED]
        known = {f.resolve() for f in self.files}
        for f in docs:
            if f.resolve() in known:
                continue
            if f.suffix.lower().lstrip(".") not in SUPPORTED:
                continue
            self.files.append(f)
            known.add(f.resolve())
            self.tree.insert("", "end", iid=str(len(self.files) - 1), values=(f.name, self._kind(f), "대기"))
        self.count_label.config(text=f"선택된 문서: {len(self.files)}개")
        if skipped:
            names = ", ".join(p.name for p in skipped[:5])
            messagebox.showinfo("건너뛴 파일", f"지원하지 않는 형식이라 건너뛰었습니다:\n{names}" + (" 외" if len(skipped) > 5 else ""))
        if not docs and not skipped:
            self.status.config(text="그 폴더에서 변환할 수 있는 문서를 찾지 못했습니다")

    @staticmethod
    def _kind(f: Path) -> str:
        ext = f.suffix.lower().lstrip(".")
        return FORMAT_LABEL.get(ext, ext.upper())

    def _clear(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.files.clear()
        self.results.clear()
        self.tree.delete(*self.tree.get_children())
        self.count_label.config(text="선택된 문서: 0개")
        self.progress["value"] = 0
        self.btn_open.config(state="disabled")

    # ---------- 변환 ----------
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showwarning("문서 없음", "먼저 변환할 문서를 끌어다 놓거나 선택해 주세요.")
            return
        if not (self.v_md.get() or self.v_json.get()):
            messagebox.showwarning("형식 선택", "Markdown 과 JSON 중 하나 이상을 골라 주세요.")
            return
        out_dir = None
        if self.v_outmode.get() == "custom":
            if not self.v_outdir.get().strip():
                messagebox.showwarning("폴더 선택", "결과를 저장할 폴더를 골라 주세요.")
                return
            out_dir = Path(self.v_outdir.get().strip())
        opts = ConvertOptions(write_markdown=self.v_md.get(), write_json=self.v_json.get(), save_images=self.v_img.get(),
                              out_dir=out_dir, save_hwpx=self.v_hwpx.get())
        self.results.clear()
        self.last_out_dirs.clear()
        self.progress.config(maximum=len(self.files), value=0)
        for iid in self.tree.get_children():
            self.tree.set(iid, "status", "대기")
            self.tree.item(iid, tags=())
        self.btn_go.config(state="disabled", text="변환 중…")
        self.status.config(text="변환 중입니다. 창을 닫지 마세요.")
        files = list(self.files)

        def work() -> None:
            convert_many(files, opts, progress=lambda i, n, r: self.q.put((i, n, r)))
            self.q.put(("done", None, None))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll(self) -> None:
        try:
            while True:
                i, n, r = self.q.get_nowait()
                if i == "done":
                    self._finish()
                else:
                    self._update_row(i - 1, r)
                    self.progress["value"] = i
                    self.status.config(text=f"{i}/{n} 처리 중… {r.source.name}")
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _update_row(self, idx: int, r: ConvertResult) -> None:
        self.results.append(r)
        iid = str(idx)
        if not self.tree.exists(iid):
            return
        if r.ok:
            tag = "warn" if r.warnings else "ok"
            text = ("⚠ " if r.warnings else "✔ ") + r.message
        else:
            tag, text = "fail", "✖ " + r.message
        self.tree.set(iid, "status", text)
        self.tree.item(iid, tags=(tag,))
        for o in r.outputs:
            d = o.parent  # .md/.json 과 그림 폴더 모두 결과 폴더 바로 아래에 있다
            if d not in self.last_out_dirs:
                self.last_out_dirs.append(d)

    def _finish(self) -> None:
        ok = sum(1 for r in self.results if r.ok)
        fail = len(self.results) - ok
        self.btn_go.config(state="normal", text="③ 변환 시작")
        self.btn_open.config(state="normal" if self.last_out_dirs else "disabled")
        msg = f"끝났습니다. 성공 {ok}개" + (f", 실패 {fail}개 (목록에서 빨간 줄을 두 번 누르면 이유가 보입니다)" if fail else "")
        self.status.config(text=msg)
        if fail == 0 and ok:
            if messagebox.askyesno("변환 완료", f"{ok}개 문서를 변환했습니다.\n결과 폴더를 열까요?"):
                self._open_out()

    # ---------- 역변환: JSON → 엑셀 ----------
    def _json_to_excel(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        sel = filedialog.askopenfilenames(title="엑셀로 되돌릴 JSON 선택 (변환결과 폴더의 .json)", filetypes=JSON_FILETYPES)
        if not sel:
            return
        out_dir = None
        if self.v_outmode.get() == "custom" and self.v_outdir.get().strip():
            out_dir = Path(self.v_outdir.get().strip())
        results = excel_from_json_many([Path(p) for p in sel], ConvertOptions(out_dir=out_dir))
        ok = [r for r in results if r.ok]
        fail = [r for r in results if not r.ok]
        for r in ok:
            for o in r.outputs:
                if o.parent not in self.last_out_dirs:
                    self.last_out_dirs.insert(0, o.parent)
        if self.last_out_dirs:
            self.btn_open.config(state="normal")
        lines = [f"엑셀로 만든 파일: {len(ok)}개"] + [f"  {r.outputs[0]}" for r in ok]
        if fail:
            lines += ["", f"실패: {len(fail)}개"] + [f"  {r.source.name}: {r.message}" for r in fail]
        warns = [w for r in ok for w in r.warnings]
        if warns:
            lines += ["", "참고:"] + [f"  {w}" for w in warns[:5]]
        self.status.config(text=f"JSON → 엑셀 완료 · 성공 {len(ok)}개" + (f", 실패 {len(fail)}개" if fail else ""))
        if fail and not ok:
            messagebox.showerror("JSON → 엑셀", "\n".join(lines))
        elif messagebox.askyesno("JSON → 엑셀", "\n".join(lines) + "\n\n결과 폴더를 열까요?"):
            self._open_out()

    def _show_detail(self, _evt=None) -> None:  # noqa: ANN001
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        r = next((x for x in self.results if x.source == self.files[idx]), None)
        if r is None:
            return
        body = f"파일: {r.source}\n결과: {r.message}\n"
        if r.outputs:
            body += "\n만든 파일:\n" + "\n".join(f"  {o}" for o in r.outputs)
        if r.warnings:
            body += "\n\n참고:\n" + "\n".join(w[-1200:] for w in r.warnings)
        messagebox.showinfo("자세히", body)

    def _open_out(self) -> None:
        if not self.last_out_dirs:
            return
        d = self.last_out_dirs[0]
        try:
            if sys.platform == "win32":
                os.startfile(str(d))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(d)])
            else:
                subprocess.Popen(["xdg-open", str(d)])
        except Exception as e:  # noqa: BLE001
            messagebox.showinfo("결과 폴더", f"{d}\n\n(자동으로 열지 못했습니다: {e})")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
