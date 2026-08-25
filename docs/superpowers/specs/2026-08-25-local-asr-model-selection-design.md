# 本地 ASR 模型选择与简体输出设计

## 目标

字幕解析页面允许用户在本机已经存在的 ASR 模型中手动选择，并将中文识别结果统一转换为简体中文。

## 范围

- 仅支持 `small` 与 `medium`，不支持 `large-v3`。
- 默认选择 `small`。
- 程序只展示 `models/faster-whisper-small` 与 `models/faster-whisper-medium` 中实际完整存在的模型。
- 首发 Windows 绿色包同时携带 `small` 与 `medium`。
- 旧任务没有模型字段时按 `small` 兼容读取。
- 中文分段文本先进行繁体转简体，再生成全文，确保分段、全文和导出文本一致。
- 无标点的相邻中文分段之间补 `，`，中文全文末尾补 `。`；模型已有标点时不重复添加。

## 后端设计

- `runtime_paths.py` 提供受限模型注册表与本地模型发现函数。模型完整性的最低条件为目录中同时存在 `config.json`、`model.bin`、`tokenizer.json`。
- `GET /asr/models` 返回本地可用模型，包含 `id`、`label`、`description` 与 `is_default`。
- `POST /transcription/tasks` 接收 `model`；缺省为 `small`，不存在或不完整时返回 400。
- 字幕任务持久化 `model`，并将它传给识别服务。
- 识别服务使用一个按名称切换的模型提供器；切换时释放旧模型，避免多个模型同时占用内存。

## 前端设计

- 字幕解析表单增加模型下拉框。
- 页面加载时请求 `/asr/models`，只渲染接口返回的本地模型；优先选择默认模型，否则选择第一个可用模型。
- 没有本地模型时禁用开始识别按钮并显示明确提示。
- 创建任务时提交当前选择的 `model`，历史任务显示使用的模型。

## 简体转换

- 使用 `opencc-python-reimplemented` 的 `t2s` 配置。
- 每个非空 ASR 分段在保存前转换，英文、数字和标点保持不变。
- 转换依赖同时加入开发依赖与 Windows 锁定依赖。

## 打包

- Windows 构建脚本下载并验证 `small`、`medium` 两个模型。
- 绿色包不包含 `large-v3`。
- 首次分发只提供最新完整包，不生成同版本更新包。
