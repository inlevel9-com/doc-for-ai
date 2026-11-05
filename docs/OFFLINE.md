# 폐쇄망에 Doc for AI 배포하기

## Windows x64에서 실행

1. 인터넷에 연결된 PC에서 [최신 릴리스](https://github.com/inlevel9-com/doc-for-ai/releases/latest)의 **Assets**에서 `docforai-vX.Y.Z-windows-x64.zip`을 받습니다. 아직 릴리스되지 않은 빌드는 **Actions → Build packages → 성공한 실행 → Artifacts → docforai-windows-x64**에서 받을 수 있으며, 이 경우 받은 ZIP을 먼저 풀어 그 안의 배포 ZIP을 꺼냅니다.
2. 기관에서 허용한 전송 방식으로 옮긴 뒤 원하는 폴더에 압축을 풉니다. 예를 들어 `D:\docforai\`에 둘 수 있습니다.
3. 압축을 푼 폴더에서 `docforai.exe`를 엽니다. ZIP에서 꺼낸 파일은 같은 폴더 구조로 유지합니다.

Windows 패키지에 Python, Tcl/Tk, 기본 문서 파서가 포함됩니다. 사용 PC에는 인터넷 연결, Python 설치, API 키가 필요 없습니다. 변환 결과는 기본적으로 원본 옆 `변환결과`에 저장합니다.

## 새 버전 확인 끄기

프로그램은 열릴 때 GitHub 릴리스(`api.github.com`)에 새 버전이 있는지 한 번 묻습니다. 폐쇄망에서는 연결이 안 되어 몇 초 안에 조용히 포기하며 문서 처리에는 영향이 없습니다. 보안 정책상 시도 자체를 막으려면 창 아래쪽 **시작할 때 새 버전 확인** 체크를 해제하세요. 설정 파일은 Windows `%APPDATA%\docforai\settings.json`, Mac `~/Library/Application Support/docforai/settings.json` 이며 `{"check_updates": false}` 로 미리 배포해 둘 수도 있습니다.

## 구형 문서 변환 도구

DOC, PPT, RTF, ODT, ODP, ODS를 변환하려면 LibreOffice가 필요합니다. Windows에서 이미 설치한 LibreOffice를 사용하거나, 포터블 폴더를 패키지의 `tools/` 아래에 복사할 수 있습니다.

```text
docforai\tools\LibreOffice\program\soffice.exe
docforai\tools\LibreOfficePortable\App\libreoffice\program\soffice.exe
```

## 한글 hwpx 저장

`.hwp`를 `.hwpx`로 다시 저장하는 기능은 PC에 설치된 **한컴오피스 한글**을 자동으로 조종합니다(Windows 전용, 2018 이상 권장). 프로그램 안에 한글이 들어 있는 것이 아니므로 한글이 없는 PC에서는 체크 항목이 꺼지고, 나머지 변환은 그대로 됩니다. 인터넷은 쓰지 않습니다.

- 결과 `.hwpx`는 `.md`, `.json`과 같은 결과 폴더에 생기고 원본 `.hwp`는 바꾸지 않습니다. 암호·배포용 문서는 한글이 열지 못해 건너뛰며, 목록의 주의 표시에 이유가 남습니다.
- 한글은 다른 프로그램이 문서를 열 때 **파일 접근 확인 창**을 띄울 수 있습니다. 문서가 많을 때는 한컴 자동화 보안 모듈(`FilePathCheckerModule`)을 레지스트리 `HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules`에 등록해 두면 창이 뜨지 않습니다. 모듈 파일은 한컴오피스 자동화 SDK에 들어 있으며 이 프로그램에는 포함하지 않습니다.
- 한글이 설치된 Windows PC에서 실제로 확인해야 하는 기능입니다. 문제가 있으면 목록의 빨간 줄이나 주의 표시를 두 번 눌러 이유를 확인하세요.

## 폐쇄망에서 Windows 패키지 빌드

인터넷에 연결된 준비 PC와 빌드 PC 모두 Windows x64, PowerShell 7.4 이상, PATH에서 실행할 수 있는 Python 3.12 x64가 필요합니다.

```powershell
# Run on the connected preparation machine.
.\scripts\download-wheels.ps1

# Transfer the source tree and wheelhouse to the offline build machine.
.\scripts\build-windows.ps1
```

`wheelhouse/`가 있으면 빌드 스크립트는 패키지 인덱스를 비활성화하고 의존성과 빌드 백엔드를 로컬 wheel에서 설치합니다. ZIP은 `dist/`에 생성됩니다. 프로젝트 라이선스는 `LICENSE`에, 빌드 환경에서 수집한 의존성 라이선스는 `licenses/`에 포함됩니다.

## Mac 패키지 빌드

Apple Silicon Mac에서 Tk가 포함된 Python 3.12 이상으로 빌드합니다. `wheelhouse/`가 있으면 Windows와 같은 방식으로 로컬 wheel만 사용합니다.

```bash
./scripts/build-macos.sh
```

`dist/docforai-vX.Y.Z-macos-arm64.zip` 안에 `AI 문서 변환기.app`과 문서, 라이선스 고지가 들어갑니다. Apple 개발자 서명은 하지 않으므로 처음 열 때 시스템 설정의 **그래도 열기** 확인이 한 번 필요합니다.

자동 테스트는 Python 소켓 연결을 차단한 상태에서 기본 변환을 확인합니다. LibreOffice를 사용하는 확장 형식은 별도로 설치된 프로그램의 동작에 따릅니다.
