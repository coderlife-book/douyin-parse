# Local ASR Model Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户只在本地存在的 small/medium 模型中选择字幕识别模型，并把中文识别结果统一输出为简体。

**Architecture:** 由 `runtime_paths.py` 维护受限模型目录注册表并发现完整模型，API 校验选择后将模型名持久化到单线程字幕任务。识别服务按任务选择模型并仅缓存当前一个模型，OpenCC 在分段进入结果对象前完成繁转简。

**Tech Stack:** Python 3.11、FastAPI、faster-whisper、OpenCC、原生 HTML/CSS/JavaScript、PyInstaller Windows 绿色包

**Spec:** `docs/superpowers/specs/2026-08-25-local-asr-model-selection-design.md`

## Global Constraints

- 仅支持 `small` 与 `medium`，不支持 `large-v3`。
- 默认选择 `small`，但只展示本机完整存在的模型。
- Windows 绿色包同时携带 `small` 与 `medium`。
- 中文全文、分段和导出文本必须一致地转换为简体。
- 无标点的中文分段之间补基础标点，页面回显、复制全文和 TXT 使用同一全文。
- 旧任务没有模型字段时按 `small` 兼容读取。

---

### Task 1: 本地模型发现与 API 合约

**Files:**
- Modify: `runtime_paths.py`
- Modify: `api_server.py`
- Modify: `tests/test_runtime_paths.py`
- Modify: `tests/test_transcription_api.py`

**Interfaces:**
- Produces: `available_asr_models() -> list[dict[str, object]]`
- Produces: `asr_model_path(model_id: str) -> Path`
- Produces: `GET /asr/models`
- Produces: `POST /transcription/tasks` JSON 字段 `model: "small" | "medium"`

- [ ] **Step 1: Write the failing tests**

  增加临时根目录测试，断言仅返回同时含 `config.json`、`model.bin`、`tokenizer.json` 的 small/medium，且 API 拒绝不在返回集合中的模型。

- [ ] **Step 2: Run tests to verify they fail**

  Run: `.venv/bin/python -m unittest tests.test_runtime_paths tests.test_transcription_api -v`
  Expected: FAIL，原因是发现函数、路由和请求字段尚不存在。

- [ ] **Step 3: Write minimal implementation**

  在固定注册表中定义 small/medium 元数据，通过三个必需文件检查可用性；API 创建任务前校验模型并向任务管理器传递 `model`。

- [ ] **Step 4: Run tests to verify they pass**

  Run: `.venv/bin/python -m unittest tests.test_runtime_paths tests.test_transcription_api -v`
  Expected: PASS。

### Task 2: 任务持久化、模型切换与简体输出

**Files:**
- Modify: `services/transcription_tasks.py`
- Modify: `services/transcription_service.py`
- Modify: `tests/test_transcription_tasks.py`
- Modify: `tests/test_transcription_service.py`
- Modify: `requirements.txt`
- Modify: `requirements-windows.lock`

**Interfaces:**
- Consumes: `asr_model_path(model_id: str) -> Path`
- Produces: `TranscriptionTask.model: str`
- Produces: `transcribe_media(path, *, model_name="small", progress_cb=None, provider=None)`
- Produces: `SwitchingWhisperModelProvider.get(model_name: str)`

- [ ] **Step 1: Write failing task-selection tests**

  断言任务清单保存所选模型并以 `model_name=<选择值>` 调用识别器；旧清单恢复为 small。

- [ ] **Step 2: Verify task-selection tests fail**

  Run: `.venv/bin/python -m unittest tests.test_transcription_tasks -v`
  Expected: FAIL，任务尚未携带模型。

- [ ] **Step 3: Implement minimal task model propagation**

  给任务字段、创建函数、持久化和识别调用增加模型名，保留旧清单默认值。

- [ ] **Step 4: Write failing service tests**

  断言提供器由 small 切到 medium 时使用对应路径且不复用旧实例；断言 `這是繁體字` 的分段与全文变为 `这是繁体字`。

- [ ] **Step 5: Verify service tests fail**

  Run: `.venv/bin/python -m unittest tests.test_transcription_service -v`
  Expected: FAIL，尚无模型切换与 OpenCC 转换。

- [ ] **Step 6: Implement minimal service behavior**

  新增单模型缓存提供器；在分段去除首尾空白后调用 OpenCC `t2s`，再拼接全文；加入 `opencc-python-reimplemented==0.1.7`。

- [ ] **Step 7: Run focused tests**

  Run: `.venv/bin/python -m unittest tests.test_transcription_tasks tests.test_transcription_service -v`
  Expected: PASS。

### Task 3: 字幕页面模型选择

**Files:**
- Modify: `web/index.html`
- Modify: `tests/test_web_transcription_ui.py`

**Interfaces:**
- Consumes: `GET /asr/models`
- Consumes: `POST /transcription/tasks` 的 `model` 字段

- [ ] **Step 1: Write the failing UI contract test**

  断言页面存在带标签的 `transcriptionModel` 下拉框；脚本通过真实 API 数据填充选择并在创建任务时提交选中值。

- [ ] **Step 2: Run test to verify it fails**

  Run: `.venv/bin/python -m unittest tests.test_web_transcription_ui -v`
  Expected: FAIL，模型控件尚不存在。

- [ ] **Step 3: Implement the model selector**

  增加下拉框、无模型状态、模型加载函数与任务请求字段；任务列表显示模型标签。

- [ ] **Step 4: Run test to verify it passes**

  Run: `.venv/bin/python -m unittest tests.test_web_transcription_ui -v`
  Expected: PASS。

### Task 4: Windows 首发绿色包

**Files:**
- Modify: `packaging/windows/build.ps1`
- Modify: `packaging/windows/verify_bundle.py`
- Modify: `tests/test_windows_packaging.py`
- Modify: `app_meta.py`
- Modify: `docs/windows-release.md`

**Interfaces:**
- Consumes: `models/faster-whisper-small`
- Consumes: `models/faster-whisper-medium`
- Produces: `releases/抖音视频工具-v1.2.0-win64.zip`

- [ ] **Step 1: Write failing bundle verification tests**

  断言验证器要求两个模型的三个核心文件，缺少 medium 时失败。

- [ ] **Step 2: Run tests to verify they fail**

  Run: `.venv/bin/python -m unittest tests.test_windows_packaging -v`
  Expected: FAIL，验证器目前只要求 small。

- [ ] **Step 3: Update build and verification**

  构建时下载两个模型，验证器检查两套模型；版本升级到 1.2.0，并在说明中记录模型选择和性能取舍。

- [ ] **Step 4: Run all tests**

  Run: `.venv/bin/python -m unittest discover -s tests -v`
  Expected: PASS。

- [ ] **Step 5: Rebuild and verify the full package**

  将 medium 模型与 OpenCC 依赖加入现有 Windows staging，重新生成 UTF-8 文件名 ZIP；运行 `verify_bundle.py`、`ZipFile.testzip()`、SHA256 和 PE32+ x86-64 检查。

- [ ] **Step 6: Commit**

  Run: `git commit -m "feat(transcription): 支持本地模型选择与简体输出"`
