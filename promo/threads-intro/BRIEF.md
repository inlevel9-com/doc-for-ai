---
workflow: general-video
flow: automation
storyboard: no
message: "hwp를 hwpx로 다시 저장할 필요 없이, 폴더째 한꺼번에 AI가 읽는 Markdown·JSON으로"
destination: threads
aspect: "4:5"
size: 1080x1350
fps: 30
length: 20s
language: ko
audience: 공공기관 Windows 사용자(비개발자)
sound: none
---

## Intent

스레드(Threads)용 20초 세로 소개 영상. 소리 없이 자막만으로 읽히며, Windows 창 모양의 가짜 앱 화면이 실제 프로그램과 같은 문구·배치로 6장면 시나리오대로 움직인다. 마지막 카드에 서비스 아이콘과 "AI 문서 변환기 | Designed by INLEVEL9".

## Scenes (user-approved in chat)

1. 탐색기에 쌓인 hwp 파일 — "PC에 쌓인 hwp, 아직도 하나씩 여세요?"
2. 폴더를 끌어다 놓는 장면 — "폴더째 끌어다 놓고"
3. 변환 시작 → 목록이 초록색 완료로 차오름 — "한꺼번에 Markdown·JSON으로"
4. 결과에 .md .json .hwpx — "hwpx로도 다시 저장"
5. JSON을 AI에 올려 엑셀 표가 나옴 — "내가 쓰는 AI에 넘기면 끝"
6. 끝 카드 — 아이콘 + "AI 문서 변환기 | Designed by INLEVEL9 · 설치 없음 · 인터넷 없이 동작"

## Customizations

- 실제 제품 UI(Tk 창)의 문구와 배치를 그대로 재현한 HTML. 타이틀 바는 Windows 11 스타일(사용자 대부분 Windows).
- 다른 프로젝트 이름은 어디에도 넣지 않는다. AI 화면은 특정 서비스 브랜드 없이 "내가 쓰는 AI"로.
- 같은 HTML을 나중에 소개 페이지에 재사용. README용으로 짧은 GIF도 함께 뽑는다.

## Assets

- `assets/icon.png` — 서비스 아이콘(제품 저장소 `src/docforai/assets/icon.png`와 동일)
- `assets/fonts/Pretendard-*.woff2` — 한국어 본문·제목 서체(SIL OFL)
