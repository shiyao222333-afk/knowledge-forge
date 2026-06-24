# v1.0.0 最终验证清单

> 验证日期：2026-06-24
> 验证版本：v1.0.0 (commit 0b4fd21)
> 验证目标：确认 A1-A5 全部功能正常工作

## 验证环境要求

- Windows 10/11
- Python 3.11+
- Qdrant 已安装（D:\qdrant\qdrant.exe）
- Ollama 已安装并运行
- 磁盘空间 > 5GB

---

## A1: install.ps1 一键部署 ✅

### 验证步骤

1. **清理环境**（首次验证）
   ```bash
   # 删除虚拟环境
   rm -rf venv/
   # 删除配置文件
   rm -f .env
   # 删除数据目录
   rm -rf data/ local_data/ snapshots/ storage/
   ```

2. **运行安装脚本**
   - 右键点击 `install.ps1`
   - 选择"使用 PowerShell 运行"
   - 或 PowerShell 中执行：`.\install.ps1`

3. **检查项**
   - [ ] Python 版本检测通过（3.11+）
   - [ ] 虚拟环境创建成功（venv\ 目录存在）
   - [ ] 依赖安装成功（无红色错误）
   - [ ] 目录结构创建成功（data\watch\, data\watch_staging\ 等）
   - [ ] .env 文件从 .env.example 复制
   - [ ] PaddleOCR 模型预热（首次需下载 ~200MB）

4. **验证命令**
   ```bash
   # 检查虚拟环境
   venv\Scripts\python.exe --version
   
   # 检查关键包
   venv\Scripts\python.exe -c "import nicegui, qdrant_client, openai, pypdf, docx, watchdog, jieba, yaml, dotenv; print('All packages OK')"
   
   # 检查目录结构
   ls data/
   # 应看到：watch/, watch_staging/, watch_processed/, watch_dead_letter/
   ```

---

## A2: run.bat 增强启动 ✅

### 验证步骤

1. **双击运行** `run.bat`

2. **检查项**
   - [ ] Step 1: 清理旧进程（端口 8080 无占用）
   - [ ] Step 2: Python 环境检查通过
   - [ ] Step 3: 配置变更检测（首次无提示，修改 pipe_cfg.yaml 后重启有提示）
   - [ ] Step 4: Ollama 检查（显示 Ollama 状态和嵌入模型状态）
   - [ ] Step 5: Qdrant 启动（或检测到已运行）+ 健康检查通过
   - [ ] Step 6: 守望文件夹提示（显示监控目录）
   - [ ] Step 7: 配置摘要显示正确
   - [ ] Step 7b: 模型预热（PaddleOCR + Ollama 嵌入）
   - [ ] Step 8: Web UI 启动（显示访问地址）

3. **验证命令**
   ```bash
   # 检查 Qdrant 健康
   curl http://127.0.0.1:6333/health
   
   # 检查 Web UI
   curl http://127.0.0.1:8080
   
   # 检查进程
   tasklist | findstr "qdrant"
   ```

4. **优雅关闭测试**
   - [ ] Ctrl+C 停止 Web UI
   - [ ] Qdrant 自动停止
   - [ ] 显示"All services stopped. Goodbye!"

---

## A3: YAML 配置化 ✅

### 验证步骤

1. **检查配置文件**
   - [ ] `pipe_cfg.yaml` 存在
   - [ ] 包含 11 项可配置参数

2. **修改配置测试**
   ```bash
   # 修改 pipe_cfg.yaml
   # 例如：修改 chunk_size: 800 → 600
   
   # 重启服务
   # 观察 Step 3 是否提示配置变更
   ```

3. **验证配置生效**
   - [ ] 修改后重启，配置生效
   - [ ] .env 中的配置覆盖 YAML 配置

4. **验证命令**
   ```bash
   # 检查配置加载
   venv\Scripts\python.exe -c "from config.settings import load_pipe_cfg; cfg = load_pipe_cfg(); print(cfg)"
   ```

---

## A4: 守望文件夹 ✅

### 验证步骤

1. **准备测试文件**
   - 创建 `test.txt`（内容："这是一个测试文件"）
   - 创建 `test.pdf`（包含可搜索文本）
   - 准备一张扫描图片 `test_scan.jpg`

2. **丢入文件测试**
   ```
   将 test.txt 复制到 data\watch\
   ```

3. **检查项**
   - [ ] 文件被自动检测（5-10秒内）
   - [ ] 文件移动到 `data\watch_staging\`（处理中）
   - [ ] 处理完成后，文件移动到 `data\watch_processed\`
   - [ ] 文件出现在知识库搜索结果中

4. **验证命令**
   ```bash
   # 检查守望日志
   type local_data\activity_log.jsonl | findstr "watch"
   
   # 检查 Qdrant 入库
   curl http://127.0.0.1:6333/collections/test_collection/points -X GET -H "Content-Type: application/json"
   ```

5. **失败处理测试**
   - [ ] 放入一个损坏的文件
   - [ ] 文件移动到 `data\watch_dead_letter\`
   - [ ] 生成 .meta.json 错误信息

6. **并发测试**
   - [ ] 同时放入 5 个文件
   - [ ] 全部成功入库（无丢失）

---

## A5: OCR 接入管道 ✅

### 验证步骤

1. **图片 OCR 测试**
   ```
   将一张包含文字的图片（test_image.png）复制到 data\watch\
   ```

2. **检查项**
   - [ ] 图片被检测到
   - [ ] PaddleOCR 自动识别文字
   - [ ] 识别结果入库
   - [ ] 搜索图片中的文字能找到

3. **混合 PDF 测试**
   - [ ] 准备一个扫描版 PDF（无文字层）
   - [ ] 放入 `data\watch\`
   - [ ] 自动 OCR 识别
   - [ ] 入库后可搜索

4. **验证命令**
   ```bash
   # 检查 OCR 结果
   # 在 Web UI 中搜索图片中的文字
   # 确认能找到对应文档
   ```

---

## 集成测试 ✅

### 完整流程测试

1. **摄入 → 搜索 → 问答**
   - [ ] 放入文件（通过守望文件夹或手动上传）
   - [ ] 文件成功入库
   - [ ] 搜索能找到文件内容
   - [ ] 问答能正确回答（有出处）

2. **多格式支持**
   - [ ] .txt 文件
   - [ ] .pdf 文件（文本版 + 扫描版）
   - [ ] .docx 文件
   - [ ] 图片文件（.jpg, .png）
   - [ ] 网页文件（.html, .md）

3. **性能测试**
   - [ ] 单个文件处理 < 30秒
   - [ ] 批量摄入（5个文件）全部成功
   - [ ] 搜索响应 < 3秒

---

## 代码质量验证 ✅

### 静态检查

1. **语法检查**
```bash
python -m py_compile search_engine.py watcher_v2.py ingest_pipeline.py text_pipeline.py main.py qconst.py warmup.py ocr_workflow.py
```
   - [ ] 无语法错误

2. **代码长度检查**
   - [ ] 所有函数 < 50行（已完成重构）
   - [ ] 无嵌套函数
   - [ ] 无重复代码

3. **导入检查**
   - [ ] 无未使用的导入
   - [ ] 无循环导入

---

## 验收标准核对

根据 PROJECT_PLAN.md 中的验收标准：

- [ ] `install.ps1` 双击后 5 分钟内完成全部安装 + 验证通过
- [ ] `run.bat` 双击后自动启动 Qdrant + Ollama（如有）+ Web UI + 守望守护进程
- [ ] 丢一个 .txt 到 `watch/`，30 秒内出现在知识库搜索结果里
- [ ] 丢一张扫描页到 `watch/`，自动 OCR → 入库 → 可搜索
- [ ] OCR 失败的文件出现在「死信队列」UI，不静默丢失
- [ ] 修改 `pipe_cfg.yaml` 后重启服务，参数生效
- [ ] 同时丢 5 个文件到 watch/，全部稳定入库，不丢数据

---

## 验证结果

| 项目 | 状态 | 备注 |
|------|------|------|
| A1: install.ps1 | ⏳ 待验证 | |
| A2: run.bat | ⏳ 待验证 | |
| A3: YAML 配置化 | ⏳ 待验证 | |
| A4: 守望文件夹 | ⏳ 待验证 | |
| A5: OCR 接入 | ⏳ 待验证 | |
| 集成测试 | ⏳ 待验证 | |
| 代码质量 | ✅ 通过 | 语法检查通过，函数长度已优化 |

---

## 阻塞问题

_记录验证过程中发现的阻塞问题_

1. 无

---

## 验证结论

_待所有检查项完成后填写_

- [ ] ✅ 通过 — v1.0.0 可以发布
- [ ] ❌ 失败 — 需要修复阻塞问题

---

**验证人**：___________  
**验证日期**：___________  
**签名**：___________
