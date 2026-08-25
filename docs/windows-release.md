# Windows 绿色版构建与发布

## 产物边界

可复现的 Windows 绿色版应在 Windows 10/11 x64 或 GitHub Actions `windows-latest` 上构建。PyInstaller 不是跨平台编译器；复用已经验证的 Windows Python、Chromium 和 FFmpeg 运行时可以在其他系统组装目录，但不能替代目标 Windows 10 的最终双击验收。

完整绿色版包含：

```text
抖音视频工具/
├── 抖音视频工具.exe
├── _internal/                   # PyInstaller 方案
├── runtime/python/              # 复用运行时方案；与 _internal/ 二选一
├── runtime/ffmpeg/              # 仅复用运行时方案存在
├── browsers/
├── models/faster-whisper-small/
├── models/faster-whisper-medium/
├── web/index.html
├── version.json
├── 版本说明.txt
├── 一键更新.bat
└── updater.ps1
```

`config.json`、`data/` 和 `downloads/` 由程序首次运行创建，不允许打入发布包。

## GitHub Actions 构建

1. 将功能分支推送到 GitHub。
2. 打开 Actions → `build-windows-portable` → Run workflow。
3. 当前首发构建只生成完整包；必填的 `minimum_version` 可填写当前基线 `1.2.0`。
4. 下载 artifact `douyin-video-tool-win64`。

工作流会执行全部 Python 测试、Windows PowerShell 更新演练、模型和 Chromium 下载、PyInstaller 构建与产物结构校验。首发只上传完整包，不应生成同版本更新包；后续版本按需生成普通更新包。

## Windows 本机构建

使用已安装 Python 3.12 和 PowerShell 7.3+ 的 Windows 构建机（目标同事电脑运行绿色版和更新器不需要安装这些环境）：

```powershell
pwsh -ExecutionPolicy Bypass -File ./packaging/windows/build.ps1
```

构建脚本使用 `requirements-windows.lock`，内置模型固定为：

- `small`：`Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120`
- `medium`：`Systran/faster-whisper-medium@08e178d48790749d25932bbc082711ddcfdfbc4f`
- 推理设备：CPU
- 计算类型：`int8`

程序只在网页中展示本地文件完整的 `small/medium` 模型，默认使用 `small`。`medium` 识别效果更好，但在 i5-10400F 上耗时更长。

中文转写会先使用 OpenCC `t2s` 转为简体，再为缺少标点的相邻中文分段和中文空格补基础逗号，必要时补全文句号。模型已有中英文终止标点时不会重复追加。页面回显、复制全文和 TXT 来自同一份持久化全文。

## 手动生成后续更新包

先把 `app_meta.py` 中的 `APP_VERSION` 提升到目标版本并重新构建绿色目录，然后运行：

```powershell
python ./packaging/windows/build_update_package.py `
  --bundle ./dist/抖音视频工具 `
  --output ./releases/更新包-v1.2.1.zip `
  --version 1.2.1 `
  --minimum-version 1.2.0
```

普通更新包只包含已登记且带 SHA-256 的程序核心。模型、Chromium、Cookie、下载和字幕记录不进入 ZIP。

也可以在构建完整包时追加 `-BuildUpdatePackage -MinimumVersion "1.2.0"`。首发版本不要使用该参数。

## 同事更新步骤

1. 退出正在运行的工具；不退出也可以，更新脚本会结束目标进程。
2. 把唯一一个 `更新包-vX.Y.Z.zip` 放进绿色版根目录。
3. 双击 `一键更新.bat`。
4. 看到“更新成功”后等待程序重新启动。
5. 若校验失败，窗口会显示原因，旧版本会从 `_rollback/` 恢复。

## 发布前验收

在与目标机相同或等效的 Windows 10 x64 环境逐项执行：

1. 全新解压，双击 EXE，浏览器打开 `http://127.0.0.1:8787/`。
2. `/health` 返回 `status=ok`、正确 `version` 和 `asr_model_ready=true`。
3. 扫码登录后重启，Cookie 仍存在。
4. 视频下载 Tab 能解析、预览和保存一个 MP4。
5. 字幕解析 Tab 只展示完整存在的 `small/medium`，两个模型都能创建任务。
6. 中文语音能转为简体文案，缺少标点时有基础逗号和句号，进度及分段数真实变化。
7. 页面回显、复制全文与下载 TXT 内容一致，中文无乱码。
8. 重启后仍可查看 `data/transcripts/` 中的历史文案。
9. 从上一版本执行普通更新，Cookie、模型、浏览器、下载和字幕记录均保留。
10. 篡改更新 ZIP 内任一负载文件后，更新被拒绝且旧版本仍可启动。

没有完成第 1–10 项时，只能把状态标记为“Windows 构建待验收”，不能宣称已经完成目标 Windows 验收。
