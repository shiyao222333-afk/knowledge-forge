#!/usr/bin/env python3
"""Fix C10: add logging to 6 except:pass locations in kb_query.py."""
import re

with open('D:/citrinitas/kb_query.py', 'r', encoding='utf-8') as f:
    content = f.read()

count = 0

# Fix 1: L495-496 PPStructure 失败回退 PaddleOCR
old1 = '    except Exception:\n        pass  # 回退到 PaddleOCR'
new1 = '    except Exception as e:\n        logger.warning(f"[OCR] PPStructure 失败，回退到 PaddleOCR: {e}")'
if old1 in content:
    content = content.replace(old1, new1, 1)
    count += 1
    print("✅ Fix 1: L495-496 PPStructure 回退 PaddleOCR")
else:
    print("❌ Fix 1: 原字符串未找到")

# Fix 2: L636-637 批量嵌入失败回退逐条
old2 = '    except Exception:\n        pass  # 回退到逐条'
new2 = '    except Exception as e:\n        logger.warning(f"[Embed] 批量嵌入失败，回退到逐条: {e}")'
if old2 in content:
    content = content.replace(old2, new2, 1)
    count += 1
    print("✅ Fix 2: L636-637 批量嵌入回退逐条")
else:
    print("❌ Fix 2: 原字符串未找到")

# Fix 3: L776-777 索引已存在（create_collection 内层）
old3 = '                except Exception:\n                    pass  # 索引已存在或创建失败，不影响主流程'
new3 = '                except Exception as e:\n                    logger.warning(f"[Qdrant] Payload 索引创建失败（可忽略）: {e}")'
if old3 in content:
    content = content.replace(old3, new3, 1)
    count += 1
    print("✅ Fix 3: L776-777 Payload 索引创建失败")
else:
    print("❌ Fix 3: 原字符串未找到")

# Fix 4: L823-824 Payload 索引创建失败（create_collection 外层）
old4 = '            except Exception:\n                pass'
new4 = '            except Exception as e:\n                logger.warning(f"[Qdrant] 集合创建异常（可忽略）: {e}")'
if old4 in content:
    content = content.replace(old4, new4, 1)
    count += 1
    print("✅ Fix 4: L823-824 集合创建异常")
else:
    print("❌ Fix 4: 原字符串未找到")

# Fix 5: L991-992 日志写入失败
old5 = '    except Exception:\n        pass  # 日志写入失败不影响主流程'
new5 = '    except Exception as e:\n        logger.warning(f"[IngestLog] 日志写入失败（可忽略）: {e}")'
if old5 in content:
    content = content.replace(old5, new5, 1)
    count += 1
    print("✅ Fix 5: L991-992 日志写入失败")
else:
    print("❌ Fix 5: 原字符串未找到")

# Fix 6: L1012-1013 scroll 单页失败
old6 = '                except Exception:\n                    continue'
new6 = '                except Exception as e:\n                    logger.warning(f"[Scroll] 分页读取失败（跳过此页）: {e}")\n                    continue'
# 需要更精确的匹配（包含上下文）
old6_big = '                    entries.append(json.loads(line))\n                except Exception:\n                    continue'
new6_big = '                    entries.append(json.loads(line))\n                except Exception as e:\n                    logger.warning(f"[Scroll] 分页读取失败（跳过此页）: {e}")\n                    continue'
if old6_big in content:
    content = content.replace(old6_big, new6_big, 1)
    count += 1
    print("✅ Fix 6: L1012-1013 scroll 单页失败")
else:
    print("❌ Fix 6: 原字符串未找到（尝试模糊匹配）")
    # 模糊：直接搜 except Exception:\n                    continue
    if '                except Exception:\n                    continue' in content:
        content = content.replace(
            '                except Exception:\n                    continue',
            '                except Exception as e:\n                    logger.warning(f"[Scroll] 分页读取失败（跳过此页）: {e}")\n                    continue',
            1
        )
        count += 1
        print("  ✅ Fix 6 (模糊): 已修复")
    else:
        print("  ❌ Fix 6: 模糊匹配也未找到")

print(f"\n共修复 {count}/6 处")
if count == 6:
    with open('D:/citrinitas/kb_query.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 已写入 kb_query.py")
else:
    print("⚠️  有未匹配的项，未写入文件")
