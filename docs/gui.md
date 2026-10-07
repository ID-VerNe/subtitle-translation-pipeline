# 图形界面（GUI）

基于 Tkinter 的 MVC 桌面界面，提供翻译任务参数配置、预设管理与后台任务进度展示。

## Key Concepts

本节介绍 Tkinter MVC 界面各组件：主窗口视图、日志桥接、视图模型、预设管理与任务控制器。

### 主窗口视图（SubtitleTranslatorApp）
解释：`SubtitleTranslatorApp` 持有 root 窗口（950x850）并组合视图模型/预设管理器/任务控制器，`setup_ui` 用 `ttk.Notebook` 建「翻译主界面」（预设、文件选择、双语/格式/语言控件、进度与开始按钮）与「高级配置」两标签页；`browse_input/output` 经 filedialog 选文件联动改扩展名，首次启动弹窗提示补全 API Key。Reference: [[subtitle/gui/main_window.py#SubtitleTranslatorApp]]
### 日志桥接（GuiLogger）
解释：`GuiLogger` 继承 `logging.Handler`，构造时接收界面 Text 控件并预定义 INFO/ERROR/WARNING 前景色 tag；`emit` 经 `text_widget.after(0, append)` 把消息调度回 Tk 主线程追加并自动滚动，按 levelname 选色，结束后重新禁用，实现后台线程日志安全上屏。Reference: [[subtitle/gui/main_window.py#GuiLogger]]
### 视图模型（AppViewModel）
解释：`AppViewModel` 用 Tk `StringVar`/`BooleanVar`/`DoubleVar` 集中承载文件路径、目标与全套高级配置值，初始化从 `core.config.TranslationConfig` 读取默认值填充；并静态提供 `safe_get_int`/`safe_get_float`/`safe_get_bool` 类型转换工具，解析失败时记 warning 回退默认，bool 按字符串真值表兜底。Reference: [[subtitle/gui/view_models.py#AppViewModel]]
### 预设管理（PresetManager）
解释：`PresetManager` 构造时经 `load_presets` 载入预设并过滤 `_` 前缀内部键；`initialize_preset` 恢复上一激活或首个预设，`apply_preset` 写入各 Tk variable，`add_custom_preset` 继承当前预设并覆盖 GUI 字段保存，`save_to_current_preset` 按 XX_YY 大写键名组装后交给 `save_config_to_presets` 落盘。Reference: [[subtitle/gui/preset_manager.py#PresetManager]]
### 任务控制器（TaskController）
解释：`TaskController` 的 `start_thread` 校验输入非空后禁用按钮并派 daemon 线程跑 `run_process`，用 `TranslationArgs` 汇集参数后 `asyncio.run` 调 `run_translation` 并传 `update_progress` 回调，完成后按目标格式生成 ASS。

`run_process` 按扩展名做提取/直用/转 SRT 预处理；`update_progress` 经 `root.after` 安全更新进度条，`do_clear_cache` 询问后调 `clear_cache` 清理缓存。Reference: [[subtitle/gui/task_controller.py#TaskController]]

## Dependencies
内部：[[pipeline]]（`run_translation` 编排）、[[core-common]]（`TranslationConfig`/`TranslationArgs`/`clear_cache`/`load_presets`/`save_presets`/`save_config_to_presets`/`PRESETS_FILE`）、[[media-process]]（MKV 提取、ASS/SRT 转换）。外部：tkinter/ttk/filedialog/scrolledtext/messagebox、logging、threading、asyncio、os。

## Consumed By

以下入口使用本模块的图形界面能力。

- [[entries]] — `gui_app.run_gui` 创建 `tk.Tk()` 根窗口并实例化 `SubtitleTranslatorApp` 后进入 `mainloop()`，用户在此界面直接配置参数、切换预设并触发翻译任务；入口还会处理 python_embed 环境下 TCL/TK 库路径的环境变量注入。

## Error Conditions
本模块错误集中在预设文件与参数解析：首启 `PRESETS_FILE` 不存在时弹「首次运行提示」引导配置 API Key；输入文件为空时 `start_thread` 拒绝启动并记录；`run_process` 对 MKV 提取失败/无法识别扩展名/无有效 SRT 时中止任务；`safe_get_int`/`safe_get_float` 解析失败回退默认并告警；`apply_preset`/`save_to_current_preset` 及顶层异常被捕获，finally 恢复按钮可用。