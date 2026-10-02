"""心履网页端读取 phix 同步对象的**最小**密码学助手。

为什么有这个文件：网页端将来若要展示客户端推上云的 `profile`（头像）等对象，
需要能把信封解开。信封密钥只依赖 **DEK + 对象名**（见 phix 协议规范 §2），
而 DEK 只在客户端内存里 —— 所以**网页端拿不到 DEK 时这里一律返回 None**，
调用方回落成首字母占位头像（`templates/base.html` 的 `.phix-avatar`）。

函数体从 `D:\\phl-lite-dev\\hellopinghe\\phixcrypto.py` **原样复制**（保持两端逐字节一致），
只保留解信封所需的最小集合。不要在这里发明新算法。
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ENVELOPE_PREFIX = "PHIX1."
NONCE_BYTES = 12
OBJECT_KEY_SALT = b"phix/v1/object-keys"


def b64d(text: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError("需要 base64url 字符串")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def aad_object(user_id: int, name: str) -> bytes:
    return f"phix/v1/object|{user_id}|{name}".encode("utf-8")


def derive_object_key(dek: bytes, name: str) -> bytes:
    """DEK + 对象名 → 对象密钥。与客户端完全一致。"""
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=OBJECT_KEY_SALT, info=name.encode("utf-8"),
    ).derive(dek)


def unseal_object(dek: bytes, user_id: int, name: str, envelope: str) -> bytes:
    if not isinstance(envelope, str) or not envelope.startswith(ENVELOPE_PREFIX):
        raise ValueError("不是 PHIX1 信封")
    rest = envelope[len(ENVELOPE_PREFIX):]
    nonce_s, ct_s = rest.split(".", 1)
    nonce, ct = b64d(nonce_s), b64d(ct_s)
    return AESGCM(derive_object_key(dek, name)).decrypt(nonce, ct,
                                                        aad_object(user_id, name))


def fetch_profile(server: str, token: str, user_id: int, dek: bytes | None = None) -> dict | None:
    """取 `profile` 同步对象。

    - `dek` 为 None（网页端的常态）→ 直接返回 None，调用方用占位头像。
    - 给了 `dek`（例如将来某处把 DEK 传进来）→ 解信封返回 dict；任何失败返回 None。
    **绝不**抛异常给视图层。
    """
    if dek is None:
        return None
    import json

    import requests

    try:
        r = requests.get(server.rstrip("/") + "/api/v1/sync/objects/profile",
                         headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if r.status_code != 200:
            return None
        payload = (r.json() or {}).get("payload")
        if not payload:
            return None
        plain = unseal_object(dek, user_id, "profile", payload)
        data = json.loads(plain.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001  网络/解密/JSON 任何失败都当"没有头像"
        return None
