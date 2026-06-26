"""
医学知识库 - 数据库模块
SQLite + FTS5 全文索引初始化与操作
"""
import sqlite3
import os
from datetime import datetime

# 数据目录：从环境变量读取，默认为后端目录
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__)))
DB_PATH = os.path.join(DATA_DIR, 'knowledge_base.db')


def get_connection():
    """获取数据库连接（带行工厂）"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库：创建主表 + FTS5 全文索引虚拟表 + 触发器"""
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 主文档表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            file_name    TEXT NOT NULL UNIQUE,
            format       TEXT NOT NULL,
            html_content TEXT NOT NULL,
            plain_text   TEXT NOT NULL,
            file_size    INTEGER,
            upload_time  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. FTS5 全文索引虚拟表（只索引 title + plain_text，不索引 HTML 避免样式干扰）
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            title,
            plain_text,
            content='documents',
            content_rowid='id'
        )
    """)

    # 3. 触发器：保持 FTS 索引与主表同步（INSERT）
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, plain_text)
            VALUES (new.id, new.title, new.plain_text);
        END
    """)

    # 4. 触发器：保持 FTS 索引与主表同步（DELETE）
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, plain_text)
            VALUES ('delete', old.id, old.title, old.plain_text);
        END
    """)

    # 5. 触发器：保持 FTS 索引与主表同步（UPDATE）
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, plain_text)
            VALUES ('delete', old.id, old.title, old.plain_text);
            INSERT INTO documents_fts(rowid, title, plain_text)
            VALUES (new.id, new.title, new.plain_text);
        END
    """)

    conn.commit()
    conn.close()
    print(f"[DB] 数据库初始化完成: {DB_PATH}")


def insert_document(title, file_name, format, html_content, plain_text, file_size):
    """插入文档并返回新记录 ID"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO documents (title, file_name, format, html_content, plain_text, file_size)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, file_name, format, html_content, plain_text, file_size))
        conn.commit()
        doc_id = cursor.lastrowid
        conn.close()
        return doc_id
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"文件名已存在: {file_name}")


def get_documents(format_filter=None, sort_order='desc'):
    """获取文档列表（支持格式筛选和排序）"""
    conn = get_connection()
    cursor = conn.cursor()

    order = 'DESC' if sort_order == 'desc' else 'ASC'
    if format_filter and format_filter != 'all':
        cursor.execute(f"""
            SELECT id, title, file_name, format, file_size, upload_time
            FROM documents
            WHERE format = ?
            ORDER BY upload_time {order}
        """, (format_filter,))
    else:
        cursor.execute(f"""
            SELECT id, title, file_name, format, file_size, upload_time
            FROM documents
            ORDER BY upload_time {order}
        """)

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_document_by_id(doc_id):
    """根据 ID 获取单个文档"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, file_name, format, html_content, plain_text, file_size, upload_time
        FROM documents WHERE id = ?
    """, (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_document(doc_id):
    """删除文档"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def search_documents(keyword, limit=50):
    """
    FTS5 全文搜索
    返回文档列表 + 上下文片段（关键词前后各32字）
    """
    conn = get_connection()
    cursor = conn.cursor()

    # FTS5 MATCH 查询，使用 snippet 提取上下文
    # 注意：FTS5 的 snippet 函数参数顺序
    try:
        cursor.execute("""
            SELECT
                d.id,
                d.title,
                d.format,
                d.upload_time,
                snippet(documents_fts, 1, '<mark>', '</mark>', '…', 32) AS context,
                bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON documents_fts.rowid = d.id
            WHERE documents_fts MATCH ? || '*'
            ORDER BY rank
            LIMIT ?
        """, (keyword, limit))
    except sqlite3.OperationalError as e:
        # 如果关键词含特殊 FTS5 字符，转义
        safe_keyword = f'"{keyword}"'
        cursor.execute("""
            SELECT
                d.id,
                d.title,
                d.format,
                d.upload_time,
                snippet(documents_fts, 1, '<mark>', '</mark>', '…', 32) AS context,
                bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON documents_fts.rowid = d.id
            WHERE documents_fts MATCH ? || '*'
            ORDER BY rank
            LIMIT ?
        """, (safe_keyword, limit))

    rows = cursor.fetchall()
    conn.close()

    # 统计每个文档的匹配次数（通过原表查询）
    results = []
    for row in rows:
        doc_id = row['id']
        title = row['title']
        format_ = row['format']
        upload_time = row['upload_time']
        context = row['context'] or ''

        # 统计该文档中关键词出现次数
        doc = get_document_by_id(doc_id)
        if doc:
            plain = doc['plain_text'] or ''
            import re
            match_count = len(re.findall(re.escape(keyword), plain))
        else:
            match_count = 0

        results.append({
            'id': doc_id,
            'title': title,
            'format': format_,
            'upload_time': upload_time,
            'context': context,
            'match_count': match_count
        })

    return results


if __name__ == '__main__':
    init_db()
    # 测试
    print("文档列表:", get_documents())
    print("搜索测试:", search_documents('高血压'))
