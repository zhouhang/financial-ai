"""
Chinese to Pinyin conversion utility
"""
from pypinyin import lazy_pinyin, Style
import re


def chinese_to_pinyin(text: str, separator: str = "_") -> str:
    """
    Convert Chinese text to Pinyin

    Args:
        text: Chinese text to convert
        separator: Separator between pinyin syllables (default: "_")

    Returns:
        Pinyin string in lowercase with separators

    Example:
        chinese_to_pinyin("货币资金数据整理") -> "huo_bi_zi_jin_shu_ju_zheng_li"
    """
    # Convert to pinyin
    pinyin_list = lazy_pinyin(text, style=Style.NORMAL)

    # Join with separator and convert to lowercase
    pinyin_str = separator.join(pinyin_list).lower()

    # Remove any non-alphanumeric characters except separator
    pinyin_str = re.sub(r'[^a-z0-9_]', '', pinyin_str)

    # Remove consecutive separators
    pinyin_str = re.sub(r'_+', '_', pinyin_str)

    # Remove leading/trailing separators
    pinyin_str = pinyin_str.strip('_')

    return pinyin_str


def generate_type_key(name_cn: str) -> str:
    """
    Generate a type_key from Chinese name

    Args:
        name_cn: Chinese name

    Returns:
        URL-safe type key

    Example:
        generate_type_key("货币资金数据整理") -> "huo_bi_zi_jin_shu_ju_zheng_li"
    """
    return chinese_to_pinyin(name_cn, separator="_")
