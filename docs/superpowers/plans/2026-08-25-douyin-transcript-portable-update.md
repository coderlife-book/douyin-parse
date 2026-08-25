# 抖音字幕解析与 Windows 绿色版实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有抖音下载工具中增加单视频语音转文案、双 Tab Web 界面、Windows 10 x64 绿色版构建和可回滚的离线一键更新。

**Architecture:** 保留 FastAPI 与静态 HTML，新增独立的 ASR 服务和单并发持久化任务管理器。运行时资源全部通过便携根目录定位；PyInstaller Windows onedir 包将程序核心、small 模型和 Playwright Chromium 分开摆放，以便普通更新只替换程序核心。

**Tech Stack:** Python 3.12、FastAPI、Uvicorn、faster-whisper、CTranslate2、PyAV、Playwright、PyInstaller、原生 HTML/CSS/JavaScript、PowerShell 5.1、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-08-25-douyin-transcript-portable-update-design.md`

## Global Constraints

- “字幕/文案”只表示视频声音的 ASR 转写结果，不表示发布描述，也不包含画面 OCR。
- 首版只支持单条视频链接；不处理图集、直播、主页批量任务或批量转写。
- ASR 固定使用 `Systran/faster-whisper-small` revision `536b0662742c02347bc0e980a01041f333bce120`、CPU 和 `int8`。
- 字幕任务最大运行并发为 1；视频下载任务保留现有行为。
- Windows 绿色版不依赖目标电脑预装 Python、FFmpeg、Chrome 或开发环境。
- 普通更新不得覆盖 `config.json`、`data/`、`downloads/`、`models/` 或 `browsers/`。
- Windows EXE 必须在 Windows 环境构建；macOS 不得被当作 Windows 产物验收环境。
- 所有功能改动遵守 RED → GREEN → REFACTOR，每个任务完成后使用 `type(scope): 中文描述` 提交。

---

### Task 1: 便携运行时路径与统一版本

**Files:**
- Create: `app_meta.py`
- Create: `runtime_paths.py`
- Modify: `services/douyin_login.py:11-15`
- Modify: `services/download_service.py:8-12`
- Modify: `api_server.py:13-16`
- Test: `tests/test_runtime_paths.py`
- Test: `tests/test_config_storage.py`

**Interfaces:**
- Produces: `APP_VERSION: str`、`MODEL_REVISION: str`、`portable_root() -> Path`、`web_index_path() -> Path`、`model_path() -> Path`、`transcripts_path() -> Path`、`browser_path() -> Path`。
- Consumes: `sys.frozen`、`sys.executable` 和可选测试环境变量 `DOUYIN_PARSE_ROOT`。

- [ ] **Step 1: 写便携路径失败测试**

```python
class RuntimePathTests(unittest.TestCase):
    def test_environment_root_controls_all_writable_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"DOUYIN_PARSE_ROOT": temp_dir}
        ):
            runtime_paths = load_runtime_paths()
            self.assertEqual(runtime_paths.portable_root(), Path(temp_dir))
            self.assertEqual(runtime_paths.transcripts_path(), Path(temp_dir) / "data" / "transcripts")
            self.assertEqual(runtime_paths.model_path(), Path(temp_dir) / "models" / "faster-whisper-small")

    def test_frozen_root_is_executable_parent(self):
        runtime_paths = load_runtime_paths()
        with mock.patch.object(runtime_paths.sys, "frozen", True, create=True), mock.patch.object(
            runtime_paths.sys, "executable", "/portable/抖音视频工具.exe"
        ):
            self.assertEqual(runtime_paths.portable_root(), Path("/portable"))
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `python3 -m unittest tests.test_runtime_paths -v`

Expected: FAIL，错误包含 `runtime_paths.py` 不存在或无法导入。

- [ ] **Step 3: 实现最小路径和版本模块**

```python
# app_meta.py
APP_VERSION = "1.1.0"
UPDATE_PROTOCOL_VERSION = 1
MODEL_REPOSITORY = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"

# runtime_paths.py
def portable_root() -> Path:
    override = os.environ.get("DOUYIN_PARSE_ROOT")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def web_index_path() -> Path:
    return portable_root() / "web" / "index.html"

def model_path() -> Path:
    return portable_root() / "models" / "faster-whisper-small"

def transcripts_path() -> Path:
    return portable_root() / "data" / "transcripts"

def browser_path() -> Path:
    return portable_root() / "browsers"
```

将 `douyin_login.py` 的 `CONFIG_PATH`、`COOKIE_PATH`、`DEFAULT_SAVE_DIR` 改为从 `portable_root()` 构造；将 `api_server.py` 的 `WEB_INDEX` 改为 `str(web_index_path())`，FastAPI 版本改为 `APP_VERSION`。

- [ ] **Step 4: 运行路径和既有配置测试**

Run: `python3 -m unittest tests.test_runtime_paths tests.test_config_storage tests.test_runtime_entrypoints -v`

Expected: PASS，且既有 Cookie 迁移测试不回归。

- [ ] **Step 5: 提交**

```bash
git add app_meta.py runtime_paths.py services/douyin_login.py services/download_service.py api_server.py tests/test_runtime_paths.py tests/test_config_storage.py
git commit -m "refactor(runtime): 统一绿色版运行路径与版本"
```

### Task 2: CPU small 模型转写服务

**Files:**
- Create: `services/transcription_service.py`
- Modify: `requirements.txt`
- Test: `tests/test_transcription_service.py`

**Interfaces:**
- Consumes: Task 1 的 `model_path()`。
- Produces: `TranscriptSegment(start: float, end: float, text: str)`、`TranscriptionResult(duration: float, language: str, segments: list[TranscriptSegment], text: str)`、`WhisperModelProvider.get()`、`transcribe_media(path, progress_cb=None, provider=None)`。

- [ ] **Step 1: 写模型参数和真实分段失败测试**

```python
class TranscriptionServiceTests(unittest.TestCase):
    def test_provider_loads_local_small_model_on_cpu_int8_once(self):
        factory = mock.Mock(return_value=object())
        provider = WhisperModelProvider(Path("/models/small"), model_factory=factory)
        self.assertIs(provider.get(), provider.get())
        factory.assert_called_once_with(
            "/models/small", device="cpu", compute_type="int8", local_files_only=True
        )

    def test_transcribe_joins_real_segments_and_reports_audio_progress(self):
        model = FakeModel(
            segments=[FakeSegment(0.0, 1.5, " 你好 "), FakeSegment(1.5, 3.0, " 世界 ")],
            duration=3.0,
        )
        progress = []
        result = transcribe_media("demo.mp4", progress_cb=progress.append, provider=FakeProvider(model))
        self.assertEqual(result.text, "你好世界")
        self.assertEqual(result.duration, 3.0)
        self.assertEqual(progress[-1], {"segment_count": 2, "processed_duration": 3.0, "duration": 3.0})
```

- [ ] **Step 2: 运行测试并确认因服务不存在而失败**

Run: `python3 -m unittest tests.test_transcription_service -v`

Expected: FAIL，错误包含 `services.transcription_service` 无法导入。

- [ ] **Step 3: 实现懒加载和转写**

```python
@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str

class WhisperModelProvider:
    def get(self):
        with self._lock:
            if self._model is None:
                factory = self._model_factory or _load_whisper_model
                self._model = factory(str(self._path), device="cpu", compute_type="int8", local_files_only=True)
            return self._model

def transcribe_media(path, progress_cb=None, provider=None):
    model = (provider or DEFAULT_MODEL_PROVIDER).get()
    raw_segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
    segments = []
    duration = float(info.duration or 0)
    for raw in raw_segments:
        text = raw.text.strip()
        if text:
            segments.append(TranscriptSegment(float(raw.start), float(raw.end), text))
        if progress_cb:
            progress_cb({"segment_count": len(segments), "processed_duration": float(raw.end), "duration": duration})
    return TranscriptionResult(duration, str(info.language or ""), segments, "".join(item.text for item in segments))
```

`_load_whisper_model` 在函数体内导入 `faster_whisper.WhisperModel`，使未安装 ASR 依赖时仍可运行不涉及模型的单元测试。`requirements.txt` 增加 `faster-whisper`，精确版本在 Windows 构建任务中锁定。

- [ ] **Step 4: 运行转写服务测试**

Run: `python3 -m unittest tests.test_transcription_service -v`

Expected: PASS，模型工厂只调用一次且进度来自真实分段。

- [ ] **Step 5: 提交**

```bash
git add services/transcription_service.py requirements.txt tests/test_transcription_service.py
git commit -m "feat(asr): 新增本地语音转写服务"
```

### Task 3: 单并发字幕任务与结果持久化

**Files:**
- Create: `services/transcription_tasks.py`
- Test: `tests/test_transcription_tasks.py`

**Interfaces:**
- Consumes: `download_video(share_url: str, *, cookie: str, save_dir: str, quality: str | None = None, progress_cb=None) -> DownloadResult` 和 `transcribe_media(path: str | Path, progress_cb: Callable | None = None, provider: WhisperModelProvider | None = None) -> TranscriptionResult`。
- Produces: `TranscriptionTask.snapshot(include_segments=False) -> dict`、`TranscriptionTaskManager.create_task(url, cookie) -> TranscriptionTask`、`get_task(task_id)`、`list_tasks()`、`text_path(task_id)`、`is_busy()`。

- [ ] **Step 1: 写单并发、持久化和恢复失败测试**

```python
class TranscriptionTaskManagerTests(unittest.TestCase):
    def test_executor_never_runs_two_transcriptions_together(self):
        tracker = ConcurrentTracker()
        manager = self.make_manager(transcriber=tracker.transcribe)
        first = manager.create_task("https://v.douyin.com/1", cookie="sid=1")
        second = manager.create_task("https://v.douyin.com/2", cookie="sid=1")
        self.wait_done(first, second)
        self.assertEqual(tracker.maximum, 1)

    def test_completed_task_writes_manifest_and_utf8_text(self):
        manager = self.make_manager(transcriber=fake_transcribe("中文文案"))
        task = manager.create_task("https://v.douyin.com/1", cookie="sid=1")
        self.wait_done(task)
        task_dir = self.root / "data" / "transcripts" / task.task_id
        self.assertEqual((task_dir / "transcript.txt").read_text(encoding="utf-8"), "中文文案")
        self.assertEqual(json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))["status"], "done")

    def test_restart_marks_running_manifest_interrupted(self):
        self.write_manifest(status="transcribing")
        manager = self.make_manager()
        self.assertEqual(manager.list_tasks()[0].status, "interrupted")
```

- [ ] **Step 2: 运行测试并确认因任务模块不存在而失败**

Run: `python3 -m unittest tests.test_transcription_tasks -v`

Expected: FAIL，错误包含 `services.transcription_tasks` 无法导入。

- [ ] **Step 3: 实现任务状态、线程池和原子持久化**

```python
class TranscriptionTaskManager:
    def __init__(self, root=None, downloader=download_video, transcriber=transcribe_media):
        self.root = Path(root or transcripts_path())
        self.root.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="douyin-asr")
        self._tasks = self._load_tasks()
        self._downloader = downloader
        self._transcriber = transcriber

    def create_task(self, url: str, *, cookie: str) -> TranscriptionTask:
        task = TranscriptionTask(source_url=url)
        self._tasks[task.task_id] = task
        self._persist(task)
        self._executor.submit(self._run_task, task, cookie)
        return task
```

`_run_task` 依次写入 `downloading`、`loading_model`、`transcribing`、`done` 或 `failed`；下载器使用任务目录下的 `temp/`，完成或失败都在 `finally` 中删除临时目录。`_persist` 先写 `manifest.json.tmp` 再 `os.replace`，TXT 仅在完成且全文非空时写入。恢复时把 `queued/downloading/loading_model/transcribing` 转为 `interrupted`。

- [ ] **Step 4: 运行任务与转写服务测试**

Run: `python3 -m unittest tests.test_transcription_tasks tests.test_transcription_service -v`

Expected: PASS，最高 ASR 并发为 1，临时文件被清理，恢复状态正确。

- [ ] **Step 5: 提交**

```bash
git add services/transcription_tasks.py tests/test_transcription_tasks.py
git commit -m "feat(transcription): 新增单并发字幕任务与持久化"
```

### Task 4: 字幕 API 与健康状态

**Files:**
- Modify: `api_server.py:1-171`
- Create: `tests/test_transcription_api.py`

**Interfaces:**
- Consumes: Task 3 的 `TranscriptionTaskManager`。
- Produces: `POST /transcription/tasks`、`GET /transcription/tasks`、`GET /transcription/tasks/{task_id}`、`GET /transcription/tasks/{task_id}/text`；扩展 `/health`。

- [ ] **Step 1: 写 API 状态码失败测试**

```python
class TranscriptionApiTests(unittest.TestCase):
    def test_create_requires_login(self):
        response = self.client.post("/transcription/tasks", json={"url": "https://v.douyin.com/demo"})
        self.assertEqual(response.status_code, 401)

    def test_create_returns_task_snapshot(self):
        self.login_manager.get_cookie.return_value = "sessionid=abc"
        response = self.client.post("/transcription/tasks", json={"url": "https://v.douyin.com/demo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")

    def test_text_returns_409_until_done(self):
        response = self.client.get("/transcription/tasks/running/text")
        self.assertEqual(response.status_code, 409)
```

- [ ] **Step 2: 运行测试并确认接口返回 404**

Run: `python3 -m unittest tests.test_transcription_api -v`

Expected: FAIL，创建接口当前返回 404。

- [ ] **Step 3: 实现请求模型和四个接口**

```python
class TranscriptionRequest(BaseModel):
    url: str = Field(min_length=1)
    session_id: str | None = None

@app.post("/transcription/tasks")
def create_transcription_task(payload: TranscriptionRequest) -> dict:
    cookie = login_manager.get_cookie(payload.session_id)
    if not cookie:
        raise HTTPException(status_code=401, detail="请先扫码登录抖音")
    return transcription_task_manager.create_task(payload.url, cookie=cookie).snapshot()

@app.get("/transcription/tasks")
def list_transcription_tasks() -> list[dict]:
    return [task.snapshot() for task in transcription_task_manager.list_tasks()]
```

详情接口使用 `include_segments=True`；TXT 接口只在 `status == "done"` 且文件存在时返回 `FileResponse(media_type="text/plain; charset=utf-8")`。`health()` 增加 `version`、`asr_model_ready` 和 `transcription_busy`。

- [ ] **Step 4: 运行 API 与既有 API 辅助测试**

Run: `python3 -m unittest tests.test_transcription_api tests.test_local_api_helpers -v`

Expected: PASS，既有下载接口行为不变。

- [ ] **Step 5: 提交**

```bash
git add api_server.py tests/test_transcription_api.py
git commit -m "feat(api): 提供字幕任务与文案下载接口"
```

### Task 5: 双 Tab Web 界面与字幕交互

**Files:**
- Modify: `web/index.html:1-1500`
- Create: `tests/test_web_transcription_ui.py`

**Interfaces:**
- Consumes: Task 4 的字幕 API。
- Produces: `activateTab(name)`、`createTranscription()`、`pollTranscriptionTask(id)`、`loadTranscriptionTasks()`、`renderTranscript(task)`、`copyTranscript()`。

- [ ] **Step 1: 写双 Tab 和交互契约失败测试**

```python
class WebTranscriptionUiTests(unittest.TestCase):
    def test_page_has_two_accessible_business_tabs(self):
        html = WEB_INDEX.read_text(encoding="utf-8")
        self.assertIn('role="tablist"', html)
        self.assertIn('data-tab="download"', html)
        self.assertIn('data-tab="transcription"', html)
        self.assertIn('aria-selected="true"', html)

    def test_page_calls_transcription_api_and_supports_copy_and_txt(self):
        html = WEB_INDEX.read_text(encoding="utf-8")
        self.assertIn('requestJson("/transcription/tasks"', html)
        self.assertIn('navigator.clipboard.writeText', html)
        self.assertIn('/text`', html)
        self.assertIn('aria-live="polite"', html)
```

- [ ] **Step 2: 运行测试并确认缺少 Tab**

Run: `python3 -m unittest tests.test_web_transcription_ui -v`

Expected: FAIL，HTML 中没有 `role="tablist"`。

- [ ] **Step 3: 实现 Tab 布局和字幕结果区域**

在共享登录区之后加入：

```html
<nav class="business-tabs" role="tablist" aria-label="业务功能">
  <button class="business-tab active" role="tab" data-tab="download" aria-selected="true" aria-controls="downloadTab">视频下载</button>
  <button class="business-tab" role="tab" data-tab="transcription" aria-selected="false" aria-controls="transcriptionTab">字幕解析</button>
</nav>
<section id="downloadTab" class="tab-panel active" role="tabpanel">
  <!-- 将现有链接解析、清晰度、下载进度和最近任务两个 panel 原样移入此处 -->
</section>
<section id="transcriptionTab" class="tab-panel" role="tabpanel" hidden>
  <label for="transcriptionUrl">抖音视频链接</label>
  <div class="row"><input id="transcriptionUrl"><button id="transcribeBtn" class="primary">开始识别</button></div>
  <div id="transcriptionStatus" class="status" aria-live="polite">等待输入链接</div>
  <div id="transcriptionProgress" class="download-progress">
    <div class="progress-track"><div id="transcriptionProgressFill" class="progress-fill"></div></div>
    <div class="progress-meta"><span id="transcriptionProgressText">0%</span><span id="transcriptionTime">等待识别</span></div>
  </div>
  <article id="transcriptResult" class="transcript-result" hidden>
    <header><h2 id="transcriptTitle">识别结果</h2><div class="row"><button id="copyTranscriptBtn">复制全文</button><a id="downloadTranscriptBtn" class="button primary">下载 TXT</a></div></header>
    <div id="transcriptText" class="transcript-text"></div>
    <ol id="transcriptSegments" class="transcript-segments"></ol>
  </article>
  <div id="transcriptionTaskList" class="task-list"></div>
</section>
```

CSS 延续现有米白、陶红、墨绿配色；Tab 使用实底选中态而非下划线，全文使用高可读的中文正文排版，时间分段使用紧凑等宽数字。窄屏下输入和按钮改为单列。

- [ ] **Step 4: 实现任务轮询、复制和下载**

```javascript
async function createTranscription() {
  const url = el.transcriptionUrl.value.trim();
  if (!url) return setStatus(el.transcriptionStatus, "请先输入抖音链接", "bad");
  const task = await requestJson("/transcription/tasks", {
    method: "POST", headers: headers(true),
    body: JSON.stringify({ url, session_id: state.sessionId || null }),
  });
  await pollTranscriptionTask(task.task_id);
}

async function copyTranscript() {
  const text = state.activeTranscript && state.activeTranscript.text;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  setStatus(el.transcriptionStatus, "文案已复制", "ok");
}
```

轮询间隔 700ms；`queued/downloading/loading_model/transcribing` 持续轮询，`done` 渲染全文和分段，`failed/interrupted` 停止轮询并显示后端消息。TXT 按钮跳转到 `/transcription/tasks/${taskId}/text`。

- [ ] **Step 5: 运行 UI 测试和 JavaScript 语法检查**

Run: `python3 -m unittest tests.test_web_transcription_ui -v && node -e "const fs=require('fs'),h=fs.readFileSync('web/index.html','utf8'),s=h.match(/<script>([\\s\\S]*?)<\\/script>/)[1]; new Function(s); console.log('JavaScript syntax OK')"`

Expected: PASS，并输出 `JavaScript syntax OK`。

- [ ] **Step 6: 提交**

```bash
git add web/index.html tests/test_web_transcription_ui.py
git commit -m "feat(web): 增加视频下载与字幕解析双标签页"
```

### Task 6: Windows EXE 启动器与绿色版构建

**Files:**
- Create: `desktop_launcher.py`
- Create: `requirements-windows.lock`
- Create: `packaging/windows/抖音视频工具.spec`
- Create: `packaging/windows/build.ps1`
- Create: `packaging/windows/verify_bundle.py`
- Create: `.github/workflows/build-windows-portable.yml`
- Modify: `services/douyin_login.py`
- Test: `tests/test_desktop_launcher.py`
- Test: `tests/test_windows_packaging.py`

**Interfaces:**
- Consumes: `server_runtime.start_background_server()`、Task 1 路径和固定模型 revision。
- Produces: `desktop_launcher.main() -> int`、`configure_bundled_browser()`、Windows ZIP artifact `抖音视频工具-v1.1.0-win64.zip`。

- [ ] **Step 1: 写启动器和包结构失败测试**

```python
class DesktopLauncherTests(unittest.TestCase):
    def test_launcher_opens_local_page_after_server_is_ready(self):
        with mock.patch("desktop_launcher.start_background_server", return_value=object()), mock.patch(
            "desktop_launcher.webbrowser.open"
        ) as open_browser, mock.patch("desktop_launcher.wait_until_exit", return_value=None):
            self.assertEqual(desktop_launcher.main(), 0)
        open_browser.assert_called_once_with("http://127.0.0.1:8787/")

class WindowsPackagingTests(unittest.TestCase):
    def test_bundle_contract_keeps_large_assets_outside_internal(self):
        required = {"抖音视频工具.exe", "models/faster-whisper-small/config.json", "browsers", "web/index.html", "一键更新.bat", "updater.ps1"}
        self.assertEqual(verify_bundle.missing_paths(self.bundle, required), set())
```

- [ ] **Step 2: 运行测试并确认启动器与构建文件不存在**

Run: `python3 -m unittest tests.test_desktop_launcher tests.test_windows_packaging -v`

Expected: FAIL，错误包含 `desktop_launcher` 或 `verify_bundle` 无法导入。

- [ ] **Step 3: 实现控制台启动器和绿色浏览器路径**

```python
def main() -> int:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browser_path()))
    handle = start_background_server()
    webbrowser.open(build_service_url(DEFAULT_HOST, DEFAULT_PORT))
    if handle is None:
        return 0
    try:
        wait_until_exit()
    except KeyboardInterrupt:
        pass
    finally:
        stop_background_server(handle)
    return 0
```

`douyin_login.py` 在冻结模式设置 `PLAYWRIGHT_BROWSERS_PATH` 并以 `playwright.chromium.launch(headless=False)` 启动随包 Chromium。源码模式保持 Playwright 默认路径。

- [ ] **Step 4: 实现 Windows 锁定依赖、spec 和构建脚本**

`requirements-windows.lock` 锁定直接依赖；`build.ps1` 创建虚拟环境、安装锁定依赖、执行 `playwright install chromium` 到 `browsers/`、调用 `snapshot_download(repo_id=MODEL_REPOSITORY, revision=MODEL_REVISION, local_dir="models/faster-whisper-small")` 下载模型，然后运行 PyInstaller onedir。spec 显式收集 `faster_whisper`、`ctranslate2`、`av`、FastAPI/Uvicorn 运行时和 `web/index.html`，模型与浏览器在构建后复制到 onedir 根目录。

- [ ] **Step 5: 实现 GitHub Actions Windows 构建**

```yaml
name: build-windows-portable
on:
  workflow_dispatch:
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: "pip" }
      - run: python -m unittest discover -s tests -v
      - shell: pwsh
        run: ./packaging/windows/build.ps1
      - uses: actions/upload-artifact@v4
        with:
          name: 抖音视频工具-v1.1.0-win64
          path: releases/抖音视频工具-v1.1.0-win64.zip
```

- [ ] **Step 6: 运行启动器、包结构和完整单测**

Run: `python3 -m unittest tests.test_desktop_launcher tests.test_windows_packaging -v && python3 -m unittest discover -s tests -v`

Expected: PASS；macOS 只验证脚本和结构契约，不声称已生成可用 Windows EXE。

- [ ] **Step 7: 提交**

```bash
git add desktop_launcher.py requirements-windows.lock packaging/windows .github/workflows/build-windows-portable.yml services/douyin_login.py tests/test_desktop_launcher.py tests/test_windows_packaging.py
git commit -m "build(windows): 增加绿色版可执行程序构建"
```

### Task 7: 可校验、可回滚的离线更新包

**Files:**
- Create: `packaging/update_manifest.py`
- Create: `packaging/windows/一键更新.bat`
- Create: `packaging/windows/updater.ps1`
- Create: `packaging/windows/build_update_package.py`
- Test: `tests/test_update_manifest.py`
- Test: `tests/test_update_scripts.py`
- Modify: `packaging/windows/build.ps1`

**Interfaces:**
- Consumes: Task 1 的 `APP_VERSION` 和 Task 6 的 onedir。
- Produces: `build_manifest(payload_root, version, minimum_version) -> dict`、`validate_relative_path(path) -> PurePosixPath`、`更新包-vX.Y.Z.zip`。

- [ ] **Step 1: 写清单哈希、排除目录和路径穿越失败测试**

```python
class UpdateManifestTests(unittest.TestCase):
    def test_manifest_hashes_core_files_and_excludes_user_data(self):
        self.write("抖音视频工具.exe", b"exe")
        self.write("web/index.html", b"html")
        self.write("data/transcripts/a/manifest.json", b"private")
        manifest = build_manifest(self.root, "1.1.1", "1.1.0")
        self.assertEqual([item["path"] for item in manifest["files"]], ["web/index.html", "抖音视频工具.exe"])
        self.assertEqual(manifest["files"][1]["sha256"], hashlib.sha256(b"exe").hexdigest())

    def test_relative_path_rejects_parent_escape(self):
        with self.assertRaises(ValueError):
            validate_relative_path("../config.json")
```

- [ ] **Step 2: 运行测试并确认清单模块不存在**

Run: `python3 -m unittest tests.test_update_manifest tests.test_update_scripts -v`

Expected: FAIL，错误包含 `packaging.update_manifest` 无法导入。

- [ ] **Step 3: 实现确定性清单与 ZIP 构建**

```python
EXCLUDED_TOP_LEVEL = {"config.json", "data", "downloads", "models", "browsers", "_rollback", "update-temp"}

def validate_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"非法更新路径：{value}")
    return path

def build_manifest(payload_root: Path, version: str, minimum_version: str) -> dict:
    files = []
    for path in sorted(item for item in payload_root.rglob("*") if item.is_file()):
        relative = path.relative_to(payload_root).as_posix()
        if PurePosixPath(relative).parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return {"protocol": 1, "version": version, "minimum_version": minimum_version, "files": files}
```

ZIP 根目录只包含 `update-manifest.json` 和 `payload/`。构建顺序按相对路径排序，所有文本用 UTF-8。

- [ ] **Step 4: 实现 BAT 和 PowerShell 更新器**

`一键更新.bat` 只调用：

```bat
@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0updater.ps1"
set "UPDATE_EXIT=%ERRORLEVEL%"
echo.
if not "%UPDATE_EXIT%"=="0" echo 更新失败，错误码：%UPDATE_EXIT%
pause
exit /b %UPDATE_EXIT%
```

`updater.ps1` 选择最高版本 ZIP，先检查 ZIP entry 不含绝对路径或 `..`，再解压到同盘临时目录；逐项核对清单大小和 SHA-256；结束目标 EXE；先完整备份当前核心，再移动新核心；二次校验。任一步骤抛出异常都只删除已安装的新核心并恢复实际已备份项；受保护集合包含 Cookie、数据、下载、模型、浏览器和更新器自身，更新负载同时受核心顶层白名单约束。

- [ ] **Step 5: 运行更新逻辑测试**

Run: `python3 -m unittest tests.test_update_manifest tests.test_update_scripts -v`

Expected: PASS，清单不包含用户数据，BAT 调用 PowerShell，脚本包含哈希校验和回滚分支。

- [ ] **Step 6: 提交**

```bash
git add packaging/update_manifest.py packaging/windows/一键更新.bat packaging/windows/updater.ps1 packaging/windows/build_update_package.py packaging/windows/build.ps1 tests/test_update_manifest.py tests/test_update_scripts.py
git commit -m "feat(update): 增加离线校验与一键回滚更新"
```

### Task 8: 文档、全量验证与 Windows 产物边界

**Files:**
- Modify: `README.md`
- Create: `docs/windows-release.md`
- Create: `版本说明.txt`

**Interfaces:**
- Consumes: 前七个任务的最终命令、目录和 API。
- Produces: 开发启动、字幕使用、Windows 构建、完整包、普通更新包和目标机验收说明。

- [ ] **Step 1: 更新 README 和 Windows 发布说明**

README 明确两个 Tab、CPU small 模型、源码依赖和 API；`docs/windows-release.md` 记录：

```powershell
./packaging/windows/build.ps1
python ./packaging/windows/build_update_package.py --bundle ./dist/抖音视频工具 --version 1.1.1 --minimum-version 1.1.0
```

同时写清楚 macOS 不能生成 Windows EXE，GitHub Actions artifact 的下载位置，以及同事把更新 ZIP 放到程序根目录后双击 `一键更新.bat` 的步骤。

- [ ] **Step 2: 运行完整自动验证**

Run: `python3 -m unittest discover -s tests -v`

Expected: 全部测试 PASS，0 failures，0 errors。

Run: `python3 -m py_compile app_meta.py runtime_paths.py api_server.py desktop_launcher.py services/*.py packaging/update_manifest.py packaging/windows/*.py`

Expected: exit 0，无语法错误。

Run: `node -e "const fs=require('fs'),h=fs.readFileSync('web/index.html','utf8'),s=h.match(/<script>([\\s\\S]*?)<\\/script>/)[1]; new Function(s); console.log('JavaScript syntax OK')"`

Expected: 输出 `JavaScript syntax OK`。

Run: `git diff --check && git status --short`

Expected: `git diff --check` exit 0；状态只包含本任务文档改动。

- [ ] **Step 3: 本机源码冒烟验证**

Run: `python3 -m uvicorn api_server:app --host 127.0.0.1 --port 8787`

另一个终端运行：

```bash
curl --fail http://127.0.0.1:8787/health
curl --fail http://127.0.0.1:8787/ | rg '视频下载|字幕解析'
```

Expected: 健康检查包含 `status=ok`、`version=1.1.0` 和 `asr_model_ready`；首页包含两个 Tab。结束服务后确认 8787 端口释放。

- [ ] **Step 4: 提交文档**

```bash
git add README.md docs/windows-release.md
git commit -m "docs(release): 补充字幕工具与绿色版发布说明"
```

- [ ] **Step 5: 记录 Windows 产物待验收项**

若当前没有可用 Windows 构建环境，不生成伪造 EXE，不宣称绿色版已验收。记录需要授权推送工作流或提供 Windows 机器后执行：Windows Actions 全量测试、bundle 结构检查、EXE 启动、健康接口、页面、模型初始化、真实视频转写和更新回滚。
