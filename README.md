# 🏥 医学知识库

一个本地化的医学文档管理平台，支持上传 Word/RTF/TXT 文档，保留原始格式，并提供全文关键词搜索与快速定位。

![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ 功能特性

| 功能 | 描述 |
|------|------|
| 📄 **文档上传** | 支持 .docx / .rtf / .txt 格式，拖拽或点击上传 |
| 🎨 **格式保留** | 字体颜色、高亮、加粗、斜体、下划线、表格等样式原样保留 |
| 📚 **内容累积** | 文档不断累积，支持按格式筛选和按时间排序 |
| 🔍 **全文搜索** | 跨文档关键词搜索，类似 Chrome 的搜索体验 |
| 📍 **快速定位** | 点击搜索结果直接跳转到文档内关键词位置 |
| 🗑️ **文档管理** | 支持删除文档 |

---

## 🚀 快速开始

### 启动后端服务

```bash
cd /Users/zhijie/Documents/医学知识库
python3 backend/server.py
```

服务启动后会输出：

```
╔═══════════════════════════════════════════════════╗
║         医学知识库后端服务                          ║
╠═══════════════════════════════════════════════════╣
║  访问地址:  http://127.0.0.1:8080                  ║
║  按 Ctrl+C 停止服务                                ║
╚═══════════════════════════════════════════════════╝
```

### 打开前端页面

在浏览器中访问：**http://127.0.0.1:8080**

或直接打开文件：`/Users/zhijie/Documents/医学知识库/frontend/index.html`

### 上传文档测试

准备一个 Word 文档（.docx），拖拽到上传区域即可。

---

## 🛠 技术架构

| 层级 | 技术方案 |
|------|---------|
| **前端** | React 18 (CDN 引入，无需构建) + 原生 JavaScript |
| **后端** | Python 标准库 `http.server`（零外部依赖） |
| **数据库** | SQLite + FTS5 全文索引 |
| **文档解析** | Python `zipfile` + `xml.etree.ElementTree`（标准库） |

---

## 📁 项目结构

```
医学知识库/
├── backend/
│   ├── server.py       # HTTP REST API 服务器
│   ├── database.py     # SQLite + FTS5 数据库模块
│   ├── doc_parser.py   # 文档解析器（Word/RTF/TXT）
│   └── knowledge_base.db  # SQLite 数据库文件（自动生成）
├── frontend/
│   ├── index.html      # 主页面入口
│   ├── styles.css      # 样式表
│   └── app.js          # React 应用
├── uploads/            # 上传文件临时存储
├── PRD_医学知识库.md    # 产品需求文档
├── UI设计文档.md        # UI 设计规范
└── README.md
```

---

## 🔌 API 接口

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/documents` | 获取文档列表 |
| `GET` | `/api/documents/:id` | 获取单个文档 HTML 内容 |
| `POST` | `/api/documents/upload` | 上传文档（multipart/form-data） |
| `DELETE` | `/api/documents/:id` | 删除文档 |
| `GET` | `/api/search?q=关键词` | 全文搜索 |

### 查询参数

- `format`: `all` | `docx` | `rtf` | `txt`
- `sort`: `desc` | `asc`

---

## ⌨️ 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+K` | 打开搜索面板 |
| `Esc` | 关闭搜索面板 |

---

## 🎯 格式保留说明

系统对 Word 文档格式的处理方式：

- **字体颜色**: `color` CSS 属性，映射自 Word 的 `<w:color>`
- **背景高亮**: Word 高亮（`<w:shd>`）映射为 `background:#RRGGBB`
- **加粗/斜体/下划线**: 对应 `<strong>` / `<em>` / `<u>` 标签
- **字号**: 根据 Word 半点单位转换为像素
- **字体名称**: 保留 `font-family`（包括中文黑体、宋体等）
- **表格**: 原样渲染 Word 表格（含边框样式）
- **标题样式**: 识别 Word 标题 1-6 并映射字号

> 💡 **提示**: .docx 文件本质上是一个 ZIP 压缩包，解析器直接读取其中的 XML 结构，提取格式信息并转换为 HTML 内联样式，无需任何外部库。

---

## 🔒 数据安全

- 数据库文件位于 `backend/knowledge_base.db`，建议定期备份
- 所有数据存储在本地，不会上传到任何服务器

---

## 📝 License

MIT License - 详见 [LICENSE](LICENSE) 文件
