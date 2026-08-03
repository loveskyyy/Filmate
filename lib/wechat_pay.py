"""微信支付 V3 服务。

负责签名、订单创建、查询、关闭。回调验签 + 资源解密由
``server/routers/transactions.py`` 直接调用本模块的 ``get_wechat_pay_service``
完成。证书/私钥以 PEM 文件存放,通过环境变量配置路径。
"""

import base64
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

logger = logging.getLogger(__name__)


class WeChatPayService:
    """微信支付 V3 服务"""

    def __init__(
        self,
        mch_id: str,
        app_id: str,
        api_v3_key: str,
        serial_no: str,
        private_key_path: str,
        base_url: str = "https://api.mch.weixin.qq.com",
    ):
        self.mch_id = mch_id
        self.app_id = app_id
        self.api_v3_key = api_v3_key
        self.serial_no = serial_no
        self.private_key_path = private_key_path
        self.base_url = base_url

    def _get_private_key(self) -> str:
        """获取私钥"""
        key_path = self.private_key_path
        if key_path.startswith("classpath:"):
            key_path = key_path.replace("classpath:", "")
            base_dir = Path(__file__).parent.parent
            key_path = base_dir / key_path

        with open(key_path) as f:
            return f.read()

    def _get_serial_no(self) -> str:
        """获取证书序列号。优先从证书文件读取,fallback 到 env 配置值。"""
        cert_path = self.private_key_path
        if cert_path.startswith("classpath:"):
            cert_path = cert_path.replace("classpath:", "")
            cert_path = cert_path.replace("_key.pem", "_cert.pem")
            base_dir = Path(__file__).parent.parent
            cert_path = base_dir / cert_path

        if not Path(cert_path).exists():
            return self.serial_no

        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
            return hex(cert.serial_number).replace("0x", "").upper()

    def _sign(self, message: str, private_key: str) -> str:
        """签名"""
        private_key_obj = cast(
            RSAPrivateKey,
            serialization.load_pem_private_key(
                private_key.encode(),
                password=None,
                backend=default_backend(),
            ),
        )
        signature = private_key_obj.sign(
            message.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    def _get_token(self, method: str, url: str, body: str = "") -> str:
        """获取授权 Token"""
        private_key = self._get_private_key()
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n"
        signature = self._sign(message, private_key)

        token = (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{self.mch_id}",'
            f'nonce_str="{nonce}",signature="{signature}",'
            f'timestamp="{timestamp}",serial_no="{self._get_serial_no()}"'
        )
        return token

    async def create_native_order(
        self,
        out_trade_no: str,
        description: str,
        amount: int,
        notify_url: str,
        attach: str = "",
    ) -> dict[str, Any]:
        """创建 Native 支付订单(返回二维码 url)"""
        url = f"{self.base_url}/v3/pay/transactions/native"

        payload = {
            "mchid": self.mch_id,
            "out_trade_no": out_trade_no,
            "appid": self.app_id,
            "description": description,
            "notify_url": notify_url,
            "amount": {
                "total": amount,
                "currency": "CNY",
            },
            "attach": attach,
        }

        body = json.dumps(payload)
        token = self._get_token("POST", "/v3/pay/transactions/native", body)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                content=body,
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Filmate/1.0",
                },
                timeout=30.0,
            )

        if response.status_code != 200:
            logger.error(f"WeChat Pay API error: {response.text}")
            raise Exception(f"微信支付创建订单失败: {response.text}")

        return response.json()

    async def query_order(self, out_trade_no: str) -> dict[str, Any]:
        """查询订单"""
        path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={self.mch_id}"
        url = f"{self.base_url}{path}"

        token = self._get_token("GET", path)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": token,
                    "Accept": "application/json",
                    "User-Agent": "Filmate/1.0",
                },
                timeout=30.0,
            )

        if response.status_code != 200:
            logger.error(f"WeChat Pay Query API error: {response.text}")
            raise Exception(f"微信支付查询订单失败: {response.text}")

        return response.json()

    async def close_order(self, out_trade_no: str) -> dict[str, Any]:
        """关闭订单"""
        path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}/close"
        url = f"{self.base_url}{path}"

        payload = {"mchid": self.mch_id}
        body = json.dumps(payload)
        token = self._get_token("POST", path, body)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                content=body,
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Filmate/1.0",
                },
                timeout=30.0,
            )

        if response.status_code != 204:
            logger.error(f"WeChat Pay Close API error: {response.text}")
            raise Exception(f"微信支付关闭订单失败: {response.text}")

        return {"code": "SUCCESS"}

    def decrypt_callback(self, resource: dict[str, str]) -> dict[str, Any]:
        """解密微信回调的 resource.ciphertext。

        API v3 密钥约定 32 字节;若 env 里的值长度不是 32,先尝试 base64
        解码,仍不是 32 字节就 SHA-256 派生,以兼容手工填写的短密钥。
        """
        encrypted_data = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        ciphertext = base64.b64decode(encrypted_data)
        nonce_bytes = nonce.encode() if isinstance(nonce, str) else nonce
        associated_data_bytes = associated_data.encode()

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw_key = self.api_v3_key
        if len(raw_key) != 32:
            try:
                aes_key = base64.b64decode(raw_key)
                if len(aes_key) != 32:
                    aes_key = hashlib.sha256(raw_key.encode()).digest()
            except Exception:
                aes_key = hashlib.sha256(raw_key.encode()).digest()
        else:
            aes_key = raw_key.encode()
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce_bytes, ciphertext, associated_data_bytes)
        return json.loads(plaintext)


# 默认实例(从环境变量或配置读取)
_default_service: WeChatPayService | None = None


def get_wechat_pay_service() -> WeChatPayService | None:
    """获取微信支付服务实例。

    配置不完整时返回 ``None`` —— 调用方应回 503 提示管理员配置,而不是
    抛异常污染启动路径。
    """
    global _default_service

    if _default_service is not None:
        return _default_service

    import os

    mch_id = os.environ.get("WECHAT_MCH_ID")
    app_id = os.environ.get("WECHAT_APP_ID")
    api_v3_key = os.environ.get("WECHAT_API_V3_KEY")
    serial_no = os.environ.get("WECHAT_SERIAL_NO")
    private_key_path = os.environ.get("WECHAT_PRIVATE_KEY_PATH") or "cert/apiclient_key.pem"

    if not (mch_id and app_id and api_v3_key and serial_no):
        logger.warning("微信支付配置不完整,跳过初始化")
        return None

    # 上面的 if 分支已保证非空,这里用 assert 帮类型推断收敛;
    # 运行时若真走到这里确实是 bug,应该被显式抛出。
    assert mch_id and app_id and api_v3_key and serial_no

    _default_service = WeChatPayService(
        mch_id=mch_id,
        app_id=app_id,
        api_v3_key=api_v3_key,
        serial_no=serial_no,
        private_key_path=private_key_path,
    )

    return _default_service
