"""
Citrinitas · 熔知 — LLM 辅助函数

包含与 LLM 交互相关的共享工具函数。
"""
import json
import re


def extract_json_block(text: str) -> dict:
    """
    从 LLM 返回文本中提取并解析 JSON 对象（支持嵌套）。
    
    策略：
      1. 先尝试直接 json.loads()（LLM 可能返回纯净 JSON）
      2. 失败则找第一个 '{'，然后匹配花括号（计数深度），提取最外层 JSON
      3. 对提取的块尝试 json.loads()
    
    返回:
        dict — 解析成功
        None — 无法提取/解析
    """
    text = text.strip()
    
    # 策略1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 策略2：提取 JSON 块（匹配花括号）
    start = text.find("{")
    if start == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    json_end = -1
    
    for i in range(start, len(text)):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break
    
    if json_end == -1:
        return None
    
    json_block = text[start:json_end]
    try:
        return json.loads(json_block)
    except json.JSONDecodeError:
        # 尝试修复常见错误：去掉尾部逗号
        json_block = re.sub(r",\s*}", "}", json_block)
        json_block = re.sub(r",\s*\]", "]", json_block)
        try:
            return json.loads(json_block)
        except json.JSONDecodeError:
            return None
