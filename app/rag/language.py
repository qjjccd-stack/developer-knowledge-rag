"""应用确定回答语言，并用本地语言识别检查正文；不把代码或引用当作回答语言。"""

import re
from functools import lru_cache

from langdetect.detector_factory import PROFILES_DIRECTORY, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException


def answer_language(question: str, requested: str = "auto") -> str:
    """检查显式 en/zh/auto；自动模式对含中文的本项目问题选择中文，否则英文。"""
    if requested not in {"auto", "en", "zh"}:
        raise ValueError("回答语言仅支持 auto、en、zh")
    if requested != "auto":
        return requested
    return "zh" if len(re.findall(r"[\u4e00-\u9fff]", question)) >= 2 else "en"


@lru_cache
def language_factory() -> DetectorFactory:
    """加载安装包自带的语言特征并固定 seed；每次检查创建独立检测器，避免共享请求状态。"""
    factory = DetectorFactory()
    factory.load_profile(PROFILES_DIRECTORY)
    factory.set_seed(0)
    return factory


def check_language(text: str, expected: str) -> dict:
    """移除代码和 URL 后识别正文；短技术表达记为不确定，高置信度外语判不匹配。"""
    prose = re.sub(r"```.*?```|`[^`]*`|https?://\S+", " ", text, flags=re.S)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", prose))
    latin = len(re.findall(r"[A-Za-z]", prose))
    if expected == "zh" and cjk >= 4:
        return {"expected": expected, "detected": "zh", "decision": "matched"}
    if expected == "en" and cjk >= 4:
        return {"expected": expected, "detected": "zh", "decision": "mismatch"}
    if latin < 30 and cjk < 4:
        return {"expected": expected, "detected": "unknown", "decision": "undetermined"}
    detector = language_factory().create()
    detector.append(prose)
    try:
        predictions = detector.get_probabilities()
    except LangDetectException:
        return {"expected": expected, "detected": "unknown", "decision": "undetermined"}
    first = predictions[0]
    detected = "zh" if first.lang.startswith("zh") else first.lang
    decision = (
        "matched" if detected == expected else "mismatch" if first.prob >= 0.8 else "undetermined"
    )
    return {
        "expected": expected,
        "detected": detected,
        "confidence": first.prob,
        "decision": decision,
    }
