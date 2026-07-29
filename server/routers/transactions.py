"""积分交易记录与微信充值相关 API。

数据规约(对齐 Filmate 现有 User 模型):
- ``User.id`` / ``Transaction.user_id`` 均为 int 自增主键
- ``User.credits`` 与 ``Transaction.amount`` 均为 int 积分
- 微信回调 ``out_trade_no`` 字符串存到 ``Transaction.trade_no``(unique 索引),
  ``Transaction.id`` 本身仍为 int 自增

积分换算(``CREDIT_PER_YUAN``): 1 元 = 100 积分,与微信分单位对齐,
  保证最小充值 0.01 元也能加上 1 积分。
"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db import get_async_session
from lib.db.models.transaction import Transaction
from lib.db.models.user import User
from lib.wechat_pay import get_wechat_pay_service
from server.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

# 1 元 = 100 积分(1 积分 = 0.01 元 = 1 分)。与微信分单位对齐,允许 0.01 元起充。
CREDIT_PER_YUAN = 100

# 微信支付回调地址配置(必须为可被微信外网访问的 URL)
WECHAT_NOTIFY_URL = os.environ.get(
    "WECHAT_NOTIFY_URL",
    "https://example.com/api/v1/users/me/recharge/notify",
)


# ==================== Response / Request Models ====================


class TransactionResponse(BaseModel):
    id: int
    type: str
    amount: int
    credits_before: int
    credits_after: int
    description: str | None
    trade_no: str | None
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int
    page: int
    page_size: int


class RechargeRequest(BaseModel):
    amount: float  # 充值金额(元)


class RechargeResponse(BaseModel):
    code_url: str
    out_trade_no: str


class CreditsResponse(BaseModel):
    credits: int


# ==================== 用户积分 ====================


@router.get("/users/me/credits", response_model=CreditsResponse)
async def get_my_credits(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前用户的积分余额。前端每 2 秒轮询用于实时反馈充值到账。"""
    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        # 关闭认证的匿名用户不存在于 users 表 —— 回 0 而不是 500
        return CreditsResponse(credits=0)
    return CreditsResponse(credits=user.credits or 0)


# ==================== 用户交易记录 ====================


@router.get("/users/me/transactions", response_model=TransactionListResponse)
async def list_my_transactions(
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前用户的积分交易记录(分页)。"""
    skip = (page - 1) * page_size

    base = select(Transaction).where(Transaction.user_id == current_user.id)
    count_stmt = select(Transaction.id).where(Transaction.user_id == current_user.id)

    page_stmt = base.order_by(Transaction.id.desc()).offset(skip).limit(page_size)
    tx_result = await session.execute(page_stmt)
    transactions = tx_result.scalars().all()

    count_result = await session.execute(count_stmt)
    total = len(count_result.all())

    return TransactionListResponse(
        transactions=[
            TransactionResponse(
                id=t.id,
                type=t.type,
                amount=t.amount,
                credits_before=t.credits_before,
                credits_after=t.credits_after,
                description=t.description,
                trade_no=t.trade_no,
                status=t.status,
                created_at=t.created_at.isoformat() if t.created_at else "",
            )
            for t in transactions
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ==================== 微信充值 ====================


@router.post("/users/me/recharge", response_model=RechargeResponse)
async def create_recharge_order(
    req: RechargeRequest,
    current_user: CurrentUser,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """创建微信充值订单(Native 扫码支付)。

    仅在配置完整时返回 ``code_url``;否则回 503 提示管理员配置。
    实际加积分发生在微信回调里(避免前端轮询前先增加造成对账不一致)。
    """
    if req.amount < 0.01:
        raise HTTPException(status_code=400, detail="充值金额不能少于 0.01 元")

    wechat_pay = get_wechat_pay_service()
    if not wechat_pay:
        raise HTTPException(status_code=503, detail="支付服务暂不可用,请联系管理员配置微信支付")

    # 校验用户存在(关闭认证的匿名用户不会到这里 —— 上方有 current_user 依赖)
    user_result = await session.execute(select(User).where(User.id == current_user.id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    out_trade_no = f"R{uuid.uuid4().hex[:16]}"

    try:
        result = await wechat_pay.create_native_order(
            out_trade_no=out_trade_no,
            description=f"Filmate 充值 ¥{req.amount:.2f}",
            amount=int(req.amount * 100),  # 元 → 分
            notify_url=WECHAT_NOTIFY_URL,
            attach=f"user_id={user.id}",
        )
        logger.info(
            "创建微信支付订单: %s, 金额: %.2f 元, 用户 id: %d",
            out_trade_no,
            req.amount,
            user.id,
        )
        return RechargeResponse(
            code_url=result.get("code_url", ""),
            out_trade_no=out_trade_no,
        )
    except Exception as e:
        logger.error(f"微信支付创建订单失败: {e}")
        raise HTTPException(status_code=500, detail=f"支付接口调用失败: {str(e)}")


@router.post("/users/me/recharge/notify")
async def recharge_notify(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """微信支付回调。

    流程:
    1. 读 request body,解析外层 envelope
    2. ``wechat_pay.decrypt_callback`` 解密 resource
    3. 若 ``trade_state == 'SUCCESS'``,从 attach 解析 user_id,加积分,
       写 ``Transaction`` 记录(``status='completed'``)
    4. 重复通知(同 trade_no 已 completed)直接回 SUCCESS,幂等
    """
    try:
        body = await request.body()
        logger.info("收到微信支付回调, body 长度: %d", len(body))

        wechat_pay = get_wechat_pay_service()
        if not wechat_pay:
            logger.error("微信支付服务未配置")
            return {"code": "ERROR", "message": "服务未配置"}

        import json

        data = json.loads(body)
        resource = data.get("resource", {})
        payment_data = wechat_pay.decrypt_callback(resource)

        out_trade_no = payment_data.get("out_trade_no")
        trade_state = payment_data.get("trade_state")
        logger.info(
            "微信支付回调解析: out_trade_no=%s, trade_state=%s",
            out_trade_no,
            trade_state,
        )

        if trade_state != "SUCCESS":
            # 终态失败 / 退款关闭等 —— 不动账,告诉微信已收到
            return {"code": "SUCCESS", "message": "ignored non-success state"}

        # 幂等:同 out_trade_no 已存在且 completed,直接回 SUCCESS
        existing = await session.execute(
            select(Transaction).where(Transaction.trade_no == out_trade_no).with_for_update()
        )
        existing_tx = existing.scalar_one_or_none()
        if existing_tx and existing_tx.status == "completed":
            logger.info("重复回调, 已处理: %s", out_trade_no)
            return {"code": "SUCCESS", "message": "already processed"}

        # 从 attach 解析 user_id (格式: user_id=xxx)
        attach = payment_data.get("attach", "")
        if not attach or "user_id=" not in attach:
            logger.error("无法从回调中解析用户 ID: attach=%r", attach)
            return {"code": "ERROR", "message": "无法解析用户ID"}

        user_id_str = attach.split("user_id=")[1].split("&")[0] if "&" in attach else attach.split("user_id=")[1]
        try:
            user_id = int(user_id_str)
        except ValueError:
            logger.error("attach 中 user_id 不是整数: %r", user_id_str)
            return {"code": "ERROR", "message": "user_id 格式非法"}

        user_result = await session.execute(select(User).where(User.id == user_id).with_for_update())
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error("用户不存在: user_id=%d", user_id)
            return {"code": "ERROR", "message": "用户不存在"}

        # 计算本次加的积分(微信分 → 元 → 积分)
        total_cents = payment_data.get("amount", {}).get("total", 0)
        yuan_amount = total_cents / 100.0
        credits_delta = int(yuan_amount * CREDIT_PER_YUAN)
        if credits_delta <= 0:
            logger.warning(
                "回调金额折算积分 <= 0, total_cents=%d, yuan=%.4f, credits=%d",
                total_cents,
                yuan_amount,
                credits_delta,
            )
            return {"code": "ERROR", "message": "金额无效"}

        credits_before = user.credits or 0
        credits_after = credits_before + credits_delta

        # 落交易记录(若之前 pending 行存在,改写为 completed)
        if existing_tx is not None:
            existing_tx.credits_before = credits_before
            existing_tx.credits_after = credits_after
            existing_tx.amount = credits_delta
            existing_tx.status = "completed"
        else:
            session.add(
                Transaction(
                    user_id=user.id,
                    type="recharge",
                    amount=credits_delta,
                    credits_before=credits_before,
                    credits_after=credits_after,
                    description="微信充值",
                    trade_no=out_trade_no,
                    status="completed",
                )
            )

        user.credits = credits_after
        await session.commit()

        logger.info(
            "充值成功: out_trade_no=%s, 积分: +%d (%d → %d), user_id=%d",
            out_trade_no,
            credits_delta,
            credits_before,
            credits_after,
            user.id,
        )
        return {"code": "SUCCESS", "message": "成功"}

    except Exception as e:
        logger.exception("微信支付回调处理失败: %s", str(e))
        # 任何异常都回 ERROR,微信会按策略重试;但要 commit 已存在的
        # pending 行(若 user 已锁定则回滚,下次再试)
        try:
            await session.rollback()
        except Exception:
            pass
        return {"code": "ERROR", "message": str(e)}
