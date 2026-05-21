# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib
import logging
import re
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from flashtext import KeywordProcessor

# 导入配置和底层组件
from .config import GLOSSARY_DIR, GLOSSARY_DB_PATH, LLM_DISCOVERY_DB_PATH, LLM_DISCOVERY_CN_DB_PATH, NAMES_DB_PATH, TranslationConfig
from .llm_client import call_llm, clean_and_extract_json
from .prompts import get_prompt_templates

logger = logging.getLogger(__name__)

class GlossaryManager:
    def __init__(self):
        self.glossary_dir = Path(GLOSSARY_DIR)
        self.db_path = GLOSSARY_DB_PATH
        self.names_db_path = NAMES_DB_PATH
        self.discovery_db_path = LLM_DISCOVERY_DB_PATH
        config = TranslationConfig()
        self.enable_discovery = config.enable_llm_discovery
        self.enable_names_db = config.enable_names_db
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping: Dict[str, str] = {}
        self.full_term_data = {}
        self._initialized = False

    def initialize(self, reverse=False):
        """初始化：建表、增量更新、加载内存"""
        if reverse:
            self.discovery_db_path = LLM_DISCOVERY_CN_DB_PATH
        else:
            self.discovery_db_path = LLM_DISCOVERY_DB_PATH

        self._init_db(self.db_path)
        if self.enable_discovery:
            self._init_db(self.discovery_db_path)
        
        self.incremental_update()
        self._load_to_memory(reverse=reverse)
        self._initialized = True
        mode = "中->英 (反向)" if reverse else "英->中 (正向)"
        print(f"✅ 语料库初始化完毕 [{mode}]: 内存中包含 {len(self.term_mapping)} 个术语")

    def _init_db(self, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS terms (
                source_term TEXT PRIMARY KEY,
                target_term TEXT,
                category TEXT,
                description TEXT,
                instruction TEXT,
                source_file TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("PRAGMA table_info(terms)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'description' not in columns:
            cursor.execute("ALTER TABLE terms ADD COLUMN description TEXT")
        if 'instruction' not in columns:
            cursor.execute("ALTER TABLE terms ADD COLUMN instruction TEXT")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_hashes (
                filename TEXT PRIMARY KEY,
                file_hash TEXT,
                processed_at TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def _calculate_file_hash(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def incremental_update(self) -> int:
        scan_dirs = [self.glossary_dir, Path(self.glossary_dir).parent.parent / "online_db_api" / "glossary"]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, file_hash FROM file_hashes")
        processed_files = dict(cursor.fetchall())
        updated_count = 0
        for s_dir in scan_dirs:
            if not s_dir.exists(): continue
            for file_path in s_dir.rglob("*.json"):
                filename = str(file_path.absolute())
                current_hash = self._calculate_file_hash(file_path)
                if filename not in processed_files or processed_files[filename] != current_hash:
                    try:
                        self._process_single_file(file_path, cursor)
                        cursor.execute('INSERT OR REPLACE INTO file_hashes VALUES (?, ?, CURRENT_TIMESTAMP)', (filename, current_hash))
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"处理语料文件 {filename} 失败: {e}")
        conn.commit()
        conn.close()
        return updated_count

    def _process_single_file(self, file_path: Path, cursor: sqlite3.Cursor):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list): return
        for item in data:
            source = item.get('source_term', '').strip()
            target = item.get('target_term', '').strip()
            if source and target:
                cursor.execute('''
                    INSERT OR REPLACE INTO terms (source_term, target_term, category, description, instruction, source_file, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (source, target, item.get('category', 'General'), item.get('description', '').strip(), item.get('instruction', '').strip(), file_path.name))

    def _load_to_memory(self, reverse=False):
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.term_mapping = {}
        self.full_term_data = {}
        if self.enable_discovery:
            self._load_from_db(self.discovery_db_path, reverse=reverse)
        self._load_from_db(self.db_path, reverse=reverse)

    def _load_from_db(self, db_path, reverse=False):
        if not Path(db_path).exists(): return
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT source_term, target_term, category, description, instruction FROM terms")
        rows = cursor.fetchall()
        REVERSE_BLACKLIST = {"Idioms/Colloquialisms", "Slang"}
        for source, target, category, description, instruction in rows:
            source = source.strip() if source else ""
            target = target.strip() if target else ""
            if not source or not target: continue
            term_info = {"source": source, "target": target, "category": category, "description": description, "instruction": instruction}
            if reverse:
                if category in REVERSE_BLACKLIST: continue
                clean_target = target.replace('，', ',')
                possible_keys = [t.strip() for t in clean_target.split(',')]
                for key in possible_keys:
                    if key:
                        self.keyword_processor.add_keyword(key, key)
                        self.term_mapping[key] = source
                        self.full_term_data[key] = term_info
            else:
                self.keyword_processor.add_keyword(source, source)
                self.term_mapping[source] = target
                self.full_term_data[source] = term_info
        conn.close()

    def extract_terms(self, text: str) -> Dict[str, dict]:
        found_sources = self.keyword_processor.extract_keywords(text)
        result = {}
        for source in set(found_sources):
            if source in self.full_term_data:
                result[source] = self.full_term_data[source]
        return result

    def save_terms(self, terms_dict: Dict[str, str], category: str = "LLM_Discovered"):
        if not terms_dict: return
        
        new_items = []
        for source, target in terms_dict.items():
            s_c, t_c = source.strip(), target.strip()
            if s_c and t_c and s_c not in self.term_mapping:
                # 更新内存
                self.keyword_processor.add_keyword(s_c, s_c)
                self.term_mapping[s_c] = t_c
                self.full_term_data[s_c] = {"source": s_c, "target": t_c, "category": category, "description": "", "instruction": ""}
                new_items.append((s_c, t_c, category))

        # 持久化到数据库
        if self.enable_discovery and new_items:
            try:
                conn = sqlite3.connect(self.discovery_db_path)
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT OR IGNORE INTO terms (source_term, target_term, category, description, instruction, source_file, updated_at)
                    VALUES (?, ?, ?, '', '', 'LLM_Auto_Discovery', CURRENT_TIMESTAMP)
                ''', new_items)
                conn.commit()
                conn.close()
                logger.info(f"成功将 {len(new_items)} 个新术语保存到发现库")
            except Exception as e:
                logger.error(f"持久化新术语失败: {e}")

    async def fetch_names_with_llm(self, text: str, config: TranslationConfig) -> Dict[str, str]:
        """【统一入口】使用 LLM 识别文本中的人名，并自动从人名库匹配译名"""
        if not text.strip(): return {}
        templates = get_prompt_templates(config.target_lang)
        ner_msgs = [{"role": "user", "content": templates["NER_NAMES"].format(content=text)}]
        ner_config = type(config)(**vars(config))
        ner_config.model_name = config.ner_model_name
        ner_config.api_key = config.ner_api_key
        ner_config.api_url = config.ner_api_url
        try:
            raw_res = await call_llm(ner_config, ner_msgs, temperature=0.0, response_format={"type": "json_object"})
            print(f"\nDEBUG [NER Raw]: {raw_res}") 
            data = clean_and_extract_json(raw_res)
            print(f"DEBUG [NER Parsed]: {data}")
            
            extracted_names = []
            if isinstance(data, dict):
                extracted_names = data.get("names", [])
                if not extracted_names and not data:
                    # 如果返回的是空字典，尝试看是否直接把名字列在了根级
                    extracted_names = data.get("person_names", [])
            elif isinstance(data, list):
                extracted_names = data
            
            if not isinstance(extracted_names, list):
                extracted_names = []
                
            if not extracted_names: return {}
            return self.search_names("", known_names=extracted_names)
        except Exception as e:
            logger.error(f"LLM 辅助人名识别失败: {e}")
            return {}

    def search_names(self, text: str, exclude_list: List[str] = None, known_names: List[str] = None) -> Dict[str, str]:
        """从文本中提取人名并在库中查询。如果提供了 known_names，则直接使用已知名单。"""
        if not self.enable_names_db or not Path(self.names_db_path).exists(): return {}
        
        # 准备最终的排除名单：外部传入的 + 内存中已有的主库词条
        final_excludes = set()
        if exclude_list:
            final_excludes.update(exclude_list)
        # 强制排除内存中已有的所有主库词条（以主库为准）
        final_excludes.update(self.term_mapping.keys())
            
        final_candidates = set()
        if known_names:
            for name in known_names:
                # 如果这个名字（或其全名）已经在主库里了，直接跳过人名库查询
                if name in final_excludes: continue
                
                parts = re.findall(r'\b\w+\b', name)
                for p in parts:
                    if len(p) > 2 and p not in final_excludes: 
                        final_candidates.add(p)
                final_candidates.add(name)
        else:
            # 回退到原来的启发式逻辑
            all_words = re.findall(r'\b\w+\b', text)
            # ... (保持原有逻辑，但使用 final_excludes)
            lower_words_set = {w.lower() for w in all_words if w.islower()}
            name_pairs = re.findall(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b', text)
            pair_candidates = {p[0] for p in name_pairs} | {p[1] for p in name_pairs}
            all_candidates = set(re.findall(r'\b[A-Z][a-z]{2,}\b', text))
            STOP_WORDS = {"The", "This", "That", "There", "Here", "When", "Where", "Which", "While", "Who", "Whom", "And", "But", "For", "With", "From", "About", "Against", "After", "Before", "Into", "During", "Has", "Have", "Had", "Does", "Did", "Was", "Were", "Are", "Been", "Being", "They", "Them", "Their", "Our", "Your", "She", "Her", "His", "Its", "You", "All", "Any", "Each", "Every", "Some", "Well", "Just", "Even", "Still", "Only", "Also", "Very", "Really", "Please", "Now", "Then", "One", "Two", "Three", "Four", "Five", "First", "Last", "Next", "Many", "More", "Most", "Other", "Such", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "China", "Russia", "Britain", "England", "America", "Ukraine", "Poland", "Germany", "Holland", "Belgium", "France", "Europe"}
            
            for word in all_candidates:
                if word in final_excludes or word in STOP_WORDS: continue
                if word.lower() in lower_words_set and word not in pair_candidates: continue
                final_candidates.add(word)
        if not final_candidates: return {}
        found_names = {}
        try:
            conn = sqlite3.connect(self.names_db_path)
            cursor = conn.cursor()
            query_list = list(final_candidates)
            placeholders = ', '.join(['?'] * len(query_list))
            query = f"SELECT 源语言, 中文译名, 国家 FROM names WHERE 源语言 IN ({placeholders}) COLLATE NOCASE"
            cursor.execute(query, query_list)
            for source, target, country in cursor.fetchall():
                if "威妥玛" in country or "音节" in country:
                    if len(source) <= 3: continue 
                if len(target.split(',')) > 5 and (not known_names or source not in known_names): continue
                found_names[source] = target
            conn.close()
        except Exception as e:
            logger.error(f"查询人名库失败: {e}")
        return found_names

glossary_manager = GlossaryManager()
