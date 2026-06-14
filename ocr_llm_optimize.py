"""
OCR LLM 优化模块

OCR识别后，用LLM分析和优化识别结果：
1. 分析识别结果的准确性
2. 少量错别字 → 自动修复
3. 大量错误 → 反馈用户
"""

import json
import re
import requests
from typing import Optional


def _llm_optimize_ocr(
    ocr_text: str,
    image_path: str,
    llm_api_key: str,
    llm_base_url: str = "https://api.deepseek.com/v1",
    llm_model: str = "deepseek-chat",
    auto_fix: bool = True,
) -> dict:
    """
    OCR识别后，用LLM分析和优化识别结果
    
    参数:
        ocr_text: OCR识别的文本内容
        image_path: 原始图片路径（用于日志）
        llm_api_key: LLM API Key
        llm_base_url: LLM API地址
        llm_model: LLM模型名
        auto_fix: 是否自动修复少量错误
    
    返回:
        {
            "ok": True,
            "optimized_text": "...",  # 优化后的文本（如果auto_fix=True且错误少）
            "original_text": "...",    # 原始OCR文本
            "quality": "good|warn|bad",
            "issues": [...],           # 发现的问题
            "suggestion": "...",       # 建议
            "confidence": 0.95,        # LLM对优化结果的置信度
        }
    """
    
    if not llm_api_key:
        return {
            "ok": False,
            "error": "未配置LLM API Key，跳过LLM优化",
            "original_text": ocr_text,
        }
    
    # 构建Prompt
    prompt = f"""你是一个OCR结果优化专家。请分析以下OCR识别结果，判断其准确性，并修复错误。

## OCR识别结果：
```
{ocr_text}
```

## 任务：
1. 分析识别结果的准确性（检查错别字、漏字、多字、格式错误）
2. 如果错误较少（<5处），直接修复并返回优化后的文本
3. 如果错误较多（≥5处）或整段识别质量差，返回问题分析和使用建议

## 输出格式（严格JSON）：
```json
{{
    "quality": "good|warn|bad",
    "issues": ["问题1", "问题2"],
    "optimized_text": "优化后的文本（如果quality=good）",
    "suggestion": "使用建议（如果quality=warn或bad）"
}}
```

## 要求：
- quality=good: 错误≤2处，已自动修复
- quality=warn: 错误3-5处，已修复但建议用户检查
- quality=bad: 错误≥5处或识别质量差，建议重新拍摄/扫描
- 保留原始格式（换行、空格、标点）
- 不要添加不存在的内容
- 如果是公式/表格，保持原有结构
"""

    try:
        headers = {
            "Authorization": f"Bearer {llm_api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": llm_model,
            "messages": [
                {"role": "system", "content": "你是OCR结果优化专家，擅长中文技术文档的错别字修复和格式还原。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,  # 低温度，保证准确性
            "response_format": {"type": "json_object"},  # 强制JSON输出
        }
        
        resp = requests.post(
            f"{llm_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"LLM API调用失败: {resp.status_code} {resp.text[:200]}",
                "original_text": ocr_text,
            }
        
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        
        # 解析JSON
        try:
            analysis = json.loads(content)
        except json.JSONDecodeError:
            # 尝试从markdown代码块中提取JSON
            match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                analysis = json.loads(match.group(1))
            else:
                return {
                    "ok": False,
                    "error": "LLM返回格式错误",
                    "original_text": ocr_text,
                    "llm_raw_output": content,
                }
        
        quality = analysis.get("quality", "warn")
        issues = analysis.get("issues", [])
        optimized_text = analysis.get("optimized_text", ocr_text)
        suggestion = analysis.get("suggestion", "")
        
        # 如果质量是good/warn且开启了自动修复，返回优化后的文本
        if auto_fix and quality in ("good", "warn") and optimized_text:
            return {
                "ok": True,
                "optimized_text": optimized_text,
                "original_text": ocr_text,
                "quality": quality,
                "issues": issues,
                "suggestion": suggestion,
                "auto_fixed": True,
            }
        else:
            # 质量差或不自动修复，返回分析结果
            return {
                "ok": True,
                "optimized_text": None,
                "original_text": ocr_text,
                "quality": quality,
                "issues": issues,
                "suggestion": suggestion,
                "auto_fixed": False,
            }
    
    except Exception as e:
        return {
            "ok": False,
            "error": f"LLM优化失败: {e}",
            "original_text": ocr_text,
        }


def _format_ocr_optimization_result(result: dict, image_path: str = None) -> str:
    """
    格式化OCR优化结果，用于日志或用户反馈
    
    参数:
        result: _llm_optimize_ocr()的返回值
        image_path: 原始图片路径
    
    返回:
        格式化的文本
    """
    lines = []
    
    if image_path:
        lines.append(f"📷 图片: {image_path}")
    
    quality = result.get("quality", "unknown")
    if quality == "good":
        lines.append("✅ OCR质量: 良好（已自动优化）")
    elif quality == "warn":
        lines.append("⚠️ OCR质量: 一般（已修复，建议检查）")
    else:
        lines.append("❌ OCR质量: 差（建议重新拍摄/扫描）")
    
    issues = result.get("issues", [])
    if issues:
        lines.append(f"\n发现的问题（{len(issues)}处）:")
        for i, issue in enumerate(issues, 1):
            lines.append(f"  {i}. {issue}")
    
    suggestion = result.get("suggestion", "")
    if suggestion:
        lines.append(f"\n💡 建议: {suggestion}")
    
    if result.get("auto_fixed"):
        lines.append("\n✨ 已自动修复错误")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    test_text = "齿轮的模数m=2.5，齿数z=20，外径da=55mm。"
    
    # 模拟OCR错误
    test_text_with_errors = "齿轮的模数m=2.5，齿数z=20，外径da=55mm。"  # 正确
    # test_text_with_errors = "齿轮的模数m=2.5，齿数z=20，外径da=55mm。"  # 错误：模→摸
    
    print("测试OCR LLM优化...")
    print(f"原始文本: {test_text_with_errors}")
    print("\n（需要配置LLM API Key才能实际运行）")
