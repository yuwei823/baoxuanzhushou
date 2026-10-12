const $ = id => document.getElementById(id);
let pictures = [], resultPictures = [], lastResult = null, controller = null, timer = null, exampleGeneration = 0;
const releasePictures = items => items.forEach(p => URL.revokeObjectURL(p.url));
const labels = { compliant: '未发现违规', non_compliant: '发现违规', needs_review: '需要复核', failed: '审核失败', partial: '发现违规 · 审核未完成' };
const states = { checked: '已检查', not_applicable: '不适用', needs_context: '需补充信息', external_verification_required: '需外部核验', failed: '执行失败', out_of_scope: '范围外' };
// Ledger order: items needing action first, then checked, then not applicable.
// Anything unlisted (a future status) sorts last rather than being dropped.
const stateOrder = { needs_context: 0, external_verification_required: 1, failed: 2, checked: 3, out_of_scope: 4, not_applicable: 5 };
// Only "checked" is a clean pass; needs_* and failed need attention; the rest are neutral.
const stateTone = { checked: 'ok', needs_context: 'warn', external_verification_required: 'warn', failed: 'warn' };
const elem = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
function notice(text) { $('notice').hidden = !text; $('notice').textContent = text; }
function count() { $('counter').textContent = `${Array.from($('text').value).length.toLocaleString()} / 10,000`; }
$('text').addEventListener('input', count);
function redraw() { const host = $('previews'); if (!host) return; host.replaceChildren(); pictures.forEach((p, i) => { const card = elem('div', undefined, 'preview'); const img = elem('img'); img.src = p.url; img.alt = `图片 ${i + 1}：${p.file.name}`; card.append(img, elem('span', `${i + 1}. ${p.file.name}`));[['←', i - 1], ['→', i + 1], ['×', -1]].forEach(([label, target]) => { const b = elem('button', label); b.type = 'button'; b.setAttribute('aria-label', label === '×' ? `删除图片 ${i + 1}` : `移动图片 ${i + 1} ${label}`); b.disabled = controller !== null || (label !== '×' && (target < 0 || target >= pictures.length)); b.onclick = () => { if (label === '×') { URL.revokeObjectURL(p.url); pictures.splice(i, 1); } else { [pictures[i], pictures[target]] = [pictures[target], pictures[i]]; } redraw(); }; card.append(b); }); host.append(card); }); }
function addFiles(files) { if (pictures.length + files.length > 5) return notice('最多上传 5 张图片。'); if ([...pictures.map(p => p.file), ...files].reduce((n, f) => n + f.size, 0) > 25 * 1024 * 1024) return notice('图片总计不能超过 25 MB。'); if (files.some(f => f.size > 10 * 1024 * 1024)) return notice('单张图片不能超过 10 MB。'); if (files.some(f => !['image/jpeg', 'image/png', 'image/webp'].includes(f.type))) return notice('仅支持 JPEG、PNG、WebP。'); pictures.push(...files.map(file => ({ file, url: URL.createObjectURL(file) }))); notice(''); redraw(); }
$('images').onchange = () => { addFiles(Array.from($('images').files)); $('images').value = ''; };
document.querySelectorAll('.toggle-option').forEach(b => b.onclick = () => { if (controller) return; document.querySelectorAll('.toggle-option').forEach(o => { const on = o === b; o.classList.toggle('is-active', on); o.setAttribute('aria-checked', String(on)); }); $('depth').value = b.dataset.depth; });
const composer = document.querySelector('.composer'); if (composer) { ['dragenter', 'dragover'].forEach(t => composer.addEventListener(t, e => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); composer.classList.add('dragging'); } }));['dragleave', 'drop'].forEach(t => composer.addEventListener(t, e => { if (t === 'dragleave' && composer.contains(e.relatedTarget)) return; e.preventDefault(); composer.classList.remove('dragging'); if (t === 'drop') addFiles(Array.from(e.dataTransfer.files || []).filter(f => f.type.startsWith('image/'))); })); }
function details(title) { const d = elem('details'); d.append(elem('summary', title)); return d; }
function render(result) {
    lastResult = result; $('download').disabled = false; $('empty').hidden = true; $('results').hidden = false; const host = $('results'); host.replaceChildren(); const key = result.status === 'failed' || result.status === 'partial' ? result.status : result.decision; const verdict = elem('div', undefined, `verdict ${key}`); verdict.append(elem('h3', labels[key] || '审核结果'), elem('p', result.summary)); host.append(verdict); if (result.mock) host.append(elem('p', '模拟演示：未调用真实模型，不计入正式验收。', 'warning'));
    const c = result.coverage; if (c) { const metrics = elem('div', undefined, 'metrics');[[result.violations.length, '违规项'], [result.review_items.filter(r => r.blocking).length, '待核验项'], [c.coverage_ratio === null ? '—' : `${Math.round(c.coverage_ratio * 100)}%`, '检查覆盖率 · 非正确率']].forEach(([v, l]) => { const m = elem('div', undefined, 'metric'); m.append(elem('b', String(v)), elem('small', l)); metrics.append(m); }); host.append(metrics); }
    if (c) {
        const counts = {}; for (const r of c.rules) counts[r.status] = (counts[r.status] || 0) + 1;
        host.append(elem('p', Object.entries(states).map(([key, label]) => `${label} ${counts[key] || 0}`).join(' · '), 'coverage-breakdown'));
        host.append(elem('p', '需补充信息或外部核验不等于执行失败；覆盖率不代表准确率。', 'privacy'));
    }
    if (result.meta?.hidden_review_items) host.append(elem('p', `简要模式隐藏了 ${result.meta.hidden_review_items} 项补充核验提示，可在逐规则覆盖中查看状态与依据。`, 'warning'));
    for (const v of result.violations || []) { const card = elem('article', undefined, 'finding'); card.append(elem('h3', v.reason), elem('p', `规则：${v.rule_id}`)); const cmp = elem('div', undefined, 'comparison'); const left = elem('div'); left.append(elem('h4', '营销内容证据')); for (const e of v.evidence) { const block = elem('div', undefined, 'evidence'); if (e.kind === 'absence') { block.textContent = `缺失：${e.required_disclosure}\n检查范围：${e.search_scope}\n完整性依据：用户声明`; } else { block.append(elem('small', `${e.image_id || '文本'} · ${e.block_id || e.source_id}`)); const source = (result.sources || []).find(s => s.source_id === e.source_id); const p = elem('p'); if (source) { const chars = Array.from(source.text), a = e.start - (source.start || 0), b = e.end - (source.start || 0); p.append(document.createTextNode(chars.slice(0, a).join('')), elem('mark', chars.slice(a, b).join('')), document.createTextNode(chars.slice(b).join(''))); } else p.textContent = e.quote; block.append(p); if (e.image_id) { const index = Number(e.image_id.split('_')[1]) - 1; if (resultPictures[index]) { const img = elem('img'); img.src = resultPictures[index].url; img.alt = e.image_id; block.append(img); } } } left.append(block); } const right = elem('div'); right.append(elem('h4', '法规原文')); for (const citation of v.citations) { const d = details(`${citation.document_title} · ${citation.article_label}`); d.className = 'citation'; d.append(elem('p', citation.original_text)); right.append(d); } cmp.append(left, right); card.append(cmp, elem('p', v.confidence === null ? '未提供置信度' : `模型自评 ${v.confidence}，未经校准，不是正确率。`)); host.append(card); }
    if (result.review_items?.length) { const d = details(`待核验事项 (${result.review_items.length})`); d.open = true; for (const r of result.review_items) d.append(elem('div', `${r.reason}\n需要：${r.required_information.join('、')}`, 'review-item')); host.append(d); }
    for (const e of result.errors || []) host.append(elem('div', `${e.stage} · ${e.code}：${e.message}`, 'error'));
    if (c) { const d = details(`逐规则覆盖 · ${c.checked}/${c.eligible} 项已检查`); const table = elem('table', undefined, 'ledger'); const head = elem('tr'); head.append(elem('th', '规则'), elem('th', '状态'), elem('th', '依据')); table.append(head); const ordered = [...c.rules].sort((a, b) => (stateOrder[a.status] ?? 9) - (stateOrder[b.status] ?? 9) || a.rule_id.localeCompare(b.rule_id)); for (const r of ordered) { const tr = elem('tr'); const status = elem('td', states[r.status] || r.status); const tone = stateTone[r.status]; if (tone) status.className = `state-${tone}`; tr.append(elem('td', r.rule_id), status, elem('td', r.reason)); table.append(tr); } d.append(table); host.append(d); }
    if (result.images?.length) { const d = details('逐图提取记录与可读性'); for (const image of result.images) { const original = resultPictures[Number(image.image_id.split('_')[1]) - 1]; if (original) { const preview = elem('img'); preview.src = original.url; preview.alt = `提交原图 ${image.image_id}`; preview.className = 'result-image'; d.append(preview); } d.append(elem('h4', image.image_id), elem('p', image.visible_text || '没有可靠文字', 'source-text')); for (const line of image.unreadable_regions) d.append(elem('p', `不可读：${line}`, 'warning')); for (const line of image.visual_observations) d.append(elem('p', `画面观察：${line}`)); } host.append(d); }
    for (const w of result.warnings || []) host.append(elem('p', w, 'warning')); if (result.meta) host.append(elem('p', `耗时 ${(result.meta.latency_ms / 1000).toFixed(1)} 秒 · 模型尝试 ${result.meta.attempts} 次 · 追踪 ${result.trace_id}`, 'privacy'));
}
function busy(on) { document.body.classList.toggle('busy', on); $('submit').disabled = on; $('cancel').hidden = !on; for (const e of document.querySelectorAll('textarea,select,input,[data-example],.toggle-option')) e.disabled = on; setText('empty-title', on ? '审核中' : '等待提交材料'); setText('empty-hint', on ? '正在比对营销证据与法规原文，请稍候。' : '审核完成后，在这里逐项对照营销证据与法规原文。'); const bar = $('progress'); if (bar) bar.hidden = !on; if (!on) setProgress(null); if (on) clearObservations(); redraw(); }
// Progress is advisory: it reflects completed rule batches, never a verdict.
function setProgress(event) {
    const host = $('progress'); if (!host) return;
    if (!event) { host.replaceChildren(); return; }
    const done = event.completed_rules ?? 0, total = event.total_rules ?? 0;
    const ratio = total ? Math.min(1, done / total) : 0;
    const label = event.stage === 'extract' ? '正在识别图片文字…' : event.stage === 'retrieve' ? '正在检索相关法规…' : event.stage === 'done' ? '正在汇总结论…' : `已比对 ${done} / ${total} 条规则`;
    const track = elem('div', undefined, 'progress-track'); const fill = elem('div', undefined, 'progress-fill'); fill.style.width = `${Math.round(ratio * 100)}%`; track.append(fill);
    host.replaceChildren(elem('p', label, 'progress-label'), track);
}
// Append what the vision model reported for each image while the audit runs.
function pushObservations(event) {
    const host = $('observations'); if (!host) return;
    host.hidden = false;
    const lines = [];
    if (event.visible_text) lines.push({ text: event.visible_text, cls: 'observation-text' });
    for (const o of event.observations || []) lines.push({ text: o, cls: 'observation-line' });
    for (const u of event.unreadable_regions || []) lines.push({ text: `不可读：${u}`, cls: 'observation-warn' });
    if (!lines.length) return;
    host.append(elem('p', `${event.image_id} · 模型读图观察`, 'observation-title'));
    for (const l of lines) host.append(elem('p', l.text, l.cls));
    host.scrollTop = host.scrollHeight;
}
function clearObservations() { const host = $('observations'); if (host) { host.replaceChildren(); host.hidden = true; } }
$('submit').onclick = async () => {
    if (controller) return; const text = $('text').value; if (!text.trim() && !pictures.length) return notice('请输入文本或上传图片。'); if (Array.from(text).length > 10000) return notice('文本最多 10,000 个 Unicode 字符。');
    exampleGeneration++; const submitted = pictures.map(p => ({ file: p.file, url: URL.createObjectURL(p.file) })); let rendered = false;
    const form = new FormData(); form.append('text', text); const context = {}; for (const id of ['channel', 'publisher_type', 'product_type', 'material_completeness']) context[id] = $(id).value; form.append('context', JSON.stringify(context)); form.append('depth', $('depth').value); pictures.forEach(p => form.append('images', p.file));
    controller = new AbortController(); busy(true); notice(''); const start = Date.now(); $('submit').textContent = '审核中 · 0 秒'; timer = setInterval(() => $('submit').textContent = `审核中 · ${Math.floor((Date.now() - start) / 1000)} 秒`, 1000);
    try {
        const r = await fetch('/api/v1/audits/stream', { method: 'POST', body: form, signal: controller.signal });
        if (r.status === 429) { notice('服务器审核任务已满，请稍后重试。'); return; }
        if (!r.ok || !r.body) { notice('本次审核未完成，输入已保留。'); return; }
        // Parse the SSE frames by hand: the payload is JSON we already understand,
        // and EventSource cannot issue a POST with a FormData body.
        const reader = r.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        for (;;) {
            const { value, done } = await reader.read(); if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split('\n\n'); buffer = frames.pop();
            for (const frame of frames) {
                const name = frame.match(/^event: (.+)$/m)?.[1]; const data = frame.match(/^data: (.+)$/m)?.[1];
                if (!name || !data) continue;
                if (name === 'progress') { const p = JSON.parse(data); if (p.stage === 'observation') pushObservations(p); else setProgress(p); continue; }
                if (name === 'result') { const payload = JSON.parse(data); releasePictures(resultPictures); resultPictures = submitted; rendered = true; render(payload); continue; }
                if (name === 'error') { notice('本次审核未完成，输入已保留。'); continue; }
            }
        }
    } catch (e) { notice(e.name === 'AbortError' ? '已取消，输入已保留。' : '连接失败，输入已保留，请检查本地服务。'); }
    finally { if (!rendered) releasePictures(submitted); clearInterval(timer); controller = null; busy(false); $('submit').textContent = '开始审核 ↗'; }
};
$('cancel').onclick = () => controller?.abort();
$('download').onclick = () => { if (!lastResult) return; const url = URL.createObjectURL(new Blob([JSON.stringify(lastResult, null, 2)], { type: 'application/json' })); const a = elem('a'); a.href = url; a.download = `audit-${lastResult.audit_id || 'error'}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
const examples = { violation: '稳赚不赔！本产品年化收益8%，保本保息，收益写进合同。限时抢购，错过不再有。联系张经理13800008888立即投保。', education: '保险知识科普：任何人都不应宣称“监管部门担保收益”。分红属于非保证利益，实际收益可能低于演示水平。本文不介绍或销售具体产品。', multi: '请结合两张图片审核完整图文材料。'};
document.querySelectorAll('[data-example]').forEach(b => b.onclick = async () => { const generation = ++exampleGeneration; releasePictures(pictures); pictures = []; $('text').value = examples[b.dataset.example]; $('channel').value = 'internet'; $('publisher_type').value = 'insurance_institution'; $('product_type').value = 'insurance'; $('material_completeness').value = b.dataset.example === 'review' ? 'partial' : 'complete'; count(); redraw(); if (b.dataset.example === 'multi') { try { const files = await Promise.all([1, 2].map(async n => new File([await (await fetch(`/static/demo-${n}.png`)).blob()], `演示图片${n}.png`, { type: 'image/png' }))); if (generation === exampleGeneration && !controller) addFiles(files); } catch { notice('演示图片加载失败。'); } } });
const setText = (id, text) => { const el = $(id); if (el) el.textContent = text; }; fetch('/api/v1/rulesets/current').then(r => r.json()).then(r => { setText('ruleset', r.ruleset_id || '规则集未就绪'); setText('scope', r.rule_count ? `${(r.documents || []).length} 份法规 · ${r.article_count} 条文 · ${r.rule_count} 条规则。` : r.summary); setText('mode', r.mock ? '模拟模式' : '百炼 API 模式'); const list = $('documents'); if (list) { list.replaceChildren(); for (const d of r.documents || []) list.append(elem('li', d.title)); } if (!r.model_configured) notice('后端尚未配置模型，请在本地 .env 设置密钥及 Base URL。'); }).catch(() => notice('无法连接本地服务。'));
