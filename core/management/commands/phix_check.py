"""诊断心履 ↔ phix 这条链路：服务在不在、加密有没有生效、公钥对不对、服务密钥行不行。

    python manage.py phix_check
    python manage.py phix_check --username someone --password '……'
    python manage.py phix_check --trust      # 确认服务器换过钥匙后，重新记下它的公钥

**只读**（唯一例外是 `--trust`，它只写 `.phix_pubkey` 这一个文件）。
启用 phix 账号打通之前/之后都建议跑一遍。
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from core import phix_auth, phix_e2e


class Command(BaseCommand):
    help = "诊断心履与 phix 统一账号之间的连接（只读）"

    def add_arguments(self, parser):
        parser.add_argument("--username", help="顺便校验一个真实账号（可选）")
        parser.add_argument("--password", help="配合 --username 使用（可选）")
        parser.add_argument(
            "--trust", action="store_true",
            help="把当前服务器公钥记成「可信」（只在确认服务器确实换过钥匙时用；"
                 "只写 .phix_pubkey 这一个文件，不改其它任何数据）")

    def handle(self, *args, **options):
        ok = True

        def line(label, good, extra=""):
            nonlocal ok
            mark = "✔" if good else "✘"
            if not good:
                ok = False
            self.stdout.write(f"  {mark} {label}" + (f"   {extra}" if extra else ""))

        self.stdout.write(self.style.MIGRATE_HEADING("心履 ↔ phix 链路诊断"))

        # 1. 开关
        self.stdout.write("\n[1] 配置")
        line("PHIX_AUTH_ENABLED 已打开", bool(getattr(phix_auth.settings,
                                                   "PHIX_AUTH_ENABLED", False)))
        line("PHIX_SERVER 已填", bool(getattr(phix_auth.settings, "PHIX_SERVER", "")),
             getattr(phix_auth.settings, "PHIX_SERVER", ""))
        line("PHIX_SERVICE_KEY 已填", bool(getattr(phix_auth.settings,
                                                  "PHIX_SERVICE_KEY", "")))
        if not phix_auth.enabled():
            self.stdout.write(self.style.WARNING(
                "\n后端**没有启用**（三项要同时满足）。此时心履行为与从前完全一样。"))
            return

        server = phix_auth.settings.PHIX_SERVER.rstrip("/")

        # 2. 连通性与加密
        self.stdout.write("\n[2] 服务器")
        import requests

        try:
            info = requests.get(server + phix_auth.PING_PATH, timeout=8).json()
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"连不上 phix：{exc}") from exc
        line("服务可达", bool(info.get("ok")), f"version={info.get('version')}")
        enc = int(info.get("enc") or 0) == 1
        line("支持应用层加密（网线上只有密文）", enc,
             "开了就更安全；没开则依赖 HTTPS 或内网" if not enc else "")
        line("服务端支持 AuthHash（kdf_algo 含 v2）",
             "scrypt-hkdf-v2" in (info.get("kdf_algos") or []),
             str(info.get("kdf_algos")))
        line("服务密钥校验已启用", bool(info.get("service_verify_enabled")))

        # 3. 公钥固定
        self.stdout.write("\n[3] 服务器公钥固定")
        if not enc:
            self.stdout.write("  · 服务器没开加密，跳过")
        else:
            base = phix_auth.base_dir()
            pinned = phix_e2e.load_pinned(base).get(server)
            # ⚠️ **存的是 hex，不是 base64**。`_server_public_key()` 调
            # `pin_key(base, server, pk.hex())`；这里以前直接拿 `/ping` 的 base64
            # 去比，于是**永远对不上** —— 既让心履所有登录在 `pin_key` 里抛
            # ServerKeyError，又让这个诊断工具报了个假的"公钥被换"。
            now = ""
            try:
                now = phix_e2e.b64d(info.get("pk") or "").hex()
            except Exception:  # noqa: BLE001
                now = ""
            if not now:
                line("拿到服务器公钥", False, "服务器返回的 pk 解不开")
            elif not pinned:
                self.stdout.write("  · 还没固定过；下一次连接会自动记下来（hex）")
            elif pinned == now:
                line("公钥与记住的一致", True, now[:12] + "…")
            else:
                # **别只说"对不上"就走人** —— 把两串都摆出来，并给出两条明确的路：
                #   服务器确实重装过 → `--trust`；怀疑有人冒充 → 别动，先查清楚。
                self.stdout.write("  ✘ 公钥与记住的不一致")
                self.stdout.write(f"      记住的：{pinned[:16]}…")
                self.stdout.write(f"      现在的：{now[:16]}…")
                self.stdout.write(f"      存的位置：{phix_e2e.pin_file(base)}")
                if options.get("trust"):
                    # **不要调 `pin_key()`** —— 它的契约是"已有且不一致就抛"，
                    # 这里恰恰是要覆盖不一致的那条，走它必然抛 ServerKeyError。
                    doc = phix_e2e.load_pinned(base)
                    doc[server] = now
                    p = phix_e2e.pin_file(base)
                    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
                    try:
                        os.chmod(p, 0o600)
                    except OSError:
                        pass
                    self.stdout.write(self.style.WARNING(
                        "      --trust 已生效：新公钥已记下。"
                        "**前提是你已经确认这是服务器重装/换钥匙，不是有人在中间冒充。**"))
                    line("公钥与记住的一致（刚刚更新）", True, now[:12] + "…")
                else:
                    ok = False
                    self.stdout.write(
                        "      → 确认是服务器重装/换过钥匙："
                        "`python manage.py phix_check --trust` 重新记一次\n"
                        "      → 不确定：**先别动**，查清是不是有人冒充（心履会拒绝连它）")

        # 4. 可选：真账号
        user = options.get("username")
        if user:
            self.stdout.write("\n[4] 真账号校验")
            pwd = options.get("password")
            if not pwd:
                raise CommandError("给了 --username 就要一起给 --password")
            have_key = bool(getattr(phix_auth.settings, "PHIX_SERVICE_KEY", ""))
            if not have_key:
                self.stdout.write(self.style.WARNING(
                    "  ! 本机没设 PHIX_SERVICE_KEY —— /auth/verify 会回 403，"
                    "这一节必然失败（**不是账号密码的问题**）。"))
            try:
                got = phix_auth.phix_verify_detailed(user, pwd)
            except phix_e2e.ServerKeyError as exc:
                # 这里原来写的是 `e2e.ServerKeyError` —— 那个名字只存在于
                # core/phix_auth.py 里，本模块没导入过，公钥一对不上就抛 **NameError**
                # （把"公钥变了"这种要紧事变成一句看不懂的报错）。已改成模块真名。
                raise CommandError(f"公钥校验失败：{exc}") from exc
            if got.get("ok"):
                line("phix 认可这个账号密码", True, f"phix#{got['user_id']}")
            else:
                why = {
                    "bad_credentials": "口令不对，或账号不存在",
                    "forbidden": "**服务密钥不对**（本机 PHIX_SERVICE_KEY 与 phix 那边不一致）",
                    "rate_limited": "被限流了，过一会儿再试",
                    "unreachable": "连不上服务（或信封打不开）",
                }.get(got.get("code"), f"服务端说：{got.get('code')}")
                line("phix 认可这个账号密码", False,
                     f"{why}" + (f"（{got.get('message')}）" if got.get("message") else ""))
            if got.get("ok"):
                from django.contrib.auth import get_user_model

                local = get_user_model().objects.filter(username=user).first()
                if local is None:
                    self.stdout.write("  · 心履这边还没有同名账号 —— 首次登录时会自动建影子账号")
                else:
                    pid = phix_auth.phix_user_id_of(local)
                    self.stdout.write(f"  · 心履本地账号已存在；phix_user_id="
                                      f"{pid}（{'已关联' if pid else '还没关联'}）")
        else:
            self.stdout.write("\n[4] 真账号校验：跳过（想验就加 --username / --password）")

        self.stdout.write("")
        if ok:
            self.stdout.write(self.style.SUCCESS("结论：这条链路是通的。"))
        else:
            self.stdout.write(self.style.ERROR("结论：有问题，看上面标 ✘ 的项。"))
