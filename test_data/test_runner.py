#!/usr/bin/env python3
"""
KnowledgeForge 自动化测试套件
用法: python test_runner.py [--phase 1|2|3|all] [--verbose]
"""

import os
import sys
import json
import subprocess
import time
import traceback
import argparse
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DATA_DIR = os.path.join(PROJECT_ROOT, "test_data")
PYTHON = r"C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe"

# 测试报告
RESULTS = []
PASS = 0
FAIL = 0
SKIP = 0


def log(phase: str, name: str, status: str, detail: str = ""):
    global PASS, FAIL, SKIP
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "INFO": "ℹ️"}.get(status, "•")
    print(f"  {icon} [{phase}] {name}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"      {line}")
    RESULTS.append({"phase": phase, "name": name, "status": status, "detail": detail, "time": datetime.now().isoformat()})
    if status == "PASS":
        PASS += 1
    elif status == "FAIL":
        FAIL += 1
    else:
        SKIP += 1


def run(cmd: list, timeout: int = 60, env: dict = None) -> tuple[int, str, str]:
    """运行命令，返回 (returncode, stdout, stderr)"""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, cwd=PROJECT_ROOT, env=full_env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)


# ═══════════════════════════════════════════
# PHASE 1: 冒烟测试
# ═══════════════════════════════════════════

def phase1_smoke():
    print("\n" + "=" * 60)
    print("  PHASE 1: 冒烟测试 (Smoke Tests)")
    print("=" * 60)

    # 1.1 Python 语法检查
    print("\n  [1.1] Python 语法编译检查")
    py_files = [
        "kb_query.py", "app.py", "ocr_workflow.py",
        "ocr_llm_optimize.py", "sync_ima.py",
        "utils/flame_bg.py", "config/classifications.py"
    ]
    for f in py_files:
        fp = os.path.join(PROJECT_ROOT, f)
        if not os.path.exists(fp):
            log("1.1", f"文件存在: {f}", "FAIL", f"文件不存在: {fp}")
            continue
        rc, out, err = run([PYTHON, "-m", "py_compile", fp])
        if rc == 0:
            log("1.1", f"语法检查: {f}", "PASS")
        else:
            log("1.1", f"语法检查: {f}", "FAIL", err)

    # 1.2 Qdrant 连接
    print("\n  [1.2] Qdrant 服务检查")
    import requests
    try:
        resp = requests.get("http://localhost:6333/", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            log("1.2", "Qdrant 连接", "PASS", f"版本: {data.get('version', 'unknown')}")
        else:
            log("1.2", "Qdrant 连接", "FAIL", f"HTTP {resp.status_code}")
    except Exception as e:
        log("1.2", "Qdrant 连接", "FAIL", str(e))

    # 1.3 Ollama 连接 + embedding 模型
    print("\n  [1.3] Ollama 服务检查")
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            log("1.3", "Ollama 连接", "PASS", f"模型数: {len(models)}")
            # 检查 embedding 模型
            if "qwen3-embedding:4b" in models:
                log("1.3", "Embedding 模型", "PASS", "qwen3-embedding:4b 可用")
            else:
                log("1.3", "Embedding 模型", "FAIL", "qwen3-embedding:4b 未找到")
        else:
            log("1.3", "Ollama 连接", "FAIL", f"HTTP {resp.status_code}")
    except Exception as e:
        log("1.3", "Ollama 连接", "FAIL", str(e))

    # 1.4 模块导入检查
    print("\n  [1.4] 模块导入检查")
    rc, out, err = run([PYTHON, "-c", "import kb_query; print('OK')"])
    if rc == 0:
        log("1.4", "kb_query 导入", "PASS")
    else:
        log("1.4", "kb_query 导入", "FAIL", err)

    rc, out, err = run([PYTHON, "-c", "from config.classifications import CLASSIFICATION_SCHEMES; print(len(CLASSIFICATION_SCHEMES))"])
    if rc == 0:
        log("1.4", "config.classifications 导入", "PASS", f"{out.strip()} 个分类法")
    else:
        log("1.4", "config.classifications 导入", "FAIL", err)

    # 1.5 环境变量检查
    print("\n  [1.5] 环境变量检查")
    env_vars = ["KB_TESSERACT_PATH", "KB_TESSDATA_PREFIX", "KB_NODE_BIN", "KB_NPM_ROOT"]
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            exists = os.path.exists(val) if val else False
            if exists:
                log("1.5", f"{var}", "PASS", val)
            else:
                log("1.5", f"{var}", "SKIP", f"已设置但路径不存在: {val}")
        else:
            log("1.5", f"{var}", "SKIP", "未设置（将使用默认值）")


# ═══════════════════════════════════════════
# PHASE 2: 功能测试
# ═══════════════════════════════════════════

def phase2_functional():
    print("\n" + "=" * 60)
    print("  PHASE 2: 功能测试 (Functional Tests)")
    print("=" * 60)

    TEST_COLLECTION = "test_zgpt_vector"

    # 2.1 帮助信息
    print("\n  [2.1] CLI 帮助")
    rc, out, err = run([PYTHON, "kb_query.py", "--help"])
    if rc == 0 and "usage" in out.lower():
        log("2.1", "--help 输出", "PASS")
    else:
        log("2.1", "--help 输出", "FAIL", out[:500])

    # 2.2 摄入测试 - 中文技术文档
    print("\n  [2.2] 摄入测试")
    test_files = [
        ("齿轮设计基础.txt", "机械-手册"),
        ("产品运营笔记.txt", "产品-运营"),
        ("edge_cases.txt", "测试-边界"),
    ]
    for fname, source in test_files:
        fp = os.path.join(TEST_DATA_DIR, fname)
        if not os.path.exists(fp):
            log("2.2", f"测试文件: {fname}", "SKIP", "文件不存在")
            continue
        rc, out, err = run([
            PYTHON, "kb_query.py", "--ingest", fp,
            "--source", source, "--collection", TEST_COLLECTION
        ], timeout=120)
        if rc == 0:
            log("2.2", f"摄入: {fname}", "PASS", _extract_summary(out))
        else:
            log("2.2", f"摄入: {fname}", "FAIL", err[:500])

    # 2.3 纯文本摄入 (--text)
    print("\n  [2.3] 纯文本摄入 (--text)")
    rc, out, err = run([
        PYTHON, "kb_query.py", "--text", "纯文本测试内容：RAG检索增强生成技术。",
        "--source", "测试-纯文本", "--collection", TEST_COLLECTION
    ])
    if rc == 0:
        log("2.3", "--text 摄入", "PASS", _extract_summary(out))
    else:
        log("2.3", "--text 摄入", "FAIL", err[:500])

    # 2.4 搜索测试
    print("\n  [2.4] 搜索测试")
    search_queries = [
        ("齿轮失效", "中文技术搜索"),
        ("智能家居", "中文运营搜索"),
        ("Transformer attention", "英文技术搜索"),
        ("RAG检索增强", "短文本搜索"),
    ]
    for query, desc in search_queries:
        rc, out, err = run([
            PYTHON, "kb_query.py", query, "--top", "3",
            "--collection", TEST_COLLECTION, "--threshold", "0.1"
        ])
        if rc == 0:
            try:
                data = json.loads(out)
                n_chunks = len(data.get("chunks", []))
                log("2.4", f"搜索: {desc} ({query})", "PASS" if n_chunks > 0 else "FAIL",
                    f"返回 {n_chunks} 条结果 (阈值 0.1)")
            except json.JSONDecodeError:
                log("2.4", f"搜索: {desc} ({query})", "FAIL", f"JSON 解析失败: {out[:200]}")
        else:
            log("2.4", f"搜索: {desc} ({query})", "FAIL", err[:300])

    # 2.5 去重测试
    print("\n  [2.5] 去重测试")
    rc, out, err = run([
        PYTHON, "kb_query.py", "--ingest", fp,  # 重复摄入齿轮设计
        "--source", "机械-重复测试", "--collection", TEST_COLLECTION
    ], timeout=120)
    if rc == 0:
        # 期望检测到重复
        if "重复" in out or "已跳过" in out:
            log("2.5", "去重检测", "PASS", "正确识别重复内容")
        else:
            log("2.5", "去重检测", "FAIL", "未检测到重复内容")
    else:
        log("2.5", "去重检测", "FAIL", err[:300])

    # 2.6 问答测试 (需要 LLM API Key)
    print("\n  [2.6] 问答测试 (需要 LLM API)")
    api_key = os.environ.get("KB_LLM_API_KEY") or _read_env_key()
    if not api_key:
        log("2.6", "LLM 问答", "SKIP", "未配置 KB_LLM_API_KEY")
    else:
        rc, out, err = run([
            PYTHON, "kb_query.py", "齿轮的失效形式有哪些",
            "--answer", "--top", "5", "--collection", TEST_COLLECTION,
            "--threshold", "0.1"
        ], timeout=120, env={"KB_LLM_API_KEY": api_key})
        if rc == 0:
            try:
                data = json.loads(out)
                if data.get("ok"):
                    has_html = bool(data.get("html"))
                    synthesis_len = len(data.get("synthesis", ""))
                    log("2.6", "LLM 问答", "PASS",
                        f"回答长度: {synthesis_len} 字符, HTML: {'是' if has_html else '否'}")
                else:
                    log("2.6", "LLM 问答", "FAIL", data.get("error", "未知错误"))
            except json.JSONDecodeError:
                log("2.6", "LLM 问答", "FAIL", f"JSON 解析失败: {out[:300]}")
        else:
            log("2.6", "LLM 问答", "FAIL", err[:500])

    # 2.7 HTML 报告生成
    print("\n  [2.7] HTML 报告检查")
    reports_dir = os.path.join(PROJECT_ROOT, "local_data", "reports")
    html_files = [f for f in os.listdir(reports_dir) if f.endswith(".html")]
    if html_files:
        latest = max(html_files)  # 按文件名排序
        log("2.7", "HTML 报告", "PASS", f"最新报告: {latest} (共 {len(html_files)} 个)")
    else:
        log("2.7", "HTML 报告", "SKIP", "无 HTML 报告（可能未运行过问答）")


# ═══════════════════════════════════════════
# PHASE 3: 边界 / 压力测试
# ═══════════════════════════════════════════

def phase3_edge_cases():
    print("\n" + "=" * 60)
    print("  PHASE 3: 边界与压力测试 (Edge Cases)")
    print("=" * 60)

    TEST_COLLECTION = "test_zgpt_vector"

    # 3.1 空查询
    print("\n  [3.1] 空查询")
    rc, out, err = run([PYTHON, "kb_query.py"], timeout=10)
    if rc == 0:
        log("3.1", "无参数运行", "PASS", "正确显示帮助信息")
    else:
        log("3.1", "无参数运行", "FAIL", err[:200])

    # 3.2 无结果查询
    print("\n  [3.2] 无结果查询（高阈值）")
    rc, out, err = run([
        PYTHON, "kb_query.py", "xyzabc123不存在的查询",
        "--collection", TEST_COLLECTION, "--threshold", "0.9"
    ])
    if rc == 0:
        try:
            data = json.loads(out)
            if data.get("ok") and len(data.get("chunks", [])) == 0:
                log("3.2", "高阈值无结果", "PASS", "正确返回空结果")
            else:
                log("3.2", "高阈值无结果", "FAIL", f"返回了 {len(data.get('chunks', []))} 条结果")
        except json.JSONDecodeError:
            log("3.2", "高阈值无结果", "FAIL", f"JSON 解析失败: {out[:200]}")
    else:
        log("3.2", "高阈值无结果", "FAIL", err[:200])

    # 3.3 搜索含特殊字符的查询
    print("\n  [3.3] 特殊字符查询")
    special_queries = [
        ("α β γ 数学符号", "希腊字母"),
        ("E = mc²", "物理公式"),
        ("智能家居 KPI GMV", "中英混合缩写"),
    ]
    for query, desc in special_queries:
        rc, out, err = run([
            PYTHON, "kb_query.py", query,
            "--collection", TEST_COLLECTION, "--threshold", "0.1"
        ])
        if rc == 0:
            try:
                data = json.loads(out)
                log("3.3", f"特殊字符: {desc}", "PASS" if data.get("ok") else "FAIL",
                    f"返回 {len(data.get('chunks', []))} 条")
            except json.JSONDecodeError:
                log("3.3", f"特殊字符: {desc}", "FAIL", f"JSON 解析失败: {out[:150]}")
        else:
            log("3.3", f"特殊字符: {desc}", "FAIL", err[:150])

    # 3.4 短文本摄入
    print("\n  [3.4] 短文本摄入")
    fp = os.path.join(TEST_DATA_DIR, "short_text.txt")
    if os.path.exists(fp):
        rc, out, err = run([
            PYTHON, "kb_query.py", "--ingest", fp,
            "--source", "测试-短文本", "--collection", TEST_COLLECTION
        ], timeout=60)
        if rc == 0:
            log("3.4", "短文本摄入", "PASS", _extract_summary(out))
        else:
            log("3.4", "短文本摄入", "FAIL", err[:300])
    else:
        log("3.4", "短文本摄入", "SKIP", "short_text.txt 不存在")

    # 3.5 Markdown 摄入（含表格/公式）
    print("\n  [3.5] Markdown 摄入")
    fp = os.path.join(TEST_DATA_DIR, "AI_Research_Notes.md")
    if os.path.exists(fp):
        rc, out, err = run([
            PYTHON, "kb_query.py", "--ingest", fp,
            "--source", "AI-研究笔记", "--collection", TEST_COLLECTION
        ], timeout=60)
        if rc == 0:
            log("3.5", "Markdown 摄入", "PASS", _extract_summary(out))
        else:
            log("3.5", "Markdown 摄入", "FAIL", err[:300])
    else:
        log("3.5", "Markdown 摄入", "SKIP", "AI_Research_Notes.md 不存在")

    # 3.6 分类法检查
    print("\n  [3.6] 分类法配置检查")
    sys.path.insert(0, PROJECT_ROOT)
    try:
        from config.classifications import CLASSIFICATION_SCHEMES
        for scheme_id, scheme in CLASSIFICATION_SCHEMES.items():
            collections = scheme.get("collections", {})
            if collections:
                log("3.6", f"分类法: {scheme_id}", "PASS",
                    f"{scheme['label']} — {len(collections)} 个集合")
            else:
                log("3.6", f"分类法: {scheme_id}", "FAIL", "无集合定义")
    except Exception as e:
        log("3.6", "分类法导入", "FAIL", str(e))

    # 3.7 清理测试数据
    print("\n  [3.7] 清理测试集合")
    rc, out, err = run([
        PYTHON, "-c", f"""
import requests, json
r = requests.delete("http://localhost:6333/collections/{TEST_COLLECTION}")
print(r.status_code, r.text[:200])
"""
    ])
    if rc == 0:
        log("3.7", f"删除测试集合 {TEST_COLLECTION}", "PASS", out.strip())
    else:
        log("3.7", f"删除测试集合 {TEST_COLLECTION}", "FAIL", err[:200])


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _extract_summary(out: str) -> str:
    """从摄入输出中提取摘要"""
    lines = [l.strip() for l in out.split("\n") if l.strip()]
    return "\n".join(lines[:5])


def _read_env_key() -> str:
    """从 .env 文件读取 API Key"""
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("KB_LLM_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def print_summary():
    total = PASS + FAIL + SKIP
    print("\n" + "=" * 60)
    print("  测试总结")
    print("=" * 60)
    print(f"  总计: {total}  |  ✅ 通过: {PASS}  |  ❌ 失败: {FAIL}  |  ⏭️ 跳过: {SKIP}")
    print("=" * 60)

    # 输出 JSON 报告
    report_path = os.path.join(TEST_DATA_DIR, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {"total": total, "pass": PASS, "fail": FAIL, "skip": SKIP},
            "results": RESULTS
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 详细报告已保存: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="KnowledgeForge 测试套件")
    parser.add_argument("--phase", default="all", choices=["1", "2", "3", "all"],
                        help="运行阶段: 1=冒烟, 2=功能, 3=边界, all=全部")
    parser.add_argument("--skip-cleanup", action="store_true", help="跳过清理测试集合")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║     KnowledgeForge 自动化测试套件                    ║")
    print(f"║     时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          ║")
    print("╚══════════════════════════════════════════════════════╝")

    if args.phase in ("1", "all"):
        phase1_smoke()
    if args.phase in ("2", "all"):
        phase2_functional()
    if args.phase in ("3", "all"):
        phase3_edge_cases()

    report_path = print_summary()
    return report_path


if __name__ == "__main__":
    main()
