# Windows 绿色版构建与发布

## 产物边界

Windows 绿色版必须在 Windows 10/11 x64 或 GitHub Actions `windows-latest` 上构建。PyInstaller 不是跨平台编译器，因此 macOS 上的源码测试不能替代 EXE 验收。

完整绿色版包含：

```text
抖音视频工具/
├── 抖音视频工具.exe
├── _internal/
├── browsers/
├── models/faster-whisper-small/
├── web/index.html
├── version.json
├── 版本说明.txt
├── 一键更新.bat
└── 更新工具.ps1
```

`config.json`、`data/` 和 `downloads/` 由程序首次运行创建，不允许打入发布包。

## GitHub Actions 构建

1. 将功能分支推送到 GitHub。
2. 打开 Actions → `build-windows-portable` → Run workflow。
3. `minimum_version` 填入允许普通更新的最低已安装版本，例如 `1.1.0`。
4. 下载 artifact `douyin-video-tool-win64`。

工作流会执行全部 Python 测试、Windows PowerShell 更新演练、模型和 Chromium 下载、PyInstaller 构建、产物结构校验，并上传 `releases/` 下的完整包和普通更新包。

## Windows 本机构建

使用已安装 Python 3.12 的 Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
./packaging/windows/build.ps1 -MinimumVersion "1.1.0"
```

构建脚本使用 `requirements-windows.lock`，模型固定为：

- 仓库：`Systran/faster-whisper-small`
- revision：`536b0662742c02347bc0e980a01041f333bce120`
- 推理设备：CPU
- 计算类型：`int8`

## 手动生成后续更新包

先把 `app_meta.py` 中的 `APP_VERSION` 提升到目标版本并重新构建绿色目录，然后运行：

```powershell
python ./packaging/windows/build_update_package.py `
  --bundle ./dist/抖音视频工具 `
  --output ./releases/更新包-v1.1.1.zip `
  --version 1.1.1 `
  --minimum-version 1.1.0
```

普通更新包只包含已登记且带 SHA-256 的程序核心。模型、Chromium、Cookie、下载和字幕记录不进入 ZIP。

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
5. 字幕解析 Tab 能把含中文语音的视频转为非空文案，进度和分段数真实变化。
6. 复制全文与下载 TXT 内容一致，中文无乱码。
7. 重启后仍可查看 `data/transcripts/` 中的历史文案。
8. 从上一版本执行普通更新，Cookie、模型、浏览器、下载和字幕记录均保留。
9. 篡改更新 ZIP 内任一负载文件后，更新被拒绝且旧版本仍可启动。

没有完成第 1–9 项时，只能把状态标记为“Windows 构建待验收”，不能宣称绿色版已经交付。
