# 媒体前后处理（Media & Post-processing）

本模块覆盖翻译链路两端的媒体桥接：前置从 MKV 提取内嵌字幕并自动将 ASS 转成 SRT，后置把翻译好的 SRT 注入 `asshead.txt` 样式模板生成双语特效 ASS（智能中英文分行、MarginV 上下排列）。核心为 `subtitle/media/extractor.py` 的 `load_module` 统一封装，加上 `subtitle/pre-process` 与 `subtitle/post-process` 两个独立 CLI。

## Key Concepts

本节介绍媒体桥接的核心机制：extractor.py 统一封装、前置提取脚本、ASS 生成与智能分行。

### 媒体桥接（extractor.py）
解释：`load_module` 用 `importlib.util` 按绝对路径动态加载前后置脚本为 `extract_tool`/`ass_tool`，免静态 import；`extract_subtitles_from_mkv`/`convert_ass_to_srt` 委托 01 脚本提取/转换，`generate_ass_from_srt` 定位 `asshead.txt`（缺失回退当前目录）后委托 `srt_to_ass` 生成特效 ASS，一次封装让上层脱离脚本细节。

Reference: [[subtitle/media/extractor.py#extract_subtitles_from_mkv]] 与 [[subtitle/media/extractor.py#convert_ass_to_srt]]

### 前置提取脚本（01-extract_srt.py）
解释：`extract_subtitles` 以 `mkvmerge -J` 取元数据，按 `codec_id` 筛字幕轨道并决定后缀（srt/ass/sup-sub/图形跳过），`mkvextract tracks` 提取并写入 track id 与语言到文件名，ass 产物经 `convert_ass_file_to_srt` 自动转 SRT 并删原 ASS。

执行前校验 `mkvmerge`/`mkvextract`（MKVToolNix）在 PATH；脚本 `main` 支持传 MKV 路径，无参时打印帮助并尝试自动找当前目录唯一 MKV。Reference: [[subtitle/pre-process/01-extract_srt.py#extract_subtitles]] 与 [[subtitle/pre-process/01-extract_srt.py#convert_ass_file_to_srt]]

### ASS 生成（srt_to_ass）
解释：`srt_to_ass` 读 SRT 与 `asshead.txt` 头部，经 `parse_srt` 切块、`defaultdict` 按时间戳分组，跳过不含 `-->` 的异常行，用 `srt_time_to_ass` 换算时间轴；`main` 默认取脚本同目录 `asshead.txt`，支持 `--head`/`--output` 覆盖。输出按块位置定样式（英文/中文/注释），非注释行加 `{\be3}`、注释行加 `{\be6}` 边缘模糊。

Reference: [[subtitle/post-process/02-post_process_ass.py#srt_to_ass]]
补充说明时间换算：`srt_time_to_ass` 把 `00:00:09,960` 去掉毫秒末位并去掉小时前导 `0` 得 `0:00:09.96`。

### 智能分行（process_block_content）
解释：`process_block_content` 是双语分行的核心：`clean_single_line` 把中文句读「，」「。」替换为空格并剥离 `\N`，再按行交给 `detect_language_style` 判中/英文（命中 `\u4e00`~`\u9fff` 记为中文，否则英文）。同语言行两两合并成一组 `(text, style)`，遇到语言切换才切组并 `" "` 拼接，最终产出顺序合理的双语/多组事件。此段语义决定了为何一块内中英文能按行归并成上下两行、注释能单独成组。

Reference: [[subtitle/post-process/02-post_process_ass.py#process_block_content]] 与 [[subtitle/post-process/02-post_process_ass.py#detect_language_style]]

## Dependencies

内部：不直接 import [[core-common]]，而是经 `load_module` 动态加载自身前后置脚本；后置消费 [[pipeline]] 生成的 SRT 供 `srt_to_ass` 解析。外部：`subprocess`/`shutil.which`（调用与探测 MKVToolNix）、`json`、`os`、`re`、`argparse`、`collections.defaultdict`。样式来自 `asshead.txt`（缺失时 `srt_to_ass` 报错返回）。

## Consumed By

以下入口使用本模块的前后置媒体转换能力。

- [[entries]] — `main.py` 一键流程经 `extractor.py` 的 `load_module` 加载本模块前后置脚本：先 `extract_subtitles_from_mkv` 提取、`convert_ass_to_srt` 转换，翻译后再 `generate_ass_from_srt` 生成 ASS（详见 `load_module`/`generate_ass_from_srt`）。
- 用户直接运行 `subtitle/pre-process/01-extract_srt.py <mkv>` 与 `subtitle/post-process/02-post_process_ass.py <srt> [--head <path>] [--output <path>]` 做独立提取与格式转换。

## Error Conditions

本节列出媒体提取与转换时可能出现的错误与兜底行为。

- MKVToolNix 未安装：`extract_subtitles` 探测 `shutil.which` 失败，打印「未找到 MKVToolNix 工具」并返回 `[]`。
- `mkvmerge -J` 分析失败或输出非 JSON（`Exception`）：打印「分析文件失败」返回 `[]`；`mkvextract` 退出码非 0 抛 `CalledProcessError`，打印「提取过程中发生错误」返回 `[]`。
- MKV 无字幕轨道或文件不存在：分别打印「未发现字幕轨道」/「文件未找到」返回 `[]`。
- 提取出图形字幕（S_DVBSUB/S_HDMV/PGS）：直接跳过并提示无法转文本；ASS 转 SRT 编码异常（UTF-8/utf-8-sig 均失败）打印「无法读取文件编码」返回 `None`，原始 ASS 予以保留（不删除）。
- 后置无 SRT 或 asshead.txt：`srt_to_ass` 打印「找不到 SRT 文件」/「找不到 ASS 头部文件」并返回；`parse_srt` 对文件缺失/编码错误、非数字序号且无 `-->` 的块均按空处理或跳过，保证生成不会因个别脏块中断。