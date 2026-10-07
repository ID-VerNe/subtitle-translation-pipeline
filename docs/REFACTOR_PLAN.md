# 字幕翻译 Pipeline — 重构方案

> 诊断日期：2026-10-04　代码规模：7691 行 Python（不含 python_embed / 备份 / 缓存）
> 原则：**算法不动，只换外壳**。梯次拯救、三级术语库、场景对齐、预取流水线是资产，重构要保护它们而不是重写。

---

## 一、诊断结论

### 核心判断

业务逻辑本身不乱。乱的是三层基础设施：**包结构 / 入口 / 状态管理**。
所以这是一次**外壳重写**，不是业务重写。如果按"推倒重来"的思路做，会毁掉最值钱的部分。

### 六处具体缺陷

| # | 缺陷 | 位置 | 严重度 | 后果 |
|---|---|---|---|---|
| 1 | 包边界不存在 | 全项目 7 处 `sys.path` 注入 | 致命 | 模块被重复加载 |
| 2 | 双导入体系并存 | `core.*` (42 处) vs `subtitle.core.*` (8 处) | 致命 | **单例翻倍，状态分裂** |
| 3 | 四入口四套世界 | `main.py` / `translate_srt_llm.py` / `gui_app.py` / `webui_gui.py` | 高 | 参数丢失、行为不一致 |
| 4 | 真 bug：NameError | `pipeline/orchestrator.py:367` | 高 | `--enable-annotations` 必崩 |
| 5 | 配置三处搬运 | `TranslationConfig` → `TranslationArgs` → `getattr` | 中 | 新增字段要改 3 处 |
| 6 | 隐式全局状态 | `glossary_manager`、`safety_fuzzer`、`_session_pool`、`_balancer_pool` | 中 | 无法测试、无法并行 |

### 缺陷 2 的详细机制（这是最需要立刻修的）

`glossary_manager.py` 用**相对导入** `from .config import ...`，
其余 40+ 处用**绝对导入** `from core.config import ...`，
`webui_gui.py` 又用 `from subtitle.core.glossary_manager import ...`。

Python 会把 `core.glossary_manager` 和 `subtitle.core.glossary_manager` 视为**两个不同模块**，
各创建一份 `glossary_manager` 单例、各建一份 `KeywordProcessor`（364 个词条的自动机，构造不便宜）。

于是 `webui_gui.py:44` 这行：

```python
glossary_manager.enable_discovery = False   # 声称"强制关闭保存权限"
```

只对**其中一份副本**生效。如果翻译主流程加载的是另一份，发现库的写权限根本没关掉——
这是**功能性 bug**，不只是风格问题。

### 缺陷 4 的详细机制

`orchestrator.py` 第 11 行只 import 了 `parse_srt`：

```python
from core.srt_utils import parse_srt          # ← 只有这个
```

但第 367、369 行在注释分支里调用了 `format_srt_block`：

```python
f.write(format_srt_block(i, block['timestamp'], text_content))   # NameError
```

结论：`--enable-annotations` 功能从未被真正跑通过。重构时顺手删掉或修好，别留着。

### 其他观察

- 死代码：`core/fewshot_manager.py`(128行)、`core/temperature_strategy.py`(163行)、`core/quality_checker.py`(172行) — 零引用
- `.backup_20260611_080725/` 整个旧 core 目录躺在源码树里
- `glossaries/` 下 5 个工具脚本混在 364 个语料 JSON 中间
- `translation.log`、`presets - 副本.json`、`.cache/*.srt` 在源码树里
- 16 处裸 `except:`，28 处 `print()` 混在业务逻辑
- 无 `pyproject.toml`、无 `requirements.lock`、零测试
- `presets.json` 所有值都是字符串（`"True"` / `"1"`），靠 `str(x).lower()=="true"` 到处转

---

## 二、重构总原则

1. **大爆炸（Big Bang）禁止。** 分四期，每期结束项目都能跑、能出片。
2. **先建网，后动刀。** 第 0 期只加测试和 .gitignore，不改一行业务代码。
3. **行为必须逐位一致。** 每期用第 0 期冻结的基线 SRT 做回归对比，输出差异必须为 0（除刻意修复的 bug）。
4. **不引入新框架。** 保持 stdlib + aiohttp + flashtext + json_repair + tkinter。
5. **可回退。** 每期一个 git tag，出问题 `git checkout` 即可。

---

## 三、第 0 期：建安全网（预计 0.5 天，零风险）

**这期的唯一目的是：让你在后面三期里敢改代码。**

### 动作清单

1. **初始化 git**（如果还没 init）
   ```bash
   git init
   # .gitignore 必须包含：
   #   __pycache__/  *.pyc  .cache/  translation.log
   #   python_embed/  .backup_*/  *with_annotations.srt
   #   "presets - 副本.json"  .venv/
   git add -A && git commit -m "baseline: 重构前快照"
   git tag v0-baseline
   ```

2. **冻结回归基线**（关键）
   找 2–3 个有代表性的真实 SRT（不同长度/语言方向），用当前代码跑出成品，存到 `tests/fixtures/baseline/`。
   同时存下 `.cache/*.json` 里的 `global_profile` / `scene_map` / 术语表——
   这样测试时不用反复调 LLM。

3. **写 20 个纯函数单测**（不需要网络、不需要 LLM，全部秒过）

   | 被测对象 | 测试点 |
   |---|---|
   | `srt_utils.parse_srt` | 正常解析、缺 index、CRLF、时间戳格式变体 |
   | `srt_utils.format_srt_block` | 输出格式、index 连续性 |
   | `cache_utils.canonical_json` | 键序稳定性、Unicode 保留 |
   | `cache_utils.build_file_cache_key` | 同内容改名 hash 不变、改内容必变 |
   | `rescue_engine._build_ladder` | n=1/2/8/15 的阶梯序列 |
   | `stages.polish_stage.postprocess_translation` | 标点清洗、数字保护（3.14 / 1,000） |
   | `post_checker.align_color_tags` | 有 tag / 无 tag 对齐 |
   | `glossary_manager._load_from_db` | 正反向映射、Slang 黑名单 |
   | `memory.scene_manager.build_scene_aligned_batches` | 批次不跨场景边界 |

   这些是纯函数，**现在就能写、就能跑**，不需要先重构。这是整个方案里性价比最高的一步。

4. **修 bug + 删杂物**（这些不需要重构就能做）
   - `orchestrator.py` 补 `format_srt_block` 导入
   - 删 `.backup_20260611_080725/`
   - 删 `translation.log`、`presets - 副本.json`、残留 `.cache/`
   - 移出 `glossaries/*.py`（5 个工具脚本）到 `tools/`
   - 把 `fewshot_manager.py` / `temperature_strategy.py` / `quality_checker.py` 移到 `attic/`（先别删，确认无用再删）

### 验收
```bash
pytest tests/ -v          # 全绿
python -m subtitle -i 有问题的字幕/xxx.srt   # 输出与 baseline 逐字一致
```

---

## 四、第 1 期：统一包结构（预计 1–2 天，收益最大）

**这期解决缺陷 1、2、3，是整个重构的核心。做完之后代码会"看起来像另一个项目"。**

### 1.1 建立真正的包

```
项目根/
├── pyproject.toml              # 新增，声明包元数据与依赖
├── src/
│   └── subtitle/               # 从 subtitle/ 整体平移过来
│       ├── __init__.py
│       ├── __main__.py         # python -m subtitle 入口
│       ├── cli.py              # 唯一 argparse 定义处
│       ├── paths.py            # 所有路径常量集中于此
│       ├── settings.py         # 配置体系
│       ├── domain/             # 纯业务，不依赖任何 IO 基建
│       ├── infra/              # 外部依赖：LLM / SQLite / SRT 文件
│       ├── app/                # 编排
│       └── ui/                 # GUI（可选，src 布局对 tkinter 不友好时放根）
├── tests/
├── tools/                      # 语料库维护脚本
└── prompts/                    # 提到包外，作为资源目录
```

`src/` 布局的好处：**Python 只会 import 你明确安装的包**，
`sys.path` 注入自动失效，从物理上杜绝"两个模块副本"。

### 1.2 导入规则（写进 CLAUDE.md / README）

```
✅ 永远用相对导入：from .config import Settings
✅ 跨包用相对：from ..infra.llm import LlmClient
❌ 禁止：import core.xxx
❌ 禁止：sys.path.insert / append
❌ 禁止：from subtitle.xxx  （在自己的包内）
```

### 1.3 合并四个入口为一个

现在的 `main.py` / `translate_srt_llm.py` / `gui_app.py` / `webui_gui.py` 收敛成：

```
src/subtitle/cli.py           # 唯一 argparse 定义处
src/subtitle/__main__.py      # python -m subtitle <命令>
```

子命令设计（比现在的"位置参数 + 隐式 GUI 兜底"清晰得多）：

```bash
python -m subtitle run input.mkv -o out.ass      # 完整流水线（取代 main.py）
python -m subtitle run input.srt --to-english     # 细粒度翻译
python -m subtitle gui                            # 桌面 GUI（取代 gui_app.py）
python -m subtitle prompt                         # WebUI 分步（取代 webui_gui.py）
python -m subtitle glossary build --feishu        # 语料库工具（从 tools/ 挪进来）
```

**关键改进**：`main.py` 现在只透传了 5 个参数给 `TranslationArgs`（bug 源头），
统一入口后所有参数都走同一条路。

### 1.4 拆掉 4 个门面层

现在的 `core/llm_client.py`、`core/request_handler.py`、`core/translation_pipeline.py`、
`core/global_memory.py` 全是 "Facade for backward compatibility"。

**重构后没有"向后兼容"的理由**——所有调用方都在同一个仓库里。直接删，
调用方改成 `from infra.llm import call_llm`（或相对导入）。

这一步能砍掉约 150 行纯转发代码，并且消除"到底该 import 哪个"的困惑。

### 1.5 media 桥接的规范化

`pre-process/01-extract_srt.py` 和 `post-process/02-post_process_ass.py` 目录名带连字符，
**根本不是合法 Python 模块名**，所以才被迫用 `importlib.util.spec_from_file_location` 动态加载
（在 `main.py` 和 `media/extractor.py` 里各重复了一遍）。

重命名：
```
pre-process/01-extract_srt.py     →  src/subtitle/infra/media/extract.py
post-process/02-post_process_ass.py →  src/subtitle/infra/media/ass_writer.py
post-process/asshead.txt          →  src/subtitle/infra/media/asshead.txt
```

改完就能正常 import，`load_module()` 这个 hack 彻底消失，`media/extractor.py` 里
重复的第二份桥接也一起删掉。

### 1.6 验收
```bash
grep -rn "sys.path" src/          # 零结果
grep -rn "^import core\.\|^from core\." src/   # 零结果
python -m subtitle run xxx.mkv -o out.ass      # 与 v0-baseline 逐字一致
```

---

## 五、第 2 期：消除隐式状态（预计 1 天）

### 2.1 路径集中到 `paths.py`

现在路径散落在 `config.py`（6 处）、`prompts.py`（1 处）、`main.py`（3 处）、
`media/extractor.py`（3 处）。全部搬到一个文件，并且**尊重环境变量**：

```python
# paths.py
import os
from pathlib import Path

def _root() -> Path:
    # 1. 环境变量优先（便携版用）
    if env := os.getenv("SUBTITLE_HOME"):
        return Path(env)
    # 2. 打包版：exe 同级
    # 3. 开发版：src/subtitle/../..
    return Path(__file__).resolve().parents[2]

ROOT = _root()
CACHE_DIR   = ROOT / ".cache"
GLOSSARY_DIR = ROOT / "glossaries"
PROMPTS_DIR  = ROOT / "prompts"
CONFIG_FILE  = ROOT / "presets.json"

def ensure_dirs() -> None:
    for d in (CACHE_DIR, GLOSSARY_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

`SUBTITLE_HOME` 这个环境变量同时解决便携版打包问题——现在 `python_embed` 的
TCL_LIBRARY hack 散在 `gui_app.py` 和 `webui_gui.py` 两处，迟早要出事。

### 2.2 `GlossaryManager` 从单例改为显式对象

```python
# 改前：core/glossary_manager.py 末尾
glossary_manager = GlossaryManager()      # 模块级单例，import 即产生

# 改后：无模块级实例
class GlossaryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._repo: GlossaryRepo | None = None
    def open(self) -> None: ...            # 显式初始化
    def close(self) -> None: ...           # 显式释放
```

调用方改成：
```python
# 改前
from core.glossary_manager import glossary_manager
glossary_manager.initialize(reverse=True)

# 改后
glossary = GlossaryService(settings)
glossary.open()
```

**这不只是洁癖问题。** 现在 `webui_gui.py` 强制 `enable_discovery = False` 的写法，
在双实例 bug 存在的情况下**并不可靠**。改成显式对象后，"这份配置影响哪一份实例"变成编译期确定的事。

### 2.3 会话池收进 `LlmClient` 实例

```python
# 改前：network/llm_client.py 模块级全局
_session_pool: Dict[str, AsyncRateLimitedSession] = {}
_balancer_pool: Dict[str, ...] = {}

# 改后
class LlmClient:
    def __init__(self, settings: Settings):
        self._sessions: dict[str, AsyncRateLimitedSession] = {}
        self._balancers: dict[str, SmartLoadBalancer] = {}

    async def __aenter__(self): ...
    async def __aexit__(self, *exc):
        for s in self._sessions.values():
            await s.__aexit__(*exc)
        self._sessions.clear()
```

顺带修一个真 bug：`get_load_balancer_stats()` 用
`md5(api_key + api_url + "True")` 算 key，但 `get_session()` 用的是
`md5(','.join(api_keys) + api_url + use_smart_balancer)`。**两个 key 算法不一致**，
多 Key 场景下统计永远拿不到。改成实例内直接访问即可根治。

### 2.4 `SafetyFuzzer` 同理

`safety_fuzzer` 也是模块级单例，且持有全量字幕块。同上处理。

### 2.5 异常分层

定义三个明确的异常类型，替代满屏的裸 `except:`：

```python
class SubtitleError(Exception): ...
class TransientLLMError(SubtitleError): ...      # 429 / 超时 → 值得重试
class PermanentLLMError(SubtitleError): ...      # 400 / 鉴权失败 → 别重试
class ContentRefused(SubtitleError): ...         # 替代哨兵对象 REFUSAL_SENTINEL
```

**`REFUSAL_SENTINEL` 这个设计要一并改掉。** 现在的做法是：

```python
raw = await call_llm(..., raise_on_refusal=True)
if raw is REFUSAL_SENTINEL:      # 用一个 object() 冒充返回值
    return ("__REFUSAL__", expected_ids)   # 再用元组首元素传字符串
```

返回值类型在 `Optional[str]` / `object` / `Tuple[str, Set[int]]` 之间来回变，
调用方必须用 `is` 比较才能分支。改成直接 `raise ContentRefused()` 后，
控制流交给异常机制，`rescue_engine` 的 `isinstance(res, tuple) and res[0] == "__REFUSAL__"`
这段可以删掉，`_do_single_request` 也能从"返回元组或 None 或列表"三态变成"返回列表或抛异常"两态。

### 2.6 验收
```bash
grep -rn "sys.path" src/ ; grep -rn "= GlossaryManager()\|= SafetyFuzzer()\|= object()" src/
grep -rn "except:" src/     # 零结果
```
新写一个测试：在同一进程内用两个不同 `GlossaryService` 实例跑不同方向的术语提取，验证互不干扰。

---

## 六、第 3 期：收敛配置与编排（预计 1–1.5 天）

### 3.1 Settings 单一来源

现状的数据流是这样的（同一个配置被搬了三遍）：

```
presets.json (全字符串)
   ↓ TranslationConfig.__post_init__  逐字段 str().lower()=="true" 转换
TranslationConfig  (30+ 字段 dataclass)
   ↓ TranslationArgs.__init__  25 行 self.x = config.x 手工搬运
TranslationArgs    (30+ 字段普通类)
   ↓ orchestrator 20 行 getattr(args,'x', default) 往回搬
TranslationConfig  (重建)
```

**三处搬运，任何漏一处就是静默的行为差异。** 重构后只剩一层：

```python
# settings.py
@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    model_name: str
    target_lang: Literal["zh", "en"] = "zh"
    batch_size: int = 8
    max_concurrent: int = 4
    rpm_limit: int = 60
    tpm_limit: int = 100_000
    temp_terms: float = 0.1
    temp_literal: float = 0.3
    temp_polish: float = 0.5
    reasoning_effort: str = ""
    # ... 其余字段

    @classmethod
    def from_presets(cls, path: Path, name: str | None = None) -> "Settings":
        """唯一的解析入口。所有类型转换集中在这里，一次性、严格。"""

    @classmethod
    def for_preset(cls, name: str) -> "Settings":
        """供 ASR 净化 / 终审 / 术语提取等子任务派生临时变体。"""
```

三个改进点：

1. **`frozen=True`** — 配置不可变，杜绝 `scrub_config = TranslationConfig(); scrub_config.api_key = p['api_key']`
   这种"复制一份再改几个字段"的模式（`orchestrator.py:180-185`、`post_checker.py:133-138` 各有一处）。
2. **转换集中且严格**。`presets.json` 里的 `"True"` / `"1"` 在 `from_presets` 里用
   `_as_bool()` 统一处理一次，而不是散落在 8 个 `str(...).lower() == "true"` 里。
   写一个 `tests/test_settings.py` 专门测各种脏输入（`"True"` / `"true"` / `"1"` / `"yes"` / `1`）。
3. **CLI 与 GUI 走同一构造路径**。现在 `translate_srt_llm.py` 有一份 argparse 默认值来自
   `TranslationConfig()`，`gui/preset_manager.py` 又有一份保存逻辑。统一后只剩 `Settings.from_presets()`。

### 3.2 拆开 `orchestrator.py`（384 行 → 5 个阶段函数）

现在的 `run_translation()` 是一个 300 行的函数，做了 9 件事：解析配置、加载语料库、
建画像、建场景、抽术语、建策略、ASR 净化、分批翻译+预取、写检查点、终审、生成注释。

拆成显式的阶段对象，每阶段一个函数，共享一个 `RunContext`：

```python
# app/run.py
@dataclass
class RunContext:
    settings: Settings
    input_path: Path
    output_path: Path
    blocks: list[SubtitleBlock]
    glossary: GlossaryService
    llm: LlmClient
    progress: ProgressTracker
    events: EventBus              # 替代散落的 progress_callback

async def run(ctx: RunContext) -> None:
    await stage_prepare(ctx)      # 载入 + 缓存检查
    await stage_memory(ctx)       # global_profile + scene_map + policy
    await stage_terms(ctx)        # 术语表（含三级库回填）
    await stage_translate(ctx)    # 分批 + 预取，唯一涉及复杂并发的部分
    await stage_finalize(ctx)     # 终审 + 注释 + 输出
```

顺带解决 `run_translation()` 里的两个具体问题：

**(a) 预取任务泄漏风险**。现在 `next_literal_task` 在 `finally` 里被 cancel，
但如果循环里抛异常、`next_literal_task` 还没被赋值……实际上第 228 行先初始化了，
还算安全。但 `process_literal_stage` 的预取参数有明显 bug：

```python
# orchestrator.py:288-296 — 预取下一批时
current_profile_str=current_profile_str,      # ← 传的是"当前批次"的场景画像
scene_guidance=scene_guidance_str,             # ← 传的是"当前批次"的场景引导
```

下一批属于**另一个场景**，却注入的是当前场景的参与者和引导。这会污染译文。
修法：预取任务只带不依赖场景的部分（`core_glossary` / `recent_state` / `future_context`），
`global_profile` 和 `scene_guidance` 留到真正处理该批时再算。
这也正好简化了代码——不需要提前算。

**(b) 双语模式的 index 假设**。`self_enforce_consistency()` 里假设双语输出时
"第 2i 条是原文、第 2i+1 条是译文"：

```python
for i in range(0, len(final_blocks), 2):
    paired = {'index': final_blocks[i]['index'], ...'content': final_blocks[i+1]['content']}
```

这和 `checkpoint_manager.save_checkpoint()` 里的写出顺序强耦合。
一旦写盘顺序改了，质检就会**静默地把译文当原文送去审校**——不报错，只是质量下降。
建议：`SubtitleBlock` 数据结构里直接带 `original` / `literal` / `polished` 三个字段，
落盘时才决定输出哪些。不要用"位置约定"传递语义。

### 3.3 统一日志

28 处 `print()` 换成 `logging`。GUI 需要的地方用 `EventBus` 转发到 tkinter 队列
（tkinter 不是线程安全的，从 worker 线程直接改控件会随机崩）。

### 3.4 补 `pyproject.toml`

```toml
[project]
name = "subtitle-pipeline"
requires-python = ">=3.10"
dependencies = ["aiohttp", "flashtext", "json-repair", "tqdm", "pyperclip"]

[project.scripts]
subtitle = "subtitle.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

装上之后 `subtitle` 直接是全局命令，不用再依赖 .bat 脚本里的路径魔法。

### 3.5 验收
```bash
pytest tests/ -v                                    # 全绿
# 逐位回归
python -m subtitle run fixture.mkv -o new.ass
diff <(sed 's/[0-9]//g' baseline.ass) <(sed 's/[0-9]//g' new.ass)   # 忽略时间码
```

---

## 七、时间线与风险

| 期次 | 内容 | 工作量 | 风险 | 可回退点 |
|---|---|---|---|---|
| 0 | 安全网 + 修 bug + 删杂物 | 0.5 天 | 无 | `v0-baseline` |
| 1 | 统一包结构 + 单入口 | 1.5 天 | 中（改 import） | `v1-package` |
| 2 | 消除隐式状态 | 1 天 | 中（改签名） | `v2-stateless` |
| 3 | Settings + 拆编排 | 1.5 天 | 中高（动核心流程） | `v3-config` |
| — | 可选：WebUI 现代化 | 1 天+ | — | — |

**总计约 4.5 天**，不含测试补充和文档更新。

### 最大的三个风险

1. **没有回归基线就动手（第 0 期被跳过）** → 一旦改坏无法察觉。
   缓解：第 0 期的 20 个单测 + 冻结 SRT 是硬前置条件，不可跳过。

2. **第 1 期的 import 迁移漏改一处** → 运行时报 `ImportError`（好）或者
   更糟：某处走了不同的 import 路径导致双实例（坏，静默）。
   缓解：迁移后立刻跑 `grep -rn "from core\.\|import core\."` 确认零残留，
   并跑一次真实 SRT 验证。

3. **第 3 期动了预取逻辑** → 可能引入翻译质量变化。
   缓解：预取参数修正单独一次提交，方便单独回退和单独评估效果。

### 不建议做的事

- ❌ **别在同期重写 prompt**。19 个 prompt 模板是调优过的资产，
  重构和调优混在一起，出问题无法归因。
- ❌ **别引入新框架**（Pydantic / 依赖注入框架 / 插件系统）。
  这个项目的复杂度用 dataclass + 显式传参完全够，引入框架只会增加依赖负担。
- ❌ **别一次性重命名所有东西**。保持目录名和函数名稳定，
  只在必要处改名，减少 diff 噪音。

---

## 八、建议的执行顺序

我会这样开始：

1. **今天先做第 0 期**（0.5 天）——特别是那 20 个单测，
   它们会让你后面三期的每一步都有反馈。
2. 先跑一次完整的真实 SRT 翻译，冻结 baseline。
3. 再进第 1 期。

如果你想更快看到效果，也可以先做第 0 期的"修 bug + 删杂物 + .gitignore"（1 小时内完成），
然后直接跳到第 1 期——第 1 期结束后代码结构会清晰很多，
但仍然建议在第 1 期之前把那 20 个单测补上。
