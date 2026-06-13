"""
OCR 完整工作流

包含：OCR识别 → 质量检查 → LLM优化 → 入库
"""

import os
import json
import sys
from typing import Optional

# 导入主模块的功能
try:
    from kb_query import (
        _ocr_paddle, _ocr_tesseract, _ocr_structured,
        _check_ocr_quality, ingest,
        print as kb_print
    )
except ImportError:
    # 如果作为独立模块运行
    import requests
    import re


def do_ocr(
    image_path: str,
    source: str = "",
    engine: str = "paddle",
    check_only: bool = False,
    collection: str = "zgptvector_v2",
    model: str = "qwen3-embedding:4b",
    llm_optimize: bool = False,
    llm_api_key: str = None,
    llm_base_url: str = None,
    llm_model: str = None,
) -> dict:
    """
    OCR 完整工作流：识别 → 质量检查 → LLM优化 → 入库
    
    参数:
        image_path: 图片路径
        source: 来源标识
        engine: OCR引擎 (paddle/tesseract/structured)
        check_only: 只识别不入库
        collection: Qdrant集合名
        model: 嵌入模型
        llm_optimize: 是否用LLM优化OCR结果
        llm_api_key: LLM API Key
        llm_base_url: LLM API地址
        llm_model: LLM模型名
    
    返回:
        {"ok": True/False, "text": "...", ...}
    """
    
    print(f"📷 开始OCR识别: {image_path}")
    print(f"   引擎: {engine}")
    
    # ── 第1步：OCR识别 ──
    ocr_result = None
    
    if engine == "paddle":
        ocr_result = _ocr_paddle(image_path)
    elif engine == "tesseract":
        ocr_result = _ocr_tesseract(image_path)
    elif engine == "structured":
        ocr_result = _ocr_structured(image_path)
    else:
        return {"ok": False, "error": f"不支持的OCR引擎: {engine}"}
    
    if not ocr_result.get("ok"):
        return {"ok": False, "error": f"OCR识别失败: {ocr_result.get('error')}"}
    
    ocr_text = ocr_result["text"]
    print(f"✅ OCR识别完成，识别文字数: {len(ocr_text)}")
    print(f"   预览: {ocr_text[:100]}...")
    
    # ── 第2步：质量检查 ──
    quality = _check_ocr_quality(ocr_result, image_path)
    print(f"\n📊 OCR质量检查:")
    print(f"   等级: {quality['grade']} (分数: {quality['score']})")
    if quality.get("issues"):
        print(f"   问题: {', '.join(quality['issues'])}")
    print(f"   建议: {quality['suggestion']}")
    
    # ── 第3步：LLM优化（可选）──
    optimized_text = ocr_text
    
    if llm_optimize and llm_api_key:
        print(f"\n🤖 开始LLM优化OCR结果...")
        
        try:
            # 导入LLM优化模块
            from ocr_llm_optimize import _llm_optimize_ocr, _format_ocr_optimization_result
            
            optimization = _llm_optimize_ocr(
                ocr_text=ocr_text,
                image_path=image_path,
                llm_api_key=llm_api_key,
                llm_base_url=llm_base_url or "https://api.deepseek.com/v1",
                llm_model=llm_model or "deepseek-chat",
                auto_fix=True
            )
            
            print(f"\n📊 LLM优化结果:")
            print(_format_ocr_optimization_result(optimization, image_path))
            
            if optimization.get("ok") and optimization.get("auto_fixed"):
                optimized_text = optimization["optimized_text"]
                print(f"\n✨ 已自动修复错误，优化后文字数: {len(optimized_text)}")
            elif optimization.get("ok") and not optimization.get("auto_fixed"):
                print(f"\n⚠️  OCR质量较差，建议重新拍摄/扫描")
                print(f"   问题: {optimization.get('suggestion', '')}")
                
                if check_only:
                    # check_only模式，显示优化建议但不入库
                    return {
                        "ok": False,
                        "error": "OCR质量较差",
                        "ocr_text": ocr_text,
                        "optimization": optimization,
                        "quality": quality
                    }
            else:
                print(f"\n⚠️  LLM优化失败: {optimization.get('error', '')}")
        
        except Exception as e:
            print(f"\n⚠️  LLM优化失败: {e}")
            print(f"   将使用原始OCR结果继续")
    
    elif llm_optimize and not llm_api_key:
        print(f"\n⚠️  未配置LLM API Key，跳过LLM优化")
    
    # ── 第4步：入库或预览 ──
    if check_only:
        print(f"\n📋 预览模式（不入库）")
        print(f"   最终文本: {optimized_text[:200]}...")
        return {
            "ok": True,
            "text": optimized_text,
            "ocr_text": ocr_text,
            "quality": quality,
            "check_only": True
        }
    
    # 入库
    print(f"\n💾 开始入库...")
    
    try:
        result = ingest(
            text=optimized_text,
            collection=collection,
            metadata={"file_name": source or os.path.basename(image_path), "source": source},
            model=model
        )
        
        if result.get("ok"):
            print(f"✅ 入库成功！")
            print(f"   切块数: {result.get('chunks', 0)}")
            print(f"   集合: {result.get('collection', '')}")
        else:
            print(f"❌ 入库失败: {result.get('error', '')}")
        
        return {
            "ok": result.get("ok", False),
            "text": optimized_text,
            "ocr_text": ocr_text,
            "quality": quality,
            "ingest_result": result
        }
    
    except Exception as e:
        print(f"❌ 入库失败: {e}")
        return {"ok": False, "error": str(e), "text": optimized_text}


def batch_ocr(
    image_dir: str,
    source_prefix: str = "",
    engine: str = "paddle",
    llm_optimize: bool = False,
    llm_api_key: str = None,
    **kwargs
) -> dict:
    """
    批量OCR：处理目录下的所有图片
    
    参数:
        image_dir: 图片目录
        source_prefix: 来源前缀
        engine: OCR引擎
        llm_optimize: 是否LLM优化
        llm_api_key: LLM API Key
        **kwargs: 其他参数传递给 do_ocr()
    
    返回:
        {"total": N, "success": N, "failed": N, "results": [...]}
    """
    
    if not os.path.isdir(image_dir):
        return {"ok": False, "error": f"目录不存在: {image_dir}"}
    
    # 支持的图片格式
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
    image_files = [
        os.path.join(image_dir, f)
        for f in os.listdir(image_dir)
        if os.path.splitext(f)[1].lower() in image_exts
    ]
    
    if not image_files:
        return {"ok": False, "error": f"目录中没有图片文件: {image_dir}"}
    
    print(f"📷 批量OCR: 找到 {len(image_files)} 张图片")
    
    results = []
    success = 0
    failed = 0
    
    for i, img_path in enumerate(image_files, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(image_files)}] {os.path.basename(img_path)}")
        print(f"{'='*60}")
        
        source = f"{source_prefix}/{os.path.basename(img_path)}" if source_prefix else os.path.basename(img_path)
        
        try:
            result = do_ocr(
                image_path=img_path,
                source=source,
                engine=engine,
                llm_optimize=llm_optimize,
                llm_api_key=llm_api_key,
                **kwargs
            )
            
            results.append(result)
            
            if result.get("ok"):
                success += 1
            else:
                failed += 1
        
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            results.append({"ok": False, "error": str(e), "image": img_path})
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"批量OCR完成: 成功 {success}/{len(image_files)}, 失败 {failed}/{len(image_files)}")
    print(f"{'='*60}")
    
    return {
        "ok": True,
        "total": len(image_files),
        "success": success,
        "failed": failed,
        "results": results
    }


if __name__ == "__main__":
    # 测试
    import argparse
    
    parser = argparse.ArgumentParser(description="OCR 完整工作流")
    parser.add_argument("image", help="图片路径或目录")
    parser.add_argument("--source", default="", help="来源标识")
    parser.add_argument("--engine", default="paddle", choices=["paddle", "tesseract", "structured"])
    parser.add_argument("--check-only", action="store_true", help="只识别不入库")
    parser.add_argument("--llm-optimize", action="store_true", help="LLM优化OCR结果")
    parser.add_argument("--llm-api-key", default=None, help="LLM API Key")
    parser.add_argument("--batch", action="store_true", help="批量处理目录")
    
    args = parser.parse_args()
    
    if args.batch:
        # 批量处理
        batch_ocr(
            image_dir=args.image,
            source_prefix=args.source,
            engine=args.engine,
            llm_optimize=args.llm_optimize,
            llm_api_key=args.llm_api_key,
            check_only=args.check_only
        )
    else:
        # 单张处理
        do_ocr(
            image_path=args.image,
            source=args.source,
            engine=args.engine,
            check_only=args.check_only,
            llm_optimize=args.llm_optimize,
            llm_api_key=args.llm_api_key
        )
