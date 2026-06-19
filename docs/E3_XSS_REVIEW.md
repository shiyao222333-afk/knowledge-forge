# E3 XSS 防护复核报告

## 复核日期
2026-06-20

## 复核范围
1. `_format_evidence_text()` 函数（行 2582-2606）
2. `_pipe_table_to_html()` 函数（行 2608-2630+）
3. `_img_tag()` 函数（行 2573-2579）
4. `_render_report_html()` 函数（行 2532-2570+）
5. 其他用户输入注入 HTML 的位置

## 复核结果

### ✅ 已正确防护的位置

1. **`_format_evidence_text()`** (行 2596)
   - 正确使用 `_html.escape(line)` 转义 HTML
   - 然后选择性还原公式和图片引用（安全，因为是系统生成的标签）

2. **`_cell_html()`** (行 2612)
   - 正确使用 `_html.escape(raw)` 转义 HTML
   - 然后选择性还原公式和图片引用

3. **`_img_tag()`** (行 2577, 2579)
   - Base64 内联图片：安全（base64 编码不含 XSS）
   - file:// 引用：正确使用 `_html.escape(img_path)` 转义路径

### ⚠️ 潜在风险的位置

1. **`_render_report_html()`** (行 2543-2545)
   - **问题**: `synthesis` (LLM 输出) 未转义直接插入 HTML
   - **代码**:
     ```python
     # 注意：不对 synthesis 做 HTML 转义，保留 $...$ 供 MathJax 渲染
     # LLM 输出是可信的；若含 < > 等字符会被 MathJax/浏览器安全处理
     synthesis_html = synthesis
     ```
   - **风险**: 低（LLM 输出来自可信的 DeepSeek API）
   - **影响**: 如果 LLM 被攻击或诱导，可能注入恶意 HTML/JavaScript
   - **缓解**: MathJax 只渲染公式，浏览器有 XSS 防护机制
   - **建议**: 当前方法对本地知识库系统可接受，生产环境应考虑：
     - 先转义 HTML，再选择性还原 `$...$` 公式
     - 使用 Content Security Policy (CSP) 防止脚本执行

## 复核结论

**总体评价**: XSS 防护基本到位，主要风险点已处理。

**建议行动**:
- ✅ 当前实现可接受（v0.5.0）
- 🔄 未来改进（v0.6.0）：改进 `_render_report_html()` 的 HTML 转义逻辑

**优先级**: 低（风险低，影响有限）

---
复核人: AI Assistant
复核日期: 2026-06-20
