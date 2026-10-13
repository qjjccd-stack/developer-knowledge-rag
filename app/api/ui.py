"""同源轻量页面；证据通过 textContent 展示，避免把不可信 Markdown 当 HTML。"""

HTML = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>研发知识库 · RAG</title>
<style>
:root{--ink:#142c36;--teal:#087f8c;--muted:#637780;--line:#dce5e8;--paper:#f5f8fa}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.layout{display:grid;grid-template-columns:285px 1fr;min-height:100vh}aside{background:#112d36;color:#d4e5e9;padding:32px 25px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-size:22px;font-weight:750;color:white}.small{font-size:12px;color:var(--muted)}aside .small{color:#9dbac4}
.pill{display:inline-block;border:1px solid #c9dde0;border-radius:25px;padding:3px 12px;font-size:12px;color:var(--teal);background:#effafa}
aside input{background:#25424c;color:white;border-color:#38555e}input,textarea,select,button{font:inherit;border:1px solid var(--line);border-radius:10px;padding:10px;width:100%}
aside label{display:block;font-size:12px;margin:32px 0 7px}button{cursor:pointer}main{padding:44px 6vw;max-width:1300px;width:100%;margin:auto}
h1{font-size:34px;line-height:1.25;letter-spacing:-1px;margin:12px 0}h2{font-size:18px;margin:0 0 15px}p{margin:10px 0}.lead{color:var(--muted);margin-bottom:28px}
.card{background:white;border:1px solid var(--line);border-radius:18px;padding:24px;margin-bottom:22px;box-shadow:0 6px 20px #102e3505}
textarea{resize:vertical;min-height:100px;border:0;background:#f6f9fa;padding:15px;outline-color:#1d9ea6}
.controls{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-top:16px}.controls button{width:160px;background:var(--teal);border:0;color:white;font-weight:650}
.controls button:disabled{opacity:.6}.controls select{width:200px;font-size:13px}
.samples{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.samples button{width:auto;font-size:12px;color:#366273;background:#f3f8fa;padding:6px 12px}
.answer{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;max-height:380px;overflow:auto}.status{color:var(--teal);font-size:12px;margin-bottom:12px}
.metrics{display:flex;gap:30px;padding-top:18px;border-top:1px solid var(--line);margin-top:20px;color:var(--muted);font-size:12px}
details{margin-top:12px;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;color:#255d6e;font-size:14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:330px;overflow:auto;background:#f5f8fa;padding:15px;border-radius:10px;font-size:12px}
a{color:var(--teal)}.doc{font-size:12px;padding:11px 0;border-bottom:1px solid #35515b}.error{color:#b94040}.notice{background:#eaf4f4;border-radius:10px;padding:12px 15px;font-size:12px;color:#49717b}
@media(max-width:850px){.layout{display:block}aside{position:relative;height:auto;padding:20px}aside label{margin-top:15px}aside #docs{max-height:160px;overflow:auto}main{padding:25px 18px}h1{font-size:28px}}
</style>
<div class="layout"><aside>
<div class="brand">▦ 研发知识库</div><div class="small">DEVELOPER KNOWLEDGE</div>
<p style="margin-top:28px">资料有出处，答案有依据。</p>
<label for="token">访问令牌</label><input type="password" id="token" value="demo-reader-token" autocomplete="off">
<button id="load" style="margin-top:10px;background:#25424c;color:white;border-color:#38555e">加载可见文档</button>
<p class="small">本机演示身份。文档范围由服务端决定。</p>
<div id="docs"></div></aside>
<main><span class="pill">研发／运维 · 资料可追溯</span><h1>从技术文档中找到答案</h1>
<p class="lead">查阅 FastAPI 官方资料，展开引用查看对应章节、原文行号与文档版本。</p>
<div class="notice">当前默认展示英文资料摘录，检索与重排在本地运行。配置生成模型后可生成中文总结。</div>
<section class="card" style="margin-top:22px"><h2>你想了解什么？</h2>
<textarea id="question" placeholder="例如：When should I use Celery instead of FastAPI BackgroundTasks?"></textarea>
<div class="samples"><button data-q="When should I use Celery instead of FastAPI BackgroundTasks?">后台任务选型</button>
<button data-q="What is a CORS origin and how should I configure credentials?">跨域与凭据</button>
<button data-q="How do I override dependencies when testing FastAPI?">测试依赖替换</button></div>
<div class="controls"><select id="mode" aria-label="检索方案"><option value="hybrid_rerank">混合检索＋重排</option value="hybrid">混合检索</option><option value="dense">语义检索</option><option value="bm25">关键词检索</option></select>
<button id="ask">查找答案 ↗</button></div></section>
<section id="result" class="card" hidden><div id="status" class="status"></div><div id="answer" class="answer"></div><div id="metrics" class="metrics"></div><div id="citations"></div></section>
<p class="small">来源采用固定版本的公开文档。演示权限划分用于验证访问边界；不代表真实企业内部资料。</p>
</main></div>
<script>
const $=id=>document.getElementById(id);
// api：携带当前令牌调用同源接口；fetch 发请求，json 解析数据，拒绝非成功响应。
async function api(path, body){
 const response=await fetch(path,{method:body?"POST":"GET",headers:{"Authorization":"Bearer "+$("token").value,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:(data.detail?.message||"请求参数或权限不符合要求"));
 return data;
}
// loadDocs：api 获取可见文档；textContent 安全显示标题，不执行资料里的 HTML。
async function loadDocs(){
 $("docs").textContent="加载中…";
 try{const docs=await api("/api/documents");$("docs").replaceChildren();
 for(const doc of docs){const row=document.createElement("div");row.className="doc";row.textContent=doc.title;$("docs").append(row);}
 if(!docs.length)$("docs").textContent="尚无可见资料，请先入库。";
 }catch(e){$("docs").textContent=e.message;}
}
// ask：api 发送问题；按结构化结果显示答案、阶段耗时与可展开的已验证引用。
async function ask(){
 if(!$("question").value.trim())return;
 $("ask").disabled=true;$("result").hidden=false;$("status").textContent="正在检索资料…";$("answer").textContent="";$("citations").replaceChildren();$("metrics").textContent="";
 try{const r=await api("/api/ask",{question:$("question").value,mode:$("mode").value,top_k:5});
 $("status").textContent=r.status==="abstained"?"资料不足／引用未通过校验":r.generation_mode==="extractive"?"资料摘录 · 本地模型":"回答完成 · 引用已核验";
 $("answer").textContent=r.answer;
 $("metrics").textContent="检索 "+r.timings.retrieval_ms.toFixed(0)+" ms　重排 "+r.timings.rerank_ms.toFixed(0)+" ms　总耗时 "+r.timings.total_ms.toFixed(0)+" ms";
 for(const c of r.citations){const d=document.createElement("details"),s=document.createElement("summary"),p=document.createElement("pre"),a=document.createElement("a");
 s.textContent="["+c.id+"] "+c.title+" · "+c.heading+" · L"+c.start_line+"–"+c.end_line;p.textContent=c.text;
 a.textContent="查看固定版本原文 ↗";a.href=c.source_url+"#L"+c.start_line+"-L"+c.end_line;a.target="_blank";a.rel="noopener noreferrer";
 d.append(s,p,a);$("citations").append(d);}
 }catch(e){$("status").textContent="请求失败";$("answer").textContent=e.message;}
 finally{$("ask").disabled=false;}
}
$("ask").addEventListener("click",ask);$("load").addEventListener("click",loadDocs);
document.querySelectorAll("[data-q]").forEach(b=>b.addEventListener("click",()=>{$("question").value=b.dataset.q;}));
loadDocs();
</script></html>"""
