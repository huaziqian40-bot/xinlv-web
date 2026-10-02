"""心履侧的 phix 传输与凭证工具。

**为什么心履要自己实现这一份**：心履（第一台服务器）在「认证委托」里是**调用方**，
它要把用户的凭证交给 phix（第二台服务器）。按 `加密链路思路.md` §4 的模型，
第 1 台应该只当"信使"——它能拿到的最少越好。所以这里做到两件事：

1. **算 AuthHash 而不是传口令**：`AuthHash = HKDF(scrypt(P, auth_salt), salt, "phix/v1/auth")`。
   与客户端算出来的一模一样，所以 **phix 那边认**。心履自己**不存**这个值，用完就丢。
2. **应用层加密**：把请求套进 X25519 密封盒信封（与 PLL/PHL 用的是同一套协议，
   见 `phix-协议规范.md` §10）。这样即使 phix 没接 HTTPS，内网线上也只有密文。

算法与 `D:\phl-lite-dev\hellopinghe\phixcrypto.py` 逐字节一致（那边是权威实现，
已有跨语言互操作测试钉着）。这里只保留心履用得上的那一小部分。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (X25519PrivateKey,
                                                              X25519PublicKey)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ---- 协议常量（与规范 §2.4 / §10 一致，改这里 = 改协议）----
ENVELOPE_PREFIX = "PHIX1."
SEAL_INFO = b"phix/v1/seal"
AUTH_INFO = b"phix/v1/auth"
ENC_INFO = b"phix/v1/enc"
REQ_AAD_PREFIX = b"phix/v1/req|"
KDF_ALGO_V1 = "scrypt-n15-r8-p1"
KDF_ALGO_V2 = "scrypt-hkdf-v2"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 32768, 8, 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
EPK_LEN, NONCE_LEN, SK_LEN = 32, 12, 32

#: 与 JavaScript `String.prototype.trim()` 一致的空白集合（两端必须一样）
_JS_TRIM_CHARS = "".join(
    [chr(c) for c in range(0x09, 0x0E)] +
    ["\u0020", "\u00a0", "\u1680"] +
    [chr(c) for c in range(0x2000, 0x200B)] +
    ["\u2028", "\u2029", "\u202f", "\u205f", "\u3000", "\ufeff"]
)


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt,
                info=info).derive(ikm)


def derive_mk(passphrase: str, salt_hex: str) -> bytes:
    """口令 → MK（scrypt，两代 KDF 共用这一步）。"""
    pw = unicodedata.normalize("NFKC", passphrase).strip(_JS_TRIM_CHARS).encode("utf-8")
    return hashlib.scrypt(pw, salt=bytes.fromhex(salt_hex), n=SCRYPT_N, r=SCRYPT_R,
                          p=SCRYPT_P, dklen=32, maxmem=SCRYPT_MAXMEM)


def derive_auth_hash(passphrase: str, auth_salt_hex: str,
                     algo: str = KDF_ALGO_V2) -> bytes:
    """口令 → AuthHash（**这是要发给 phix 的东西**，不是口令本身）。"""
    if algo == KDF_ALGO_V1:
        raise ValueError("v1 账号没有 AuthHash（它只能比对口令原文）")
    raw = bytes.fromhex(auth_salt_hex)
    return _hkdf(derive_mk(passphrase, auth_salt_hex), raw, AUTH_INFO, 32)


def auth_hash_hex(passphrase: str, auth_salt_hex: str,
                  algo: str = KDF_ALGO_V2) -> str:
    return derive_auth_hash(passphrase, auth_salt_hex, algo).hex()


def uses_auth_hash(algo: str | None) -> bool:
    return (algo or KDF_ALGO_V2) != KDF_ALGO_V1


# ---------------- 应用层加密信封（规范 §10） ----------------

def seal_box(msg: bytes, recipient_pk: bytes) -> bytes:
    esk = X25519PrivateKey.generate()
    epk = esk.public_key().public_bytes(serialization.Encoding.Raw,
                                        serialization.PublicFormat.Raw)
    shared = esk.exchange(X25519PublicKey.from_public_bytes(recipient_pk))
    salt = epk + recipient_pk
    key = _hkdf(shared, salt, SEAL_INFO, 32)
    nonce = os.urandom(NONCE_LEN)
    return epk + nonce + AESGCM(key).encrypt(nonce, msg, salt)


def open_box(sealed: bytes, recipient_sk_raw: bytes, recipient_pk: bytes) -> bytes:
    """打开给自己的密封盒。心履平时用不到（它只发不收），测试与排障时有用。"""
    if len(sealed) < EPK_LEN + NONCE_LEN + 16:
        raise ValueError("密封盒长度不对")
    epk = sealed[:EPK_LEN]
    nonce = sealed[EPK_LEN:EPK_LEN + NONCE_LEN]
    ct = sealed[EPK_LEN + NONCE_LEN:]
    sk = X25519PrivateKey.from_private_bytes(recipient_sk_raw)
    shared = sk.exchange(X25519PublicKey.from_public_bytes(epk))
    salt = epk + recipient_pk
    key = _hkdf(shared, salt, SEAL_INFO, 32)
    return AESGCM(key).decrypt(nonce, ct, salt)


def raw_private_bytes(sk: X25519PrivateKey) -> bytes:
    """X25519 私钥 → 32 字节原始字节。"""
    return sk.private_bytes(serialization.Encoding.Raw,
                            serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())


def env_aad(method: str, path: str) -> bytes:
    return REQ_AAD_PREFIX + method.encode("utf-8") + b"|" + path.encode("utf-8")


def make_envelope(server_pk: bytes, method: str, path: str, body,
                  query: str = "") -> tuple[dict, bytes]:
    sk = os.urandom(SK_LEN)
    inner = {"m": method, "p": path, "q": query, "b": body,
             "ts": int(time.time()), "nonce": b64e(os.urandom(16))}
    iv = os.urandom(NONCE_LEN)
    ct = AESGCM(sk).encrypt(iv, json.dumps(inner, ensure_ascii=False).encode("utf-8"),
                            env_aad(method, path))
    return {"sealed_sk": b64e(seal_box(sk, server_pk)), "iv": b64e(iv),
            "ct": b64e(ct)}, sk


def open_envelope_response(sk: bytes, method: str, path: str, envelope: dict) -> bytes:
    return AESGCM(sk).decrypt(b64d(envelope["iv"]), b64d(envelope["ct"]),
                              env_aad(method, path))


# ---------------- 密钥材料生成（老用户迁移：现场建 phix 账号用） ----------------
#
# 这一段从 `D:\phl-lite-dev\hellopinghe\phixcrypto.py`（权威实现）复制了**最小集合**：
# 只够在迁移登录时生成一套 v2 密钥材料去调 `POST /auth/register`。逐字节一致，
# 有跨语言互操作测试钉着。心履只生成、不落盘、不解析。

DEK_BYTES = 32
SALT_BYTES = 16
OBJECT_KEY_SALT = b"phix/v1/object-keys"
KEYCHECK_NAME = "__keycheck__"
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 去掉易混的 I O 0 1
RECOVERY_CHARS = 24
_ASCII_ALNUM = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def new_salt() -> str:
    return secrets.token_hex(SALT_BYTES)


def new_key_check_plain() -> str:
    return secrets.token_hex(32)


def new_recovery_code() -> str:
    """24 位 base32（去易混字符）≈ 115 bit 熵，XXXX-XXXX-… 便于抄写。"""
    chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CHARS))
    return "-".join(chars[i:i + 4] for i in range(0, RECOVERY_CHARS, 4))


def normalize_recovery_code(code: str) -> str:
    """去分隔符、统一大写，只留 ASCII 字母数字（与 Node 端 `[0-9A-Za-z]` 对齐）。"""
    up = unicodedata.normalize("NFKC", code).upper()
    return "".join(ch for ch in up if ch in _ASCII_ALNUM)


def aad_identity(username: str) -> bytes:
    """身份族 AAD：注册前拿不到 user_id，只能用 username。"""
    return f"phix/v1/identity|{username}".encode("utf-8")


def seal(key: bytes, plaintext: bytes, aad: bytes) -> str:
    """加密 → 信封字符串 `PHIX1.<b64 nonce>.<b64 ct||tag>`（对象族/身份族通用）。"""
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return f"{ENVELOPE_PREFIX}{b64e(nonce)}.{b64e(ct)}"


def derive_kek(passphrase: str, salt_hex: str, algo: str = KDF_ALGO_V2) -> bytes:
    """口令 → KEK。v1 的 KEK 就是 MK；v2 是 HKDF(MK, "enc")。"""
    mk = derive_mk(passphrase, salt_hex)
    if algo == KDF_ALGO_V1:
        return mk
    return _hkdf(mk, bytes.fromhex(salt_hex), ENC_INFO, 32)


def derive_object_key(dek: bytes, name: str) -> bytes:
    return _hkdf(dek, OBJECT_KEY_SALT, name.encode("utf-8"), 32)


def wrap_dek(dek: bytes, passphrase: str, salt_hex: str, username: str,
             algo: str = KDF_ALGO_V2) -> str:
    return seal(derive_kek(passphrase, salt_hex, algo), dek, aad_identity(username))


def wrap_dek_with_recovery(dek: bytes, code: str, salt_hex: str, username: str,
                           algo: str = KDF_ALGO_V2) -> str:
    return seal(derive_kek(normalize_recovery_code(code), salt_hex, algo), dek,
                aad_identity(username))


def make_key_check(dek: bytes, username: str, plain_hex: str) -> str:
    """自检块：用 `__keycheck__` 的对象密钥加密**随机明文**（非公开常量）。"""
    return seal(derive_object_key(dek, KEYCHECK_NAME), bytes.fromhex(plain_hex),
                aad_identity(username))


def new_material(username: str, passphrase: str, key_mode: str = "password",
                 kdf_algo: str = KDF_ALGO_V2) -> dict:
    """注册新账号：随机生成一把 DEK，返回整套材料 + 恢复码 + AuthHash。"""
    dek = os.urandom(DEK_BYTES)
    code = new_recovery_code()
    plain = new_key_check_plain()
    salt = new_salt()
    rsalt = new_salt()
    asalt = new_salt()
    out = {
        "dek": dek,
        "recovery_code": code,
        "kdf_algo": kdf_algo,
        "kdf_salt": salt,
        "auth_salt": asalt,
        "recovery_salt": rsalt,
        "key_wrap": wrap_dek(dek, passphrase, salt, username, kdf_algo),
        "recovery_wrap": wrap_dek_with_recovery(dek, code, rsalt, username, kdf_algo),
        "key_check": make_key_check(dek, username, plain),
        "key_check_plain": plain,
        "key_mode": key_mode,
    }
    if uses_auth_hash(kdf_algo):
        out["auth_hash"] = auth_hash_hex(passphrase, asalt, kdf_algo)
    return out


# ---------------- 服务器公钥固定 ----------------
#
# 与客户端一样：**首次信任后固定存本地**，以后对不上就拒绝连接（防冒充）。

class ServerKeyError(Exception):
    pass


def pin_file(base_dir: Path) -> Path:
    return Path(base_dir) / ".phix_pubkey"


def load_pinned(base_dir: Path) -> dict:
    try:
        return json.loads(pin_file(base_dir).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def pin_key(base_dir: Path, server: str, pk_hex: str) -> None:
    """把服务器公钥记下来；**已有且不一致就报错**。"""
    doc = load_pinned(base_dir)
    old = doc.get(server)
    if old and old != pk_hex:
        raise ServerKeyError(
            f"phix 服务器的加密公钥变了（{server}）！可能是服务器重装过，"
            "也可能是有人在中间冒充。确认无误后删掉 "
            f"{pin_file(base_dir)} 里对应的那条再试。")
    if old != pk_hex:
        doc[server] = pk_hex
        try:
            p = pin_file(base_dir)
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
            os.chmod(p, 0o600)
        except OSError:
            pass          # 存不下就只是不能固定，不该挡住登录


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
