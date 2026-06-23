"""
Citrinitas Watch Folder — 守望文件夹自动摄入守护进程

文件进入 data/watch/ → 写入完成检测 → staging → 分类+摄入 → processed/DLQ

用法（由 main.py 自动启动）:
    from watcher import start_watcher, stop_watcher
    watcher_thread = start_watcher()
    # ... app runs ...
    stop_watcher()
"""

import os
import sys
import time
import json
import shutil
import fnmatch
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from queue import Queue, Empty

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import (
    PROJECT_DIR,
    WATCH_POLL_INTERVAL,
    WATCH_WRITE_COMPLETE_CHECKS,
    WATCH_WRITE_CHECK_INTERVAL,
    WATCH_MAX_FILE_SIZE_MB,
    WATCH_PROCESSING_TIMEOUT,
    WATCH_DLQ_MAX_SIZE_MB,
    WATCH_DLQ_TTL_DAYS,
    WATCH_PROCESSED_TTL_DAYS,
    WATCH_STAGING_TTL_DAYS,
    WATCH_INFRA_RETRY_INTERVAL,
    WATCH_QUEUE_MAX_SIZE,
    WATCH_TEMP_PATTERNS,
)
from qconst import QDRANT_URL, OLLAMA_URL
from utils.activity_log import log_activity

# ═══════════════════════════════════════════
# 路径定义
# ═══════════════════════════════════════════

WATCH_DIR = os.path.join(PROJECT_DIR, "data", "watch")
STAGING_DIR = os.path.join(PROJECT_DIR, "data", "watch_staging")
PROCESSED_DIR = os.path.join(PROJECT_DIR, "data", "watch_processed")
DLQ_DIR = os.path.join(PROJECT_DIR, "data", "watch_dead_letter")
LOCK_FILE = os.path.join(PROJECT_DIR, "data", ".watch.lock")

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════

_observer: Observer | None = None
_worker_thread: threading.Thread | None = None
_queue: Queue | None = None
_stop_event: threading.Event | None = None
_heartbeat_time: float = 0.0
_heartbeat_lock = threading.Lock()
_watch_stats: dict = {
    "processed": 0,
    "failed": 0,
    "skipped": 0,
    "dlq_count": 0,
    "running": False,
    "infra_ok": True,
}


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _is_temp_file(filename: str) -> bool:
    """检查是否为临时文件（Office ~$/下载中/系统文件）。"""
    for pattern in WATCH_TEMP_PATTERNS:
        if fnmatch.fnmatch(filename.lower(), pattern.lower()):
            return True
    return False


# ── OCR 就绪状态（延迟初始化）──
_ocr_ready: bool | None = None  # None=未检查, True=就绪, False=不可用


def _check_ocr_ready() -> bool:
    """检查 OCR 引擎是否可用（轻量级导入检查，不加载模型）。返回 True/False。"""
    global _ocr_ready
    if _ocr_ready is not None:
        return _ocr_ready

    try:
        from paddleocr import PaddleOCR
        _ocr_ready = True
    except ImportError:
        _ocr_ready = False
        log_activity(
            action="watch_ocr_unavailable",
            detail="PaddleOCR 未安装，图片文件将入 DLQ",
        )
    return _ocr_ready


def _is_write_complete(filepath: str) -> bool:
    """轮询文件大小，连续 N 次不变 → 认为写入完成。"""
    checks = WATCH_WRITE_COMPLETE_CHECKS
    interval = WATCH_WRITE_CHECK_INTERVAL
    last_size = -1
    stable_count = 0
    lock_retry_max = 3  # 文件被锁时最多重试 3 次

    for _ in range(checks * 2):  # 最多等 checks*2 轮，防止无限等
        lock_retries = 0
        while lock_retries < lock_retry_max:
            try:
                current_size = os.path.getsize(filepath)
                break  # 成功读取
            except PermissionError:
                lock_retries += 1
                if lock_retries >= lock_retry_max:
                    return False  # 文件被锁太久，跳过
                time.sleep(interval * 2)
            except OSError:
                return False  # 文件被删了

        if current_size == last_size:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
            last_size = current_size
        time.sleep(interval)

    return False  # 超时仍未稳定


def _check_infra() -> dict:
    """检查基础设施健康状态。返回 {"qdrant": bool, "ollama": bool}。"""
    result = {"qdrant": False, "ollama": False}

    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        result["qdrant"] = resp.status_code == 200
    except Exception:
        pass

    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        result["ollama"] = resp.status_code == 200
    except Exception:
        pass

    return result


def _ensure_dir(path: str):
    """确保目录存在。"""
    os.makedirs(path, exist_ok=True)


def _move_or_copy(src: str, dst_dir: str) -> str:
    """将文件移入目标目录。跨盘时回退到复制+删除。"""
    _ensure_dir(dst_dir)
    dst = os.path.join(dst_dir, os.path.basename(src))

    # 同名文件加时间戳
    if os.path.exists(dst):
        name, ext = os.path.splitext(os.path.basename(src))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(dst_dir, f"{name}_{ts}{ext}")

    try:
        shutil.move(src, dst)
    except OSError:
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except OSError:
            pass

    return dst


def _move_to_staging(filepath: str) -> str | None:
    """将文件从 watch/ 移到 staging/。返回 staging 路径或 None。"""
    try:
        return _move_or_copy(filepath, STAGING_DIR)
    except Exception as e:
        log_activity(
            action="watch_staging_failed",
            detail=f"无法移入 staging: {e}",
            source=os.path.basename(filepath),
        )
        return None


def _check_disk_space(min_mb: int = 50) -> bool:
    """检查 DLQ 所在磁盘是否有足够空间。返回 True = 够用。"""
    try:
        import shutil
        usage = shutil.disk_usage(DLQ_DIR)
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= min_mb
    except Exception:
        return True  # 无法检查时保守允许


def _move_to_dlq(filepath: str, error: str, step: str) -> str | None:
    """将文件移入 DLQ，同时写入 .meta.json。返回 DLQ 路径。"""
    # 磁盘空间检查
    if not _check_disk_space(min_mb=50):
        log_activity(
            action="watch_disk_full",
            detail="磁盘空间不足 (<50MB)，无法写入 DLQ。文件保留在 staging。",
            source=os.path.basename(filepath),
        )
        return None

    try:
        dst = _move_or_copy(filepath, DLQ_DIR)
        meta = {
            "original_name": os.path.basename(filepath),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "failed_step": step,
            "error": error,
            "retry_count": 0,
        }
        meta_path = dst + ".meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except IOError as e:
            # .meta.json 写入失败 → 删除已移动的 DLQ 文件，报告失败
            log_activity(
                action="watch_meta_write_failed",
                detail=f".meta.json 写入失败 (磁盘满/权限): {e}",
                source=os.path.basename(filepath),
            )
            try:
                if os.path.isfile(dst):
                    os.remove(dst)
            except OSError:
                pass
            return None

        _watch_stats["failed"] += 1
        _watch_stats["dlq_count"] = _count_dlq()

        log_activity(
            action="watch_dlq",
            detail=f"[{step}] {error}",
            source=os.path.basename(filepath),
        )
        return dst
    except Exception as e:
        log_activity(
            action="watch_dlq_failed",
            detail=f"无法移入 DLQ: {e}",
            source=os.path.basename(filepath),
        )
        return None


def _move_to_processed(filepath: str):
    """将处理完成的文件移入 processed/。"""
    try:
        _move_or_copy(filepath, PROCESSED_DIR)
        _watch_stats["processed"] += 1
    except Exception as e:
        log_activity(
            action="watch_processed_failed",
            detail=f"无法移入 processed: {e}",
            source=os.path.basename(filepath),
        )


def _count_dlq() -> int:
    """统计 DLQ 中的条目数（.meta.json 文件数）。"""
    try:
        if not os.path.isdir(DLQ_DIR):
            return 0
        return len([f for f in os.listdir(DLQ_DIR) if f.endswith(".meta.json")])
    except Exception:
        return 0


def _dlq_size_mb() -> float:
    """计算 DLQ 目录总大小（MB）。"""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(DLQ_DIR):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        pass
    return total / (1024 * 1024)


# ═══════════════════════════════════════════
# 清理函数
# ═══════════════════════════════════════════

def _recover_orphans():
    """启动时扫描 staging/，将孤儿文件移回 watch/。"""
    if not os.path.isdir(STAGING_DIR):
        return

    count = 0
    for filename in os.listdir(STAGING_DIR):
        filepath = os.path.join(STAGING_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        if _is_temp_file(filename):
            try:
                os.remove(filepath)
            except OSError:
                pass
            continue
        try:
            _move_or_copy(filepath, WATCH_DIR)
            count += 1
        except Exception:
            pass

    if count > 0:
        log_activity(
            action="watch_orphan_recovery",
            detail=f"从 staging 恢复 {count} 个文件到 watch/",
        )


def _cleanup_dlq():
    """清理过期 DLQ 条目。"""
    if WATCH_DLQ_TTL_DAYS <= 0 or not os.path.isdir(DLQ_DIR):
        return

    now = time.time()
    ttl_seconds = WATCH_DLQ_TTL_DAYS * 86400
    removed = 0

    for filename in os.listdir(DLQ_DIR):
        filepath = os.path.join(DLQ_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            if now - os.path.getmtime(filepath) > ttl_seconds:
                os.remove(filepath)
                # 同时删除对应的 .meta.json
                meta_path = filepath + ".meta.json"
                if os.path.exists(meta_path):
                    os.remove(meta_path)
                removed += 1
        except OSError:
            pass

    if removed > 0:
        log_activity(
            action="watch_dlq_cleanup",
            detail=f"自动清理 {removed} 条过期 DLQ 条目",
        )
    _watch_stats["dlq_count"] = _count_dlq()


def _cleanup_processed():
    """清理过期的已处理文件。"""
    if WATCH_PROCESSED_TTL_DAYS <= 0 or not os.path.isdir(PROCESSED_DIR):
        return

    now = time.time()
    ttl_seconds = WATCH_PROCESSED_TTL_DAYS * 86400
    removed = 0

    for filename in os.listdir(PROCESSED_DIR):
        filepath = os.path.join(PROCESSED_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            if now - os.path.getmtime(filepath) > ttl_seconds:
                os.remove(filepath)
                removed += 1
        except OSError:
            pass

    if removed > 0:
        log_activity(
            action="watch_processed_cleanup",
            detail=f"自动清理 {removed} 个过期已处理文件",
        )


def _cleanup_staging():
    """清理 staging 中的过期孤儿文件。"""
    if WATCH_STAGING_TTL_DAYS <= 0 or not os.path.isdir(STAGING_DIR):
        return

    now = time.time()
    ttl_seconds = WATCH_STAGING_TTL_DAYS * 86400
    removed = 0

    for filename in os.listdir(STAGING_DIR):
        filepath = os.path.join(STAGING_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            if now - os.path.getmtime(filepath) > ttl_seconds:
                os.remove(filepath)
                removed += 1
        except OSError:
            pass

    if removed > 0:
        log_activity(
            action="watch_staging_cleanup",
            detail=f"自动清理 {removed} 个过期 staging 文件",
        )


# ═══════════════════════════════════════════
# 处理逻辑
# ═══════════════════════════════════════════

def _process_file(filepath: str):
    """处理单个文件：提取 → 分类 → 摄入 → 移入 processed/DLQ。"""
    import kb_query
    from classify_pipeline import classify_document
    from text_pipeline import extract_text as _extract_text, ocr_image as _ocr_image
    from qconst import DEFAULT_COLLECTION, CONFIDENCE_LOW, CONFIDENCE_HIGH

    filename = os.path.basename(filepath)
    _watch_stats["infra_ok"] = True

    # ── 格式检查 ──
    ext = os.path.splitext(filename)[1].lower()
    supported = {".txt", ".md", ".json", ".csv", ".log", ".pdf", ".docx",
                 ".pptx", ".epub", ".html", ".htm", ".xml", ".jpg", ".jpeg",
                 ".png", ".bmp", ".tiff", ".tif"}
    if ext not in supported:
        _move_to_dlq(filepath, f"不支持的文件格式: {ext}", "format_check")
        return

    # ── 文件大小检查 ──
    if WATCH_MAX_FILE_SIZE_MB > 0:
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if size_mb > WATCH_MAX_FILE_SIZE_MB:
                _move_to_dlq(
                    filepath,
                    f"文件过大 ({size_mb:.1f}MB > {WATCH_MAX_FILE_SIZE_MB}MB)",
                    "size_check",
                )
                return
        except OSError:
            _move_to_dlq(filepath, "无法读取文件大小", "size_check")
            return

    # ── 文本提取 ──
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    if ext in image_exts:
        # 图片文件 → OCR 路径
        if not _check_ocr_ready():
            _move_to_dlq(filepath, "OCR 引擎不可用，PaddleOCR 未安装", "ocr_check")
            return
        try:
            ocr_result = _ocr_image(filepath)
            if not ocr_result.get("ok") or not ocr_result.get("text", "").strip():
                _move_to_dlq(
                    filepath,
                    ocr_result.get("error", "OCR 识别失败或结果为空"),
                    "ocr",
                )
                return
            text = ocr_result["text"]
        except Exception as e:
            _move_to_dlq(filepath, f"OCR 异常: {e}", "ocr")
            return
    else:
        try:
            result = _extract_text(filepath)
        except Exception as e:
            _move_to_dlq(filepath, f"文本提取异常: {e}", "extract")
            return

        if not result.get("ok"):
            _move_to_dlq(filepath, result.get("error", "文本提取失败"), "extract")
            return

        text = result.get("text", "")
    if not text or not text.strip():
        _move_to_dlq(filepath, "提取的文本为空", "extract_empty")
        return

    # ── AI 分类 ──
    try:
        classify_result = classify_document(text, file_path=filepath)
    except Exception as e:
        _move_to_dlq(filepath, f"分类异常: {e}", "classify")
        return

    if not classify_result.get("ok"):
        _move_to_dlq(
            filepath,
            classify_result.get("error", "分类失败"),
            "classify",
        )
        return

    annotated = classify_result.get("annotated", {})
    classification = classify_result.get("classification", {})
    field_sources = annotated.get("field_sources", {})
    overall_conf = annotated.get("overall_confidence", 0.0)

    # ── 置信度路由 ──
    metadata = dict(classification)
    metadata["source_path"] = filepath
    metadata["ingestion_source"] = "watch"

    if overall_conf >= CONFIDENCE_HIGH:
        # 直接入库
        pass
    elif overall_conf >= CONFIDENCE_LOW:
        # 待审核
        metadata["needs_review"] = True
    else:
        # 置信度过低 → Qdrant DLQ（JSON 格式，走现有管道）
        import kb_query as kbq_module
        dlq_dir = os.path.join(PROJECT_DIR, "local_data", "dead_letter")
        os.makedirs(dlq_dir, exist_ok=True)
        dlq_file = os.path.join(dlq_dir, f"{int(time.time())}.json")
        dlq_data = {
            "content": text[:3000],
            "metadata": metadata,
            "confidence": overall_conf,
            "field_sources": field_sources,
            "reason": f"守望文件夹: 置信度过低 ({overall_conf:.2f} < {CONFIDENCE_LOW:.2f})",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(dlq_file, "w", encoding="utf-8") as f:
            json.dump(dlq_data, f, ensure_ascii=False, indent=2)

        _move_to_processed(filepath)  # 文件已提取，移 processed
        log_activity(
            action="watch_low_confidence",
            detail=f"置信度 {overall_conf:.2f} < {CONFIDENCE_LOW:.2f}，入死信队列",
            source=filename,
        )
        return

    # ── 摄入 ──
    try:
        ingest_result = kb_query.ingest(
            text=text,
            metadata=metadata,
            collection=DEFAULT_COLLECTION,
            field_sources=field_sources,
            overall_confidence=overall_conf,
        )
    except Exception as e:
        _move_to_dlq(filepath, f"摄入异常: {e}", "ingest")
        return

    if ingest_result.get("ok"):
        _move_to_processed(filepath)
    else:
        _move_to_dlq(
            filepath,
            ingest_result.get("error", "摄入失败"),
            "ingest",
        )


def _process_file_with_timeout(filepath: str):
    """带超时保护的文件处理。"""
    result = {"ok": False, "error": "timeout"}

    def target():
        nonlocal result
        try:
            _process_file(filepath)
            result["ok"] = True
        except Exception as e:
            result["error"] = str(e)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=WATCH_PROCESSING_TIMEOUT)

    if thread.is_alive():
        # 超时了，但线程是 daemon 的，进程退出时会被清理
        _move_to_dlq(
            filepath,
            f"处理超时（>{WATCH_PROCESSING_TIMEOUT}秒）",
            "timeout",
        )


# ═══════════════════════════════════════════
# 文件监控 + 处理循环
# ═══════════════════════════════════════════

class WatchHandler(FileSystemEventHandler):
    """watchdog 事件处理器 — 文件创建时入队。"""

    def __init__(self, queue: Queue, stop_event: threading.Event):
        super().__init__()
        self.queue = queue
        self.stop_event = stop_event

    def on_created(self, event):
        if event.is_directory:
            return
        if self.stop_event.is_set():
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)

        # 过滤临时文件
        if _is_temp_file(filename):
            _watch_stats["skipped"] += 1
            return

        # 入队（超限拒绝）
        try:
            self.queue.put(filepath, timeout=0.5)
        except Exception:
            _watch_stats["skipped"] += 1
            log_activity(
                action="watch_queue_full",
                detail=f"队列已满，丢弃文件: {filename}",
                source=filename,
            )


def _processing_loop(queue: Queue, stop_event: threading.Event):
    """后台处理循环：从队列取文件，逐个处理。"""
    global _heartbeat_time

    log_activity(action="watch_started", detail="守望文件夹处理循环启动")

    # 首先扫描 watch/ 中已有的文件
    _scan_existing_files(queue)

    _watch_stats["running"] = True

    while not stop_event.is_set():
        # 更新心跳
        with _heartbeat_lock:
            _heartbeat_time = time.time()

        try:
            filepath = queue.get(timeout=2.0)
        except Empty:
            # 定期清理
            _cleanup_dlq()
            _cleanup_processed()
            _cleanup_staging()
            continue

        filename = os.path.basename(filepath)

        # 文件可能已在排队期间被删除
        if not os.path.isfile(filepath):
            continue

        # 过滤临时文件（二次检查）
        if _is_temp_file(filename):
            _watch_stats["skipped"] += 1
            continue

        # 基础设施检查
        infra = _check_infra()
        if not (infra["qdrant"] and infra["ollama"]):
            _watch_stats["infra_ok"] = False
            log_activity(
                action="watch_infra_down",
                detail=f"基础设施不可用 (qdrant={infra['qdrant']}, ollama={infra['ollama']})，暂停处理，{WATCH_INFRA_RETRY_INTERVAL}s 后重试",
            )
            # 文件留在 watch/ 中，不入 DLQ
            # 等待重试间隔
            retry_deadline = time.time() + WATCH_INFRA_RETRY_INTERVAL
            while time.time() < retry_deadline:
                if stop_event.is_set():
                    return
                time.sleep(1)
            # 重新把文件放进队列
            try:
                queue.put(filepath, timeout=0.5)
            except Exception:
                pass
            continue

        _watch_stats["infra_ok"] = True

        # 写入完成检测（文件被 move 到 staging 前先确认）
        if not _is_write_complete(filepath):
            log_activity(
                action="watch_write_incomplete",
                detail=f"文件写入未完成，跳过: {filename}",
                source=filename,
            )
            # 稍后再试
            time.sleep(1)
            try:
                queue.put(filepath, timeout=0.5)
            except Exception:
                pass
            continue

        # 移入 staging
        staging_path = _move_to_staging(filepath)
        if not staging_path:
            continue

        # 处理文件
        _process_file_with_timeout(staging_path)

    _watch_stats["running"] = False
    log_activity(action="watch_stopped", detail="守望文件夹处理循环已停止")


def _scan_existing_files(queue: Queue):
    """扫描 watch/ 中已有的文件并加入队列。"""
    if not os.path.isdir(WATCH_DIR):
        return

    files = []
    for filename in os.listdir(WATCH_DIR):
        filepath = os.path.join(WATCH_DIR, filename)
        if os.path.isfile(filepath) and not _is_temp_file(filename):
            files.append(filepath)

    for fp in sorted(files):
        try:
            queue.put(fp, timeout=0.5)
        except Exception:
            _watch_stats["skipped"] += 1


# ═══════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════

def _check_lock_file() -> bool:
    """检查是否已有 watcher 实例在运行。返回 True = 可以安全启动。"""
    if not os.path.isfile(LOCK_FILE):
        return True

    # 读取锁文件中的 PID
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        # 锁文件损坏，删除后允许启动
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        return True

    # 检查该 PID 是否还活着
    try:
        import ctypes
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return False  # 进程还在
    except Exception:
        pass  # 非 Windows 或权限不足，保守允许启动

    # 进程不在了，清理僵尸锁
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass
    return True


def _write_lock_file():
    """写入当前 PID 到锁文件。"""
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        log_activity(
            action="watch_lock_failed",
            detail="无法写入锁文件，多实例保护失效",
        )


def _remove_lock_file():
    """删除锁文件。"""
    try:
        if os.path.isfile(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def start_watcher() -> threading.Thread | None:
    """启动守望文件夹守护进程。返回 watcher 线程。"""
    global _observer, _worker_thread, _queue, _stop_event

    # 多实例检测
    if not _check_lock_file():
        log_activity(
            action="watch_multiple_instance",
            detail="已有守望进程在运行，拒绝重复启动",
        )
        print("[watcher] 已有守望进程在运行，跳过启动。")
        return None

    # 确保目录存在
    for d in [WATCH_DIR, STAGING_DIR, PROCESSED_DIR, DLQ_DIR]:
        _ensure_dir(d)

    # 恢复孤儿文件
    _recover_orphans()

    # 清理过期文件
    _cleanup_dlq()
    _cleanup_processed()
    _cleanup_staging()

    # 初始化队列和信号
    _queue = Queue(maxsize=WATCH_QUEUE_MAX_SIZE)
    _stop_event = threading.Event()

    # 启动文件监控
    _observer = Observer()
    handler = WatchHandler(_queue, _stop_event)
    _observer.schedule(handler, WATCH_DIR, recursive=False)
    _observer.start()

    # 启动处理线程
    _worker_thread = threading.Thread(
        target=_processing_loop,
        args=(_queue, _stop_event),
        daemon=True,
        name="citrinitas-watcher",
    )
    _worker_thread.start()

    _watch_stats["running"] = True
    log_activity(action="watch_started", detail="守望文件夹已启动")

    # 写入 PID 锁文件
    _write_lock_file()

    return _worker_thread


def stop_watcher():
    """停止守望文件夹守护进程。"""
    global _observer, _stop_event

    if _stop_event:
        _stop_event.set()

    if _observer:
        _observer.stop()
        _observer.join(timeout=5)

    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=10)

    _watch_stats["running"] = False
    _remove_lock_file()
    log_activity(action="watch_stopped", detail="守望文件夹已停止")


def is_watcher_alive() -> bool:
    """检查 watcher 线程是否存活（心跳检测）。"""
    with _heartbeat_lock:
        last_beat = _heartbeat_time
    if last_beat == 0:
        return False
    # 超过 60 秒无心跳 → 认为死亡
    return (time.time() - last_beat) < 60


def get_watch_stats() -> dict:
    """获取守望文件夹运行统计。"""
    _watch_stats["dlq_count"] = _count_dlq()
    return _watch_stats.copy()
