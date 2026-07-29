"""积分交易记录模型。

每次用户积分变动都落一行,作为审计/查询/对账的真相源。
余额本身存在 ``users.credits`` 字段,交易记录只描述 delta。
"""

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class Transaction(TimestampMixin, Base):
    """积分交易记录表"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 交易类型: recharge(微信充值) / consumption(消费扣减) / refund(退款) / adjustment(管理员调整)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 积分增量(可正可负;recharge 永远为正)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # 交易前后的积分余额(冗余存,方便对账;真值仍以 users.credits 为准)
    credits_before: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 微信商户订单号(回调关联用),以 R 开头便于与本地 id 区分
    trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    # pending / completed / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    # 预留的 JSON 扩展字段
    extra: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
