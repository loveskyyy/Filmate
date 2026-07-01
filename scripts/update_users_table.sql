-- 更新 users 表添加新字段
-- 运行方式: sqlite3 your_database.db < scripts/update_users_table.sql

-- 添加 email 字段
ALTER TABLE users ADD COLUMN email TEXT;

-- 添加 hashed_password 字段
ALTER TABLE users ADD COLUMN hashed_password TEXT NOT NULL DEFAULT '';

-- 添加 credits 字段（积分）
ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 0;

-- 设置默认管理员的密码（admin123）
-- 需要先安装 passlib: pip install passlib[bcrypt]
-- 然后运行 Python 脚本生成密码哈希

-- 创建管理员（如果不存在）
-- INSERT OR IGNORE INTO users (username, role, is_active, email, hashed_password, credits)
-- VALUES ('admin', 'admin', 1, 'admin@example.com', '$2b$12$...', 0);
