# -*- coding: utf-8 -*-
"""长轮询：让客户端"有变化就立刻知道"，而不是自己定时去问。

背景：同步延迟要压到秒级。原来客户端只有用户手动触达才拉取，别的设备改了
要等很久才知道。这里加一个 `GET /api/v1/sync/watch`：请求进来后服务端**挂着
不回**，直到这个账号的心情数据真的变了（或挂满 ~25 秒超时），再返回。
客户端拿到"变了"就立刻跑一次 `/sync/pull/` —— 延迟从"用户手动刷新"变成"一个 RTT"。

为什么不用 WebSocket：服务端是 Django + **waitress**（纯 WSGI，不支持 WS），
上 WS 要换 ASGI + Channels + Redis，还得改部署配置；而这个场景里长轮询和 WS 的
延迟都是一个 RTT，人眼分不出来。长轮询在现有栈上零基础设施改动就能跑。

**正确性靠数据库，不靠进程内计数器**：光标（cursor）是从库里现算的
（见 `api._mood_cursor`），所以换 worker、重启服务都不会漏变化；
进程内的 `Condition` 只是让"变了"能立刻叫醒等待的请求，不做判断依据。

**挂起请求是有代价的**：waitress 每个连接占一个线程，所以用 `WATCH_SLOTS`
限住同时挂起的个数，超出的立刻打回让客户端短轮询 —— 详见那个常量的注释。
"""
import os
import threading
import time

#: 一次长轮询最多挂多久（秒）。
MAX_HOLD_SECONDS = 25.0

#: 即便没人 notify，也至少每隔这么久回库里看一眼。
#: 进程内 notify 只覆盖"写请求也在这台 worker 上"这一种情况；
#: 多 worker 时另一个 worker 写的就收不到 notify，靠这个兜底。
POLL_FALLBACK_SECONDS = 2.0

#: 同时最多挂起多少个长轮询。
#:
#: **这个上限是必须的，不是保守**：waitress 是线程池模型，一个挂起的请求
#: 就**实打实占住一个线程**整整 25 秒。假如线程数不大而同时有那么多客户端
#: 挂在这里，服务端就再也接不了任何别的请求 —— 连"把数据写进去、好让长轮询
#: 醒过来"的那个写请求都要排队，同步从"秒级"直接退化成"卡住"。也就是说：
#: 没有上限的长轮询会把线程池饿死，而且是自己饿死自己。
#:
#: 所以拿不到名额就**立刻返回**（`changed=false` + `retry_after`），让客户端
#: 退化成短轮询。客户端最多多等 `retry_after` 秒，仍然是秒级，但服务端任何时候
#: 都留得下线程干正事。
#:
#: **默认值按"线程池最小的那种部署"来取，不按理想情况取**，因为取大了的后果
#: 是服务端卡死、取小了的后果只是客户端退化成短轮询（延迟仍是秒级）—— 两者
#: 严重程度完全不对等，所以要往小的一边站。
#: 实测（2026-09-29）生产机 192.168.5.35 的 `xinlv.service` 里 ExecStart **没有**
#: `--threads`，也就是 waitress 的默认值 **4** 个线程（`/proc/<pid>/task` 数出来
#: 是 5 = 4 个 worker + 主线程）。所以默认取 4 的一半 = 2，保证任何部署下都还剩
#: 至少 2 个线程接正常请求。
#:
#: 线程数提上去之后（`run_server.bat` 已经写成 `--threads=32`，Linux 的
#: `xinlv.service` 也要照做），再把这个数一起提上去，两边**必须成对改**：
#:     Environment=MOODTREE_WATCH_SLOTS=8
#: 单改一边就等于把线程池占满（8 条挂起 vs 4 个线程）。
WATCH_SLOTS = max(1, int(os.environ.get("MOODTREE_WATCH_SLOTS") or 0) or 2)

#: 拿不到名额时让客户端等多久再来（秒）。**必须给这个提示**：客户端分辨不出
#: "正常挂满 25 秒超时"（应当立刻再挂）和"名额满了被立刻打回"（立刻再挂就是
#: 热循环打服务器），只能靠服务端明确说一声。
BUSY_RETRY_AFTER_SECONDS = 1.0

_cond = threading.Condition()
_generation = 0
_slots = threading.BoundedSemaphore(WATCH_SLOTS)


def try_acquire_slot():
    """试着占一个"挂起名额"。拿不到返回 False，调用方应立刻回 `retry_after`。"""
    return _slots.acquire(blocking=False)


def release_slot():
    """还名额。**必须放在 finally 里** —— 客户端提前断开时 waitress 会抛异常，
    漏还几次名额之后长轮询就等于被永久关掉了。"""
    try:
        _slots.release()
    except ValueError:  # 还多了：说明调用方写错了，但绝不该因此把请求打成 500
        pass


def free_slots():
    """还剩几个名额（观测用：排查"为什么客户端在短轮询"时看）。"""
    return getattr(_slots, "_value", -1)


def bump():
    """有记录被写入/删除时调一次：叫醒所有正在等的人。"""
    global _generation
    with _cond:
        _generation += 1
        _cond.notify_all()


def generation():
    with _cond:
        return _generation


def wait_for_bump(since_generation, timeout):
    """等价于 `sleep(timeout)`，但只要有人 bump 就立刻醒。返回是否被 bump 叫醒。"""
    with _cond:
        if _generation != since_generation:
            return True
        _cond.wait(timeout)
        return _generation != since_generation


def wait_for_change(read_cursor, since_cursor, max_hold=None):
    """挂着等，直到 `read_cursor()` 算出来的光标和 `since_cursor` 不一样。

    返回 `(changed, cursor)`：`changed=False` 表示挂满超时了（客户端应立刻再挂一次）。
    `read_cursor` 是一个无参函数，返回当前光标字符串 —— 由调用方决定怎么算
    （见 `api._mood_cursor`），这里不碰数据库，方便单测。

    `max_hold=None` 表示用模块级的 `MAX_HOLD_SECONDS`。**注意是调用时才读**，
    不能写成默认参数值 —— 那是定义时就绑定了，改模块常量（或测试里 patch）
    不会生效（写这一版时就踩过，测试里挂了整整 25 秒）。
    """
    if max_hold is None:
        max_hold = MAX_HOLD_SECONDS
    deadline = time.monotonic() + max_hold
    current = read_cursor()
    if current != since_cursor:
        return True, current
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, read_cursor()
        gen = generation()
        wait_for_bump(gen, min(POLL_FALLBACK_SECONDS, remaining))
        current = read_cursor()
        if current != since_cursor:
            return True, current
