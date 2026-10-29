# 考题 · 本地题库

一个本地优先、可整体复制迁移的题库导入、收藏和刷题工具，适用于 Windows。

## 运行

双击 `start_portable.bat`。项目自带 `python_runtime/`，不需要另外安装 Python、虚拟环境或依赖。

程序启动后只绑定 `127.0.0.1`，会自动打开本地浏览器页面。题库和设置保存在项目目录的 `data/` 中，复制整个文件夹即可迁移。

## 功能

- DOCX、文字型 PDF 和图片导入
- 图片 OCR 与 DeepSeek 辅助整理
- 缺失答案的 DeepSeek 候选答案（需人工确认）
- 科目 → 考题 → 题目目录
- 搜索、题型/状态筛选、收藏和编辑
- 随机练习、精确判分、错题复盘
- 做题后的 DeepSeek 选项解析
- 本地 SQLite 数据库和本地设置文件

## API 设置

在“设置”页面保存 LLM/OCR 接口。密钥只保存在本机 `data/settings.json`，不要把这个文件提交到公开仓库。

## 开发运行

如果本机已经安装 Python，可以执行：

```bat
python -m pip install -r requirements.txt
python launcher.py --reload
```

## 目录说明

```text
app/              Flask 后端、SQLite 和解析服务
web/              原生 HTML/CSS/JavaScript 前端
data/             本地数据库和设置（不提交密钥与数据）
python_runtime/   可迁移的 Python 运行时和依赖
start_portable.bat
```

## 许可证

个人学习和复习使用。题库内容的版权归原始来源所有。
