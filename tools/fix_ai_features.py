import sqlite3

# 连接到数据库
conn = sqlite3.connect("./games.db")
cursor = conn.cursor()

# 更新豆包记录
cursor.execute('''
    UPDATE ai_features 
    SET company_name = "字节", 
        category_id = 1, 
        is_approved = 1 
    WHERE url = "https://www.doubao.com"
''')

print(f"更新了 {cursor.rowcount} 条记录")

# 提交更改
conn.commit()

# 查询更新后的豆包记录
cursor.execute('SELECT id, title, url, company_name, category_id, is_approved FROM ai_features WHERE url = "https://www.doubao.com"')
feature = cursor.fetchone()

print("\n更新后的豆包记录:")
print(f"ID: {feature[0]}")
print(f"标题: {feature[1]}")
print(f"URL: {feature[2]}")
print(f"公司名: {feature[3]}")
print(f"分类ID: {feature[4]}")
print(f"是否通过审核: {feature[5]}")

# 关闭连接
conn.close()