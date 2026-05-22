# Tianwen ClearC

Tianwen ClearC 是一个桌面磁盘空间分析工具，支持在 Windows 和 macOS 上扫描目录或磁盘，并通过图形树快速查看文件和目录的空间占用情况。各平台安装包请在仓库的 Releases 页面下载。

## 功能特点

- 支持选择磁盘或任意目录进行扫描。
- 使用后台线程扫描，避免界面卡死。
- 通过图形树展示空间占用，矩形面积越大表示占用越大。
- 上方目录树展示名称、大小、文件数、目录数。
- 图形树支持单击查看详情、双击进入目录、返回上级。
- 支持关键字、扩展名、最小大小、文件/目录类型过滤。
- 支持右键打开、在资源管理器或 Finder 中显示、复制路径。
- 支持导出 CSV 和 JSON 报告。
- 对无权限目录显示“无权限跳过”，并提供跳过详情列表。
- 对扫描过程中临时消失的缓存或日志文件静默忽略。
- 支持 Windows exe 和 macOS app/dmg 打包。

## 界面说明

程序主界面分为上下两块：

- 目录树：以树形结构展示扫描结果，方便逐层查看目录和文件。
- 图形树：用矩形面积展示空间占用，黄色/橙黄色表示目录，文件会按扩展名分配不同颜色。

扫描系统目录时，部分路径可能因为权限不足无法读取。程序会继续扫描其他目录，并在状态栏显示“无权限跳过 N 项”；点击该按钮可以查看具体路径和原因。

## 环境要求

- Python 3.10 或更高版本。
- Windows 10/11 或 macOS。
- Python 依赖见 `requirements.txt` 和 `requirements-dev.txt`。

## 本地运行

macOS / Linux：

```bash
cd tianwen_clearC
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
tianwen-clearc
```

Windows PowerShell：

```powershell
cd tianwen_clearC
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
tianwen-clearc
```

不激活虚拟环境也可以直接运行：

```bash
.venv/bin/python -m tianwen_clearc.app
```

Windows：

```powershell
.venv\Scripts\python -m tianwen_clearc.app
```

## 测试和代码检查

```bash
pytest
ruff check .
python -m compileall -q src tests packaging
```

## Windows 打包

在 Windows 环境执行：

```bat
scripts\build_windows.bat
```

打包完成后查看：

```text
dist\TianwenClearC\TianwenClearC.exe
```

## macOS 打包

在 macOS 环境执行：

```bash
chmod +x scripts/build_macos.sh
scripts/build_macos.sh
```

脚本会使用 `tianwen_clearc.icns` 作为应用图标，并输出到：

```text
release/Tianwen ClearC.app
release/Tianwen_ClearC_macOS_arm64.zip
release/Tianwen_ClearC_macOS_arm64.dmg
release/tianwen_clearC_20260521_152516.zip
```

## 项目结构

```text
tianwen_clearC/
  docs/                         文档
  packaging/                    打包配置
  scripts/                      Windows/macOS 打包脚本
  src/tianwen_clearc/           应用源码
  tests/                        自动化测试
  pyproject.toml                项目配置
  requirements.txt              运行依赖
  requirements-dev.txt          开发依赖
  tianwen_clearc.icns           macOS 应用图标
```

## 文档

- `docs/01_research.md`：调研文档
- `docs/02_implementation_plan.md`：实施文档
- `docs/03_tech_stack.md`：技术栈说明
- `docs/04_usage_guide.md`：使用说明
- `docs/05_commands.md`：命令汇总

## 说明

Tianwen ClearC 默认不跟随符号链接，避免循环扫描或重复统计。打包好的 `.exe`、`.app`、`.dmg`、`.zip` 建议通过 GitHub Releases 发布，不建议直接提交到源码仓库。
