#!/usr/bin/env python3
"""初始化管理员账户"""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import text

from lib.db.engine import get_async_session


def make_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


async def main():
    async for session in get_async_session():
        # 添加字段
        for col_sql in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 0",
            "ALTER TABLE users ALTER COLUMN created_at SET DEFAULT NOW()",
            "ALTER TABLE users ALTER COLUMN updated_at SET DEFAULT NOW()",
        ]:
            try:
                await session.execute(text(col_sql))
            except Exception:
                pass
        await session.commit()

        # 检查
        result = await session.execute(text("SELECT * FROM users WHERE username = 'root'"))
        if result.fetchone():
            print("管理员 root 已存在")
            return

        # 插入（包含所有必填字段）
        now = datetime.now(UTC)
        uid = secrets.token_hex(8)
        pw_hash = make_hash("root123")
        await session.execute(
            text("""
            INSERT INTO users (id, username, hashed_password, role, is_active, credits, created_at, updated_at)
            VALUES (:id, :username, :password, :role, :is_active, :credits, :created_at, :updated_at)
        """),
            {
                "id": uid,
                "username": "root",
                "password": pw_hash,
                "role": "admin",
                "is_active": True,
                "credits": 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        await session.commit()
        print("管理员创建成功! root / root123")


if __name__ == "__main__":
    asyncio.run(main())
