# 폐쇄망에 Doc for AI 배포하기

## Windows x64에서 실행

1. 인터넷에 연결된 PC에서 [최신 릴리스](https://github.com/inlevel9-com/doc-for-ai/releases/latest)의 **Assets**에서 `docforai-vX.Y.Z-windows-x64.zip`을 받습니다. 아직 릴리스되지 않은 빌드는 **Actions → Build packages → 성공한 실행 → Artifacts → docforai-windows-x64**에서 받을 수 있으며, 이 경우 받은 ZIP을 먼저 풀어 그 안의 배포 ZIP을 꺼냅니다.
2. 기관에서 허용한 전송 방식으로 옮긴 뒤 원하는 폴더에 압축을 풉니다. 예를 들어 `D:\docforai\`에 둘 수 있습니다.
3. 압축을 푼 폴더에서 `docforai.exe`를 엽니다. ZIP에서 꺼낸 파일은 같은 폴더 구조로 유지합니다.

Windows 패키지에 Python, Tcl/Tk, 기본 문서 파서가 포함됩니다. 사용 PC에는 인터넷 연결, Python 설치, API 키가 필요 없습니다. 변환 결과는 기본적으로 원본 옆 `변환결과`에 저장합니다.

## 구형 문서 변환 도구

DOC, PPT, RTF, ODT, ODP, ODS를 변환하려면 LibreOffice가 필요합니다. Windows에서 이미 설치한 LibreOffice를 사용하거나, 포터블 폴더를 패키지의 `tools/` 아래에 복사할 수 있습니다.

```text
docforai\tools\LibreOffice\program\soffice.exe
docforai\tools\LibreOfficePortable\App\libreoffice\program\soffice.exe
```

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
