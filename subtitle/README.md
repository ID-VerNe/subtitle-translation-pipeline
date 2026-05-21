# 🚀 AI 视频字幕自动化翻译 (CLI + GUI 版)

本工具提供了一套基于 **LLM (大语言模型)** 的全自动视频字幕翻译工作流。支持一键完成“格式转换 -> 术语提取 -> 直译 -> 润色 -> 样式注入”，并提供简洁易用的 GUI 图形界面。

---

## ⚡ 快速开始 (傻瓜式一键部署)

如果你不想手动配置复杂的环境，请按照以下步骤操作：

### 0. 准备工作 (仅 Windows 用户)

**macOS 用户可以跳过此步**，直接进入下一步运行脚本。

对于 Windows 用户，本工具依赖 Python 环境，如果你还没安装，请务必执行此步：

1.  **下载**: 前往 [Python 官网](https://www.python.org/downloads/windows/) 下载 **Python 3.10** 或更高版本 (推荐 3.10.11)。
2.  **安装 (非常重要)**:
    *   运行下载的安装包。
    *   **必须勾选**底部的 `Add Python to PATH` (将 Python 添加到环境变量)。
    *   选择 `Customize installation` (自定义安装)，确保 `tcl/tk and IDLE` 被勾选 (这是运行图形界面的核心组件)。
    *   点击 `Install` 完成安装。

### 1. 自动部署环境

*   **Windows 用户**:
    1.  找到项目根目录下的 `setup_project.ps1` 文件。
    2.  右键点击它，选择“**使用 PowerShell 运行 (Run with PowerShell)**”。
    3.  脚本会自动检测并安装：`Chocolatey` (包管理器)、`MKVToolNix` (提取工具) 以及隔离的 `Python 虚拟环境`。
*   **macOS 用户**:
    1.  打开终端 (Terminal)，进入项目目录。
    2.  输入命令 `bash setup_gui.sh` 并回车。
    3.  脚本会自动通过 `Homebrew` 安装所需依赖。

### 2. 配置 API Key (必须)

安装完成后，脚本会自动在 `subtitle/` 目录下生成一个 `.env` 文件：
1.  使用记事本打开 `subtitle/.env`。
2.  填入你的 `LLM_API_KEY` 和 `LLM_API_URL`。
3.  **(推荐)** 填写 `NER_API_KEY` 和 `NER_API_URL`（建议使用智谱 GLM-4-Flash，可免费大规模识别文中人名）。
4.  保存并关闭。

### 3. 启动程序

*   **Windows 用户**: 直接双击项目根目录下的 `start_gui.ps1` 即可打开图形界面。
*   **macOS 用户**: 在终端运行 `./start_gui.sh`。

---

## 🌟 核心优势

*   **全自动流水线**：一键完成“格式转换 -> 术语提取 -> 直译 -> 润色 -> 样式注入”。
*   **双向翻译支持**：不仅支持英译中，还内置了完善的**中译英**模式（自动切换 Prompt 并反转语料库）。
*   **智能梯次拯救 (Rescue Mode)**：遇到敏感词拦截（Content Filter）时，系统会自动启动 `8->6->4->2->1` 梯次减量并**自动剥离上下文**重试，确保任务不中断。
*   **全量批次滑动窗口**：润色阶段参考“上文+下文”共 3 个完整批次的语境，彻底解决指代不明问题。
*   **物理隔离语料库**：区分精校库与发现库，并针对不同翻译方向使用独立数据库，保护核心资产。

> 👉 **[想要了解这些功能是如何实现的？点击查看实现原理文档](../CLI_Implementation.md)**

---

## 🛠️ 准备工作

### 1. 环境配置

确保你已安装 Python 3.10+ 和 [MKVToolNix](https://mkvtoolnix.download/downloads.html#windows) (用于字幕提取)。

```powershell
# 进入 subtitle 目录
cd subtitle

# (推荐) 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，并填入你的 LLM API Key。

```powershell
cp .env.example .env
```

编辑 `.env` 文件：
```ini
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
LLM_API_URL=https://api.deepseek.com/v1/chat/completions  # 示例地址
LLM_MODEL=deepseek-chat                                   # 示例模型
```

---

## 🚀 推荐：一键自动化处理 (Automation Workflow)

为了简化操作，我们提供了一个主控脚本 `subtitle/main.py`。它会自动串联起提取、翻译和转换的所有步骤。

**基础用法示例**:

| 输入类型 | 目标格式 | 语言模式 | 运行命令 |
| :--- | :--- | :--- | :--- |
| **视频 (MKV)** | **ASS** | 英译中 (双语) | `python subtitle/main.py -i video.mkv` |
| **视频 (MKV)** | **SRT** | 英译中 (单语) | `python subtitle/main.py -i video.mkv -o out.srt --no-bilingual` |
| **字幕 (SRT)** | **ASS** | **中译英** (双语) | `python subtitle/main.py -i cn.srt --to-english` |
| **字幕 (SRT)** | **SRT** | **中译英** (单语) | `python subtitle/main.py -i cn.srt -o en.srt --to-english --no-bilingual` |
| **字幕 (ASS)** | **ASS** | 英译中 (双语) | `python subtitle/main.py -i source.ass` |

**核心逻辑提示**:
1. **输入自适应**: 脚本支持 `.mkv` (自动提取)、`.srt` 和 `.ass` (自动预转为中间格式)。
2. **输出位置**: 
   - **默认情况下** (即不加 `-o` 参数时)，生成的成品文件将保存在**输入文件所在的同一个文件夹内**。
3. **智能识别后缀**: 指定 `-o xxx.srt` 则输出纯文本，指定 `-o xxx.ass` 则自动应用样式。
4. **语言切换**: 使用 `--to-english` 开启中译英，系统将自动切换模板并反转术语表。

**配置说明 (.env)**:
所有的运行参数（API、并发数、批次大小等）现在都可以在 `.env` 文件中统一配置，CLI 仅需指定输入输出文件。

编辑 `.env` 文件：
```ini
# LLM API 配置
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
LLM_API_URL=https://api.deepseek.com/v1/chat/completions
LLM_MODEL_NAME=deepseek-chat

# 运行参数
MAX_CONCURRENT_REQUESTS=4
BATCH_SIZE=8
MAX_RETRIES=3
RETRY_DELAY=2.0
RPM_LIMIT=100

# 翻译温度 (0.0 - 1.0)

TEMP_TERMS=0.1
TEMP_LITERAL=0.3
TEMP_POLISH=0.5

# 语料库自动化
ENABLE_LLM_DISCOVERY=True  # 是否允许加载/保存 LLM 自动发现的术语库 (llm_discovery.db)
```

---

## 🛠️ 分步工作流程 (Step-by-Step Workflow)

如果你需要更精细地控制每一步（例如在翻译前手动修改提取出的 SRT），可以按照以下步骤操作。

### 第一步：提取与预处理 (Extract & Pre-process)

此步骤将从你的视频文件 (MKV) 中提取字幕。
*   如果提取出的是 ASS 字幕，脚本会自动将其转换为 SRT 格式。
*   如果提取出的是 SRT 字幕，脚本会直接输出。

**使用方法**:
```powershell
# 在项目根目录下运行
python subtitle/pre-process/01-extract_srt.py "你的视频文件.mkv"
```

**输出**: 脚本会在同目录下生成一个或多个 `.srt` 文件（例如 `视频名_track3_eng.srt`）。

---

### 第二步：LLM 智能翻译 (Main Translation)

此步骤是核心，使用 AI 将英文 SRT 翻译成中文。

**1. 定制 Prompt (关键!)**
AI 需要知道视频的主题才能准确提取术语。在运行前，**必须**检查并修改 `subtitle/prompts/term_extract.prompt`。
找到 `# Context` 部分，修改为你当前视频的主题。
```markdown
# Context
这是一部关于**{{在此处填写你的视频主题}}**的视频。
```

**2. 运行翻译**
```powershell
# 基础用法
python subtitle/translate_srt_llm.py -i "上一步生成的字幕.srt" -o "翻译结果.srt"
```

**常用参数**:
*   `--api-url`: 你的 LLM API 地址。
*   `--model-name`: 你使用的模型名称。
*   `--no-bilingual`: 仅输出中文（默认为双语对照）。
*   `--max-concurrent`: 直译阶段的最大并发数（默认 4）。

---

### 第三步：生成 ASS 特效字幕 (Post-process)

此步骤将翻译好的 SRT 文件转换为格式精美的 ASS 字幕。
它会自动识别中英文，进行智能分行，并应用预设的样式（如字体、大小、边框等）。

**使用方法**:
```powershell
# 将翻译好的 SRT 转换为最终的 ASS
python subtitle/post-process/02-post_process_ass.py "翻译结果.srt"

# (可选) 指定输出文件名
python subtitle/post-process/02-post_process_ass.py "翻译结果.srt" -o "最终成品.ass"
```

**功能**:
*   **智能分行**: 自动将同一时间轴内的中英文拆分为独立的行。
*   **自动样式**: 中文行应用中文样式，英文行应用英文样式（通过 `MarginV` 实现双语上下排列）。

---

## 📚 语料库管理 (Glossary Management)

本项目采用独特的“**物理隔离**”双数据库设计，并支持**深度上下文元数据**：

### 1. 核心字段说明 (New!)
现在的术语库支持 JSON 格式的高级定义，LLM 会严格遵守这些元数据：
- `source_term`: 英文原文。
- `target_term`: 中文译名。
- `category`: 类别（如 Named Entities, Idioms）。
- `description`: **词条背景说明**。解释这个词在特定文化或技术背景下的含义。
- `instruction`: **翻译指令**。明确要求 AI 如何处理，例如“保留引号”、“使用口语表达”、“需加译者注”等。

示例：
```json
{
  "source_term": "water off a duck's back",
  "target_term": "浮云",
  "description": "形容批评或警告不起作用。",
  "instruction": "使用现代中文网络流行语‘浮云’来捕捉这种‘不在意’的情绪。"
}
```

### 2. 双数据库设计
1. **精校语料库 (`glossary_cache.db`)**：
   - **数据来源**：自动扫描 `subtitle/glossaries/` 以及项目根目录下的 `online_db_api/glossary/`。
   - **特性**：拥有**最高优先级**。
   - **适用场景**：存放你多年积累的、带有详细背景说明的专业知识库。

2. **人名翻译数据库 (`names_translation.db`)**：
   - **数据来源**：内置 67 万条《世界人名翻译大辞典》数据。
   - **工作原理**：翻译前调用 `NER_MODEL` (如 GLM-4-Flash) 智能提取全文人物全名，并自动在库中匹配建议译名注入上下文。
   - **特性**：精准度极高，有效避免 `Will` (动词 vs 人名) 等歧义。

3. **发现库 (`llm_discovery.db`)**：
   - **数据来源**：由 LLM 通过“五步循环采样”在翻译前自动预读全文提取。
   - **特性**：辅助参考。你可以通过 `.env` 中的 `ENABLE_LLM_DISCOVERY` 开关控制是否将其保存到磁盘。
   - **适用场景**：自动补齐视频中偶尔出现的、你的主库未包含的专有名词或人名。

### 1. 手动修正术语
如果 AI 提取的术语有误，你可以：
1.  运行脚本，等待 "Step 1: 构建术语表" 完成。
2.  观察终端输出，找到 **"【当前生效的术语表】"** 及其下方的文件路径。
3.  **中断脚本** (Ctrl+C)。
4.  根据路径找到该 JSON 文件，手动编辑修正或添加键值对。
5.  **重新运行命令**，脚本会优先加载该缓存文件中的术语，而不会重新提取。

👉 **[进阶：如何构建自己的永久语料库？](glossaries/README.md)**
我们提供了一套完整的工具链，帮助你从过往的字幕文件中提取术语，构建属于自己的专业知识库。详情请点击上方链接。

### 2. 调整 Prompt
你可以随时修改 `subtitle/prompts/` 下的 `.prompt` 文件，以调整 AI 的翻译风格：
*   `literal_trans.prompt`: 负责直译，要求准确。
*   `review_and_polish.prompt`: 负责润色，控制口语化程度和语气。

## 💡 新手操作贴士 (Beginner Tips)

如果你是第一次在 Windows 命令行中使用此类工具，请务必阅读以下建议：

1. **如何快速复制路径**：
   在 Windows 文件夹中，按住键盘上的 **Shift 键**，同时**右键点击**视频或字幕文件，选择“**复制为路径 (Copy as path)**”。
2. **务必使用双引号**：
   如果你的文件夹名或文件名中包含**空格**（例如 `My Movie S01E01.mkv`），在输入命令时，**必须**用英文双引号把路径包起来，否则会报错：
   - ❌ 错误：`python subtitle/main.py -i C:\Movies\The Grand Tour.mkv`
   - ✅ 正确：`python subtitle/main.py -i "C:\Movies\The Grand Tour.mkv"`
3. **不要手动输入复杂路径**：
   你可以先输入 `python subtitle/main.py -i `（注意末尾有空格），然后直接把文件从文件夹里**拖拽**进命令行窗口，路径会自动填入。

---

## ❓ 常见问题 (FAQ)

**Q: 运行命令提示 "找不到文件" 或 "Invalid Argument"？**

A: 这通常是因为路径中包含空格但没有使用双引号包围。请参考上方的“新手贴士”，确保路径被 `""` 包裹。

**Q: 翻译中断了怎么办？**

A: 脚本会自动保存进度到 `.cache/` 目录下。直接重新运行，脚本会通过文件哈希识别任务并自动从断点续传。

**Q: 遇到敏感词被 API 拦截（Content Filter）怎么办？**

A: 脚本内置了**拯救逻辑**。它会自动尝试减小批次并剥离上下文语境进行翻译。如果最终依然失败，该行将保留原文/直译，确保整个任务不报错停止。

**Q: 想要强制重新翻译？**

A: 删除输出文件 (`.srt/.ass`) 以及 `.cache/` 目录下对应的缓存。如果需要彻底清除 AI 发现的术语，请删除 `llm_discovery.db` 或 `llm_discovery_cn.db`。精校库永远不会被程序修改。

**Q: 用什么模型合适？**

A: 目前本地测试使用 **GPT-OSS-20B**，在线API测试使用小米 **Mimo-V2-Flash** 、谷歌 **Gemini-3-Pro** 和零壹万物 **Yi-Lightning**。其他模型可以自行测试。

**Q: 运行 `01-extract_srt.py` 报错 "未找到 MKVToolNix 工具"？**

A: 请确保你已经安装了 MKVToolNix，并且把安装目录（例如 `C:\Program Files\MKVToolNix`）添加到了系统的 **环境变量 Path** 中。添加后需要重启终端才能生效。

**Q: 生成的字幕有乱码怎么办？**

A: 脚本默认使用 UTF-8 编码处理所有文件。如果你的源文件是 GBK 或其他编码，请先将其转换为 UTF-8。Windows 记事本 "另存为" 时选择编码为 UTF-8 即可。

**Q: 如何修改生成的 ASS 字幕样式（字体、颜色、大小）？**

A: `02-post_process_ass.py` 使用 `subtitle/post-process/asshead.txt` 作为样式模板。你可以直接编辑这个 txt 文件，修改 `[V4+ Styles]` 下的参数。建议使用 Aegisub 打开一个生成的 ass 文件，调好样式后，把头部信息复制回 `asshead.txt`。

**Q: API 报错 429 (Too Many Requests) 或超时？**

A: 这是因为并发数过高或 API 提供商限制了速率。
1. 尝试降低 `--max-concurrent` 参数（例如改为 2 或 1）。
2. 在 `.env` 或代码中增加重试等待时间。

**Q: 为什么生成的 ASS 字幕有时候中英文没有分行显示？**

A: 脚本是根据“一行中文、一行英文”的逻辑来自动分行的。如果翻译结果中，某一块只有中文或只有英文，或者中英文混在同一行（未换行），脚本可能无法正确识别。请检查中间的翻译结果 SRT 文件，确保 LLM 输出的格式是规范的双语对照格式。
