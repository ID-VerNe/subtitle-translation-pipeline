# -*- coding: utf-8 -*-
"""
同步飞书 SOP《4-2 特殊专有名词翻译和注释》到本地语料库。

流程：
1. 解析飞书导出的 Markdown（5 列或 4 列表格）
2. 取译优先级：我组自用译名 > 我组出版用译名 > 其他常见译名
   - "保留不译" → target_term 直接用英文原名，备注写入 description
   - 三列全空（或仅有背景）的行 → 跳过，但旧库中的对应条目会被清理
3. 直接修改 JSON（source_term 忽略大小写匹配）：
   - 已有条目：若译名/分类/备注有变化则原地更新，无变化则不动
   - 新条目：按章节写入新的数字编号 JSON 文件
4. 全量重建 glossary_cache.db（清空 terms + file_hashes 后按 glossary_manager
   的相同逻辑重新导入），保证 DB 与 JSON 严格一致。

用法:
    python sync_feishu_sop.py [markdown_path]
默认 markdown 路径: .workbuddy/tmp/corpus_doc.md（由 lark-cli 拉取）
"""
import json
import os
import re
import sqlite3
import sys
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # subtitle pipeline source/
GLOSSARIES_DIR = PROJECT_ROOT / "subtitle" / "glossaries"
DB_PATH = PROJECT_ROOT / "subtitle" / "glossary_cache.db"
DEFAULT_MD = PROJECT_ROOT / ".workbuddy" / "tmp" / "corpus_doc.md"

CATEGORY_MAP = {
    "常规名词标准翻译": "常规术语",
    "常见人物": "常见人物",
    "Top Gear & The Grand Tour": "Top Gear & The Grand Tour",
    "哈蒙德的修车房、哈蒙德酒水": "哈蒙德系列",
    "克拉克森的农场": "克拉克森的农场",
    "James Gin": "James Gin",
    "其他节目": "其他节目",
}

# SOP 原文中的笔误修正（修正后才能匹配真实字幕中的拼写）
TYPO_FIX = {
    "Bughatti Veyron": "Bugatti Veyron",
    "Trimuph": "Triumph",
    "gentlemen's sasuge": "gentlemen's sausage",
    "Jaekoo": "Jaecoo",
}

# SOP 表格中译名误填进"背景"列的特殊行
SPECIAL_TARGET = {
    "Volkswagen T-Roc": "大众探歌",
}

# 4 列表（无背景列）的章节
FOUR_COL_SECTIONS = {"James Gin", "其他节目"}


def clean_cell(text):
    text = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\\([.!()\\-])", r"\1", text)
    return text.strip()


def parse_tables(md_path):
    """返回 [(section_title, rows), ...]，row 为 dict"""
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    headings = [(i, l.strip().lstrip("# ").strip()) for i, l in enumerate(lines) if l.startswith("### ")]
    parts = []
    for idx, (start, title) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        rows, header_passed = [], False
        for line in lines[start:end]:
            s = line.strip()
            if not s.startswith("|"):
                header_passed = False if not s else header_passed
                continue
            if re.fullmatch(r"\|[-\s|:]+\|?", s):
                # 表头分隔行（兼容 |-|-|-| 与 |---|---| 两种风格）
                header_passed = True
                continue
            if not header_passed:
                continue
            cols = [clean_cell(c) for c in s.split("|")]
            if cols and cols[0] == "":
                cols = cols[1:]
            if cols and cols[-1] == "":
                cols = cols[:-1]
            if len(cols) < 3 or cols[0] in ("", "专有名词"):
                continue
            if title in FOUR_COL_SECTIONS:
                background, own, publish, common = "", cols[1], cols[2], cols[3] if len(cols) > 3 else ""
            else:
                background, own, publish = cols[1], cols[2], cols[3] if len(cols) > 3 else ""
                common = cols[4] if len(cols) > 4 else ""
            source = TYPO_FIX.get(cols[0], cols[0])
            rows.append({
                "source_term": source,
                "background": background,
                "own": own, "publish": publish, "common": common,
            })
        if rows:
            parts.append((title, rows))
    return parts


def pick_translation(row):
    """按优先级选译名，返回 (target, keep_untranslated)。无可用译名返回 (None, False)"""
    if row["source_term"] in SPECIAL_TARGET:
        return SPECIAL_TARGET[row["source_term"]], False
    for cand in (row["own"], row["publish"], row["common"]):
        if not cand:
            continue
        m = re.match(r"^(.*)（保留不译）$", cand)
        if cand == "保留不译":
            return row["source_term"], True
        if m and m.group(1).strip() == row["source_term"]:
            return row["source_term"], True
        return cand, False
    return None, False


def build_description(row, keep_untranslated):
    notes = []
    if keep_untranslated:
        notes.append("SOP 规定保留不译")
    if row["background"] and row["background"] != chosen:
        notes.append(row["background"])
    chosen = pick_translation(row)[0]
    if row["publish"] and row["publish"] != chosen:
        notes.append(f"出版用译名：{row['publish']}")
    if row["common"] and row["common"] != chosen:
        notes.append(f"其他常见译名：{row['common']}")
    return "；".join(notes)


def load_existing_index():
    """返回 {lower_source: [{'filepath', 'entry', 'idx'}, ...]}，索引所有 *.json"""
    index = {}
    for fpath in sorted(GLOSSARIES_DIR.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [警告] 无法读取 {fpath.name}: {e}")
            continue
        if not isinstance(data, list):
            continue
        for i, item in enumerate(data):
            src = str(item.get("source_term", "")).strip().lower()
            if src:
                index.setdefault(src, []).append({"filepath": fpath, "entry": item, "idx": i})
    return index


def sync_jsons(parts):
    """原地更新已有条目；新条目按章节写入新编号文件。返回统计 dict"""
    index = load_existing_index()
    stats = {"updated": [], "unchanged": 0, "removed": 0, "new": 0, "skipped_no_target": []}
    files_touched = {}  # filepath -> data(list) 缓存

    def get_file(fp):
        if fp not in files_touched:
            files_touched[fp] = json.loads(fp.read_text(encoding="utf-8"))
        return files_touched[fp]

    # 第一步：删除所有将被同步覆盖的旧条目（新表为准）
    covered = set()
    for title, rows in parts:
        for row in rows:
            covered.add(row["source_term"].strip().lower())
    to_remove = {}  # filepath -> set(idx)
    for src in covered:
        for ref in index.get(src, []):
            to_remove.setdefault(ref["filepath"], set()).add(ref["idx"])
    for fp, idxs in to_remove.items():
        data = get_file(fp)
        stats["removed"] += len(idxs & set(range(len(data))))
        files_touched[fp] = [e for i, e in enumerate(data) if i not in idxs]

    # 第二步：写回被修改的文件（空文件删除）
    for fp, data in files_touched.items():
        if data:
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        else:
            fp.unlink()
            print(f"  [清理] {fp.name} 已空，删除")

    # 第三步：新条目按章节写入新编号文件
    def next_number():
        nums = [int(p.stem) for p in GLOSSARIES_DIR.glob("*.json") if p.stem.isdigit()]
        return max(nums) + 1 if nums else 1

    num = next_number()
    written_files = []
    for title, rows in parts:
        category = CATEGORY_MAP.get(title, title)
        entries = []
        for row in rows:
            target, keep = pick_translation(row)
            if not target:
                stats["skipped_no_target"].append(f"{row['source_term']}({title})")
                continue
            entry = {
                "source_term": row["source_term"],
                "target_term": target,
                "category": category,
                "description": build_description(row, keep),
            }
            entries.append(entry)
            stats["new"] += 1
        if entries:
            fname = f"{num}.json"
            (GLOSSARIES_DIR / fname).write_text(
                json.dumps(entries, ensure_ascii=False, indent=4), encoding="utf-8")
            print(f"  [新增] {fname}: {len(entries)} 条（{category}）")
            written_files.append(fname)
            num += 1
    return stats


def rebuild_db():
    """全量重建 glossary_cache.db（与 core/glossary_manager.py 逻辑一致）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS terms (
        source_term TEXT PRIMARY KEY, target_term TEXT, category TEXT,
        description TEXT, instruction TEXT, source_file TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cols = [c[1] for c in cur.execute("PRAGMA table_info(terms)").fetchall()]
    if "description" not in cols:
        cur.execute("ALTER TABLE terms ADD COLUMN description TEXT")
    if "instruction" not in cols:
        cur.execute("ALTER TABLE terms ADD COLUMN instruction TEXT")
    cur.execute("""CREATE TABLE IF NOT EXISTS file_hashes (
        filename TEXT PRIMARY KEY, file_hash TEXT, processed_at TIMESTAMP)""")

    cur.execute("DELETE FROM terms")
    cur.execute("DELETE FROM file_hashes")
    n_files, n_terms = 0, 0
    for fpath in sorted(GLOSSARIES_DIR.rglob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [错误] 解析 {fpath} 失败: {e}")
            continue
        if not isinstance(data, list):
            continue
        h = hashlib.md5(fpath.read_bytes()).hexdigest()
        for item in data:
            source = str(item.get("source_term", "")).strip()
            target = str(item.get("target_term", "")).strip()
            if not source or not target:
                continue
            cur.execute("""INSERT OR REPLACE INTO terms
                (source_term, target_term, category, description, instruction, source_file, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (source, target, item.get("category", "General"),
                 item.get("description", "").strip(), item.get("instruction", "").strip(),
                 fpath.name))
            n_terms += 1
        cur.execute("INSERT OR REPLACE INTO file_hashes VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (str(fpath.absolute()), h))
        n_files += 1
    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM terms").fetchone()[0]
    conn.close()
    print(f"  [DB] 重建完成: {n_files} 个文件, 导入 {n_terms} 条, 表内总计 {total} 条")


def main():
    md_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    print(f"[1/3] 解析 {md_path}")
    parts = parse_tables(md_path)
    for title, rows in parts:
        print(f"  章节《{title}》: {len(rows)} 行")
    print("[2/3] 同步 JSON ...")
    stats = sync_jsons(parts)
    print(f"  新增 {stats['new']} 条 | 原地清理旧条目 {stats['removed']} 条 | "
          f"无译名跳过 {len(stats['skipped_no_target'])} 条")
    if stats["skipped_no_target"]:
        print("  跳过: " + ", ".join(stats["skipped_no_target"]))
    print("[3/3] 重建 glossary_cache.db ...")
    rebuild_db()
    print("完成！")


if __name__ == "__main__":
    main()
