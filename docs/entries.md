# 入口模块（Entries）

本模块是系统所有启动入口与兼容层门面的集合：`main.py` 一键总控、`translate_srt_llm.py` 细粒度翻译 CLI、`gui_app.py` 桌面 GUI、`webui_gui.py` 浏览器 WebUI，配上两个向后兼容的聚合门面 `translation_pipeline.py` 与 `global_memory.py`，把高层业务逻辑重新暴露给调用方。

## Key Concepts

本节介绍系统的全部启动入口与兼容层门面：main.py 一键总控、细粒度翻译 CLI、桌面 GUI、WebUI 与两个聚合门面。

### CLI 总控入口（main.py）

解释：`main.py` 是一键式入口，识别 MKV/SRT/ASS 后自动走提取→翻译→转换全流程，无参数时拉起 GUI。`load_module` 用 `importlib.util` 按路径动态加载 pre/post-process 子工具，`main` 编排提取/转换→ `run_translation` → `srt_to_ass` 三步，`--to-english` 切换中译英、`--format` 决定最终 srt/ass。Reference: [[subtitle/main.py#main]] 和 [[subtitle/main.py#load_module]]

### 细粒度翻译 CLI（translate_srt_llm.py）

解释：`translate_srt_llm.py` 暴露翻译细粒度参数（批次、并发、温度、API/模型、推理力度、后置质检轮数）并托管全流程编排，封装 `TranslationConfig()` 作为参数默认值，`--enforce-consistency` 控制翻译后三级终审质检，运行时以 `asyncio.run` 调用 orchestrator。Reference: [[subtitle/translate_srt_llm.py#main]]

### 桌面 GUI 入口（gui_app.py）

解释：`run_gui` 启动 Tkinter MVC 界面，先探测嵌入式 python_embed 环境并注入 TCL/TK_LIBRARY 环境变量，再实例化 `SubtitleTranslatorApp` 并进入 `mainloop`。Reference: [[subtitle/gui_app.py#run_gui]]

### WebUI 入口（webui_gui.py）

解释：`WebUiGui` 是浏览器交互式分步翻译入口，提供刷术语库、"接入发现库/人名库"开关与 0/1/2/3/4A/4B 六个分步 prompt 生成按py，生成的 prompt 自动复制到剪贴板，术语发现库在本进程强制设为只读。Reference: [[subtitle/webui_gui.py#WebUiGui]]

### 兼容层门面（translation_pipeline.py）

解释：`translation_pipeline.py` 为重构后的翻译管线提供向后兼容的聚合导出，汇聚上下文构建、全局术语提取、梯次拯救与直译/润色两阶段符号，供旧调用方平滑迁移。Reference: [[subtitle/core/translation_pipeline.py]]

### 记忆门面（global_memory.py）

解释：`global_memory.py` 聚合 `memory/global_profile`、`memory/policy_engine`、`memory/scene_manager` 三块记忆的全部导出（全局画像构建、翻译策略、场景映射/分批），方便上层一次导入拿全记忆能力。Reference: [[subtitle/core/global_memory.py]]

## Dependencies

`main.py` 与 `translate_srt_llm.py` 调用 [[pipeline]] 编排翻译，依赖 [[core-common]] config（`TranslationConfig`/`TranslationArgs`/`CACHE_DIR`）与 `get_cache_path`，`main.py` 经 `load_module` 加载 [[media-process]]。

门面分别委托 [[core-context]]/[[core-rescue]]/[[core-stages]] 与 [[core-memory]]，运行时依赖 [[network]]；`gui_app.py`/`webui_gui.py` 依赖 [[gui]] 与 [[core-glossary]] 术语管理器。外部依赖 argparse、asyncio、importlib.util、logging、tkinter、pyperclip。

## Consumed By

用户通过 CLI 与 GUI 直接调用本模块各入口，无上层 Python 代码反依赖：命令行执行 `main.py`/`translate_srt_llm.py`、双击跑 `gui_app.py`、WebUI 跑 `webui_gui.py`；两个门面则由 [[pipeline]] 等重构后模块 import 以获得向后兼容的符号。

## Error Conditions

`main.py` 输入路径不存在时记录 `找不到输入文件` 提前返回；MKV 提取失败或 ASS 转 SRT 无产物时打印 `MKV 字幕提取失败` 终止。`webui_gui.py` 未输入英文原文时弹 `请先输入英文原文` 警告，术语库加载/刷新失败时捕获异常弹框。`translate_srt_llm.py` 用 `TranslationConfig()` 提供安全默认值，缺参时 argparse 报错，`--reasoning-effort` 用 choices 约束非法取值。