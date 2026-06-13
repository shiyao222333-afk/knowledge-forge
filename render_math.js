// render_math.js — KaTeX 服务端公式渲染
// 用法: node render_math.js <input.json> <output.json>
// input.json: {"formulas":[{"text":"...","display":true/false}, ...]}
// output.json: {"results":[{"html":"..."}, ...]}

const katex = require('katex');
const fs = require('fs');

const inputFile = process.argv[2];
const outputFile = process.argv[3];

if (!inputFile || !outputFile) {
    console.error('Usage: node render_math.js <input.json> <output.json>');
    process.exit(1);
}

function renderFormula(text, displayMode) {
    try {
        const html = katex.renderToString(text, {
            throwOnError: false,
            output: 'html',
            displayMode: displayMode,
            strict: false,
            trust: true
        });
        return { ok: true, html: html };
    } catch (e) {
        return { ok: false, html: `<span class="katex-error" title="${e.message.replace(/"/g, '&quot;')}">${text}</span>` };
    }
}

const input = JSON.parse(fs.readFileSync(inputFile, 'utf-8'));
const results = (input.formulas || []).map(f => renderFormula(f.text, !!f.display));
fs.writeFileSync(outputFile, JSON.stringify({ results: results }), 'utf-8');
