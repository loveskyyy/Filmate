"""模拟微信支付 notify 回调,验证 user.credits 是否正确累加。

不真的发 HTTP 请求,直接调内部 notify 处理函数:
1. 选 user_id=1(默认 admin),记录当前 credits
2. 构造一个伪造的加密 callback body(用 lib.wechat_pay 内部加密)
3. 调 notify 路由处理函数
4. 查 user.credits 变化
5. 清理:回滚 credits 增量 + 删除测试 transaction

如果 credits 真的 +N 积分,逻辑就验证通过。
"""

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("simulate_notify")

# 导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

# 从 .env 读配置(用 os.environ 加载)
import os

from dotenv import load_dotenv
from sqlalchemy import select

from lib.db import async_session_factory
from lib.db.models.transaction import Transaction
from lib.db.models.user import User
from lib.wechat_pay import WeChatPayService

load_dotenv(Path(__file__).parent.parent / ".env")


def make_fake_callback_body(pay_service: WeChatPayService, out_trade_no: str, user_id: int, total_cents: int) -> dict:
    """构造伪造的微信支付回调 body。

    实际微信回调是:
    {
      "id": "...",
      "create_time": "...",
      "resource": {
        "algorithm": "AEAD_AES_256_GCM",
        "ciphertext": "...",
        "associated_data": "...",
        "nonce": "...",
      },
      "summary": "..."
    }
    """
    import base64
    import hashlib
    import os as os_mod

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    plain = json.dumps(
        {
            "out_trade_no": out_trade_no,
            "transaction_id": "TX" + uuid.uuid4().hex[:24],
            "trade_state": "SUCCESS",
            "amount": {"total": total_cents, "currency": "CNY"},
            "mchid": pay_service.mch_id,
            "appid": pay_service.app_id,
            "attach": f"user_id={user_id}",
            "success_time": "2026-07-29T10:00:00+08:00",
            "bank_type": "OTHERS",
        },
        ensure_ascii=False,
    )

    # 派生 AES key（与 decrypt_callback 镜像）
    raw_key = pay_service.api_v3_key
    if len(raw_key) != 32:
        try:
            aes_key = base64.b64decode(raw_key)
            if len(aes_key) != 32:
                aes_key = hashlib.sha256(raw_key.encode()).digest()
        except Exception:
            aes_key = hashlib.sha256(raw_key.encode()).digest()
    else:
        aes_key = raw_key.encode()

    nonce = os_mod.urandom(12)
    # 微信 V3 回调默认 associated_data 为空字符串
    associated_data = b""
    ciphertext = AESGCM(aes_key).encrypt(nonce, plain.encode("utf-8"), associated_data)

    return {
        "id": "fake-event-" + uuid.uuid4().hex[:16],
        "create_time": "2026-07-29T10:00:00+08:00",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "associated_data": "",
            "nonce": base64.b64encode(nonce).decode(),
        },
        "summary": "支付成功",
    }


async def main():
    # 1. 读 user_id=1 当前 credits
    async with async_session_factory() as session:
        u = (await session.execute(select(User).where(User.id == 1))).scalar_one_or_none()
        if not u:
            print("ERROR: user_id=1 不存在,无法测试。请先创建 admin 账号。")
            return
        initial_credits = u.credits or 0
        print(f"[BEFORE] user_id=1 credits = {initial_credits}")

    # 2. 构造测试参数
    out_trade_no = "SIM" + uuid.uuid4().hex[:16]  # 不冲突
    test_total_cents = 100  # 1 元 = 100 积分
    expected_delta = 100  # 1 元 → 100 积分

    # 3. 初始化微信支付服务
    pay_service = WeChatPayService(
        mch_id=os.environ.get("WECHAT_MCH_ID", "1739932365"),
        app_id=os.environ.get("WECHAT_APP_ID", "wx239beabbde597de9"),
        api_v3_key=os.environ.get("WECHAT_API_V3_KEY", "xY7zW9vU8tS6rQ5pO4nM3lK2jI1hG0fE"),
        serial_no=os.environ.get("WECHAT_SERIAL_NO", "3A75FCDCCC5FDAB6A53DE46C8E2ACB14333CDC56"),
        private_key_path=os.environ.get("WECHAT_PRIVATE_KEY_PATH", "classpath:cert/apiclient_key.pem"),
    )
    print(f"[INIT] WeChatPayService 初始化完成, mch_id={pay_service.mch_id}")
    print(f"[DEBUG] api_v3_key length={len(pay_service.api_v3_key)}, value={pay_service.api_v3_key!r}")

    # 4. 构造 callback body
    body = make_fake_callback_body(pay_service, out_trade_no, user_id=1, total_cents=test_total_cents)
    print(f"[SIMULATE] out_trade_no={out_trade_no}, total_cents={test_total_cents} (1元→{expected_delta}积分)")

    # 5. 调 notify 处理函数(直接 import 路由处理函数)

    from server.routers.transactions import recharge_notify

    # 构造一个 mock Request 对象
    class MockRequest:
        def __init__(self, body_bytes):
            self._body = body_bytes

        async def body(self):
            return self._body

    body_bytes = json.dumps(body).encode("utf-8")
    mock_req = MockRequest(body_bytes)

    async with async_session_factory() as session:
        try:
            response = await recharge_notify(request=mock_req, session=session)
        except Exception as e:
            import traceback

            print(f"[RAW EXCEPTION] {type(e).__name__}: {e!r}")
            print(f"[TRACEBACK]\n{traceback.format_exc()}")
            raise
        print(f"[RESPONSE] {response}")

    # 6. 查 user.credits 和 transactions
    async with async_session_factory() as session:
        u = (await session.execute(select(User).where(User.id == 1))).scalar_one_or_none()
        after_credits = u.credits or 0
        delta = after_credits - initial_credits
        print(f"[AFTER] user_id=1 credits = {after_credits} (delta = +{delta})")

        tx = (
            await session.execute(select(Transaction).where(Transaction.trade_no == out_trade_no))
        ).scalar_one_or_none()
        if tx:
            print(
                f"[TX] trade_no={tx.trade_no}, amount={tx.amount}, status={tx.status}, before={tx.credits_before}, after={tx.credits_after}"
            )
        else:
            print("[TX] NOT FOUND!")

    # 7. 断言
    if delta == expected_delta and tx and tx.status == "completed":
        print(f"\n✅ 验证通过: credits +{delta} 正确累加, transaction 已写")
    else:
        print(f"\n❌ 验证失败: 预期 +{expected_delta} 实际 +{delta}")

    # 8. 清理:回滚 + 删 tx
    async with async_session_factory() as session:
        u = (await session.execute(select(User).where(User.id == 1))).scalar_one_or_none()
        u.credits = initial_credits  # 还原
        tx = (
            await session.execute(select(Transaction).where(Transaction.trade_no == out_trade_no))
        ).scalar_one_or_none()
        if tx:
            await session.delete(tx)
        await session.commit()
        print(f"[CLEANUP] credits 还原 = {initial_credits}, 测试 transaction 已删")


if __name__ == "__main__":
    asyncio.run(main())
