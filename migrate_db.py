import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('games.db')
cursor = conn.cursor()

# 创建categories表
cursor.execute('''
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# 插入默认分类
cursor.execute('''
INSERT OR IGNORE INTO categories (id, name, created_at) VALUES (1, '游戏', CURRENT_TIMESTAMP)
''')

# 检查games表是否已经有category_id字段
cursor.execute("PRAGMA table_info(games)")
columns = [column[1] for column in cursor.fetchall()]

# 如果没有category_id字段，则添加
if 'category_id' not in columns:
    cursor.execute('''
    ALTER TABLE games ADD COLUMN category_id INTEGER DEFAULT 1
    ''')

# 提交更改
conn.commit()

# 关闭连接
conn.close()

print("✅ 数据库迁移完成！")
