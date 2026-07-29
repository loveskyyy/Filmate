"""微信支付 V3 本地工具。

提供查询/关闭订单的能力,便于运维在不开 WebUI 的情况下对账。
不依赖 filmate 内部模块,直接复用 wechat_pay 服务的轻量封装。
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from lib.wechat_pay import WeChatPayService


def _get_service() -> WeChatPayService:
    """从环境变量构造服务实例,失败抛错(无降级路径)。"""
    return WeChatPayService(
        mch_id=os.environ["WECHAT_MCH_ID"],
        app_id=os.environ["WECHAT_APP_ID"],
        api_v3_key=os.environ["WECHAT_API_V3_KEY"],
        serial_no=os.environ["WECHAT_SERIAL_NO"],
        private_key_path=os.environ.get("WECHAT_PRIVATE_KEY_PATH", "cert/apiclient_key.pem"),
    )


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


async def _query(out_trade_no: str) -> None:
    svc = _get_service()
    result = await svc.query_order(out_trade_no)
    _print(result)


async def _close(out_trade_no: str) -> None:
    svc = _get_service()
    result = await svc.close_order(out_trade_no)
    _print(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Filmate 微信支付本地工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_query = sub.add_parser("query", help="按商户订单号查询微信支付订单")
    p_query.add_argument("out_trade_no")

    p_close = sub.add_parser("close", help="关闭未支付订单")
    p_close.add_argument("out_trade_no")

    args = parser.parse_args()

    try:
        if args.cmd == "query":
            asyncio.run(_query(args.out_trade_no))
        elif args.cmd == "close":
            asyncio.run(_close(args.out_trade_no))
    except KeyError as e:
        print(f"缺少环境变量: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
