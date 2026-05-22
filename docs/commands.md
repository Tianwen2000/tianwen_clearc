# Tianwen ClearC 命令汇总

日期：2026-05-21

## 1. 进入项目目录

```bash
cd /Users/a123/PycharmProjects/pipenv_project/deng/tianwen_clearC
```

## 2. 创建虚拟环境

```bash
python3 -m venv .venv
```

## 3. 激活虚拟环境

macOS / Linux：

```bash
source .venv/bin/activate
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

Windows CMD：

```bat
.venv\Scripts\activate.bat
```

## 4. 安装依赖

开发环境：

```bash
pip install -r requirements-dev.txt
pip install -e .
```

只安装运行依赖：

```bash
pip install -r requirements.txt
pip install -e .
```

## 5. 启动程序

已激活虚拟环境：

```bash
tianwen-clearc
```

未激活虚拟环境：

```bash
.venv/bin/python -m tianwen_clearc.app
```

Windows 未激活虚拟环境：

```powershell
.venv\Scripts\python -m tianwen_clearc.app
```

## 6. 运行测试

```bash
pytest
```

或：

```bash
.venv/bin/python -m pytest
```

## 7. 代码检查

```bash
ruff check .
```

自动修复一部分问题：

```bash
ruff check . --fix
```

格式化代码：

```bash
ruff format .
```

## 8. 语法编译检查

```bash
python -m compileall -q src tests
```

## 9. Windows 打包 exe

需要在 Windows 环境执行：

```bat
scripts\build_windows.bat
```

打包完成后查看：

```powershell
dist\TianwenClearC
```

如果手动打包，建议使用项目内置 spec，避免 PyInstaller 漏收 `tianwen_clearc.treemap`：

```bat
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m PyInstaller --clean --noconfirm packaging\tianwen_clearc_windows.spec
```

## 10. macOS 打包 app

需要在 macOS 环境执行：

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

手动打包时需要带上 `--icon tianwen_clearc.icns`：

```bash
.venv/bin/python -m PyInstaller --clean --noconfirm --windowed \
  --name "Tianwen ClearC" \
  --icon tianwen_clearc.icns \
  --paths src \
  src/tianwen_clearc/app.py
```

## 11. 退出虚拟环境

```bash
deactivate
```
