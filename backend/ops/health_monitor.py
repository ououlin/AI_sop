"""设备健康度评估。

在线状态由 AggregationServer 的心跳超时判定；
在此基础上结合摄像头、帧率、上报延迟给出 healthy / warning / offline。
"""

from typing import List, Tuple

DEFAULT_MIN_FPS = 5.0
DEFAULT_MAX_LATENCY_MS = 500.0


def evaluate(
    info,
    min_fps: float = DEFAULT_MIN_FPS,
    max_latency_ms: float = DEFAULT_MAX_LATENCY_MS,
) -> Tuple[str, List[str]]:
    """返回 (健康状态, 问题列表)。"""
    if not info.is_online:
        return "offline", ["心跳超时"]

    issues: List[str] = []
    if not getattr(info, "camera_ok", True):
        issues.append("摄像头异常")
    fps = getattr(info, "fps", 0.0) or 0.0
    if fps < min_fps:
        issues.append("帧率过低 {:.1f}".format(fps))
    latency = getattr(info, "latency_ms", 0.0) or 0.0
    if latency > max_latency_ms:
        issues.append("上报延迟 {:.0f}ms".format(latency))

    return ("warning" if issues else "healthy"), issues
