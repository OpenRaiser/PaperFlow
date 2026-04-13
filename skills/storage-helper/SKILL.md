# Storage Helper Skill

## 职责

数据存取：读写 SQLite 数据库，管理用户画像、论文缓存、行为日志。

## 数据库表结构

### profiles 表

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    profile_json TEXT NOT NULL,
    version TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### papers 表

```sql
CREATE TABLE papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arxiv_id TEXT UNIQUE,
    doi TEXT,
    title TEXT NOT NULL,
    authors TEXT,
    institution TEXT,
    abstract TEXT,
    venue TEXT,
    publish_date DATE,
    embedding BLOB,
    embedding_model TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pushed BOOLEAN DEFAULT FALSE,
    push_date DATE
);

CREATE INDEX idx_papers_arxiv ON papers(arxiv_id);
CREATE INDEX idx_papers_doi ON papers(doi);
CREATE INDEX idx_papers_pushed ON papers(pushed) WHERE pushed = FALSE;
```

### behavior_logs 表

```sql
CREATE TABLE behavior_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    push_id TEXT NOT NULL,
    paper_id INTEGER,
    action TEXT NOT NULL,
    action_type TEXT NOT NULL,
    category TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);

CREATE INDEX idx_behavior_user ON behavior_logs(user_id);
CREATE INDEX idx_behavior_push ON behavior_logs(push_id);
CREATE INDEX idx_behavior_timestamp ON behavior_logs(timestamp);
```

### task_status 表

```sql
CREATE TABLE task_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    task_type TEXT NOT NULL,
    user_id TEXT,
    status TEXT NOT NULL,
    progress_json TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

## API

### 用户画像操作

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `create_profile(user_id, profile_json)` | user_id, profile_json | profile_id | 创建新用户画像 |
| `get_profile(user_id)` | user_id | profile_json | 获取用户画像 |
| `update_profile(user_id, profile_json)` | user_id, profile_json | success | 更新用户画像 |
| `get_profile_history(user_id, days)` | user_id, days | list | 获取历史画像（用于周报对比） |

### 论文操作

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `add_paper(paper_data)` | paper_data dict | paper_id | 添加论文 |
| `add_papers_batch(papers_list)` | papers list | count | 批量添加论文 |
| `get_paper_by_arxiv(arxiv_id)` | arxiv_id | paper | 根据 arxiv_id 查询 |
| `get_paper_by_doi(doi)` | doi | paper | 根据 doi 查询 |
| `get_unpushed_papers(limit)` | limit | list | 获取未推送的论文 |
| `mark_pushed(paper_ids)` | paper_ids list | count | 标记已推送 |

### 行为日志操作

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `log_behavior(user_id, push_id, paper_id, action, action_type, category, metadata)` | 各字段 | log_id | 记录行为日志 |
| `get_behavior_logs(user_id, start_date, end_date)` | user_id, dates | list | 获取指定时间段的行为日志 |
| `get_selection_stats(user_id, days)` | user_id, days | stats dict | 获取选择统计 |

### 任务状态操作

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `create_task(task_id, task_type, user_id)` | 各字段 | task_id | 创建任务记录 |
| `update_task_status(task_id, status, progress_json)` | 各字段 | success | 更新任务状态 |
| `get_task(task_id)` | task_id | task | 获取任务状态 |
| `get_user_tasks(user_id, days)` | user_id, days | list | 获取用户任务历史 |

## 脚本实现 (scripts/db_ops.py)

```python
#!/usr/bin/env python3
"""
SciTaste Database Operations
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "scitaste.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库，创建所有表"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 创建 profiles 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            profile_json TEXT NOT NULL,
            version TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 papers 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT UNIQUE,
            doi TEXT,
            title TEXT NOT NULL,
            authors TEXT,
            institution TEXT,
            abstract TEXT,
            venue TEXT,
            publish_date DATE,
            embedding BLOB,
            embedding_model TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pushed BOOLEAN DEFAULT FALSE,
            push_date DATE
        )
    """)
    
    # 创建 behavior_logs 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS behavior_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            push_id TEXT NOT NULL,
            paper_id INTEGER,
            action TEXT NOT NULL,
            action_type TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)
    
    # 创建 task_status 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            task_type TEXT NOT NULL,
            user_id TEXT,
            status TEXT NOT NULL,
            progress_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def create_profile(user_id, profile_json):
    """创建新用户画像"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO profiles (user_id, profile_json, version)
        VALUES (?, ?, ?)
    """, (user_id, json.dumps(profile_json), profile_json.get("version", "0.1")))
    conn.commit()
    profile_id = cursor.lastrowid
    conn.close()
    return profile_id

def get_profile(user_id):
    """获取用户画像"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT profile_json FROM profiles WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["profile_json"])
    return None

def update_profile(user_id, profile_json):
    """更新用户画像"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE profiles 
        SET profile_json = ?, version = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (json.dumps(profile_json), profile_json.get("version", "0.1"), user_id))
    conn.commit()
    conn.close()
    return True

# ... 其他函数实现

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
```

## 注意事项

1. **事务处理**：批量操作使用事务保证原子性
2. **索引优化**：常用查询字段建立索引
3. **数据备份**：每日自动备份数据库
4. **连接管理**：使用连接池避免频繁创建连接
