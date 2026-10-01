PAGE = r"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Tracker czasu</title>
<style>
:root{--bg:#f6f6f4;--fg:#1c1c1a;--mut:#74746f;--card:#fff;--line:#e4e4df;--acc:#2f5bd8;--warn:#b86a00}
@media(prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecece8;--mut:#9a9a94;--card:#1f1f1d;--line:#33332f;--acc:#7b9bff;--warn:#e0a040}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0}h2{font-size:14px;margin:0 0 8px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:12px}
button,select,input{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
button{cursor:pointer}button.p{background:var(--acc);color:#fff;border-color:var(--acc)}
.row{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px dashed var(--line)}
.row:last-child{border:0}.mut{color:var(--mut)}
#tl{position:relative;height:46px;background:var(--bg);border:1px solid var(--line);border-radius:8px;overflow:hidden}
#tl div{position:absolute;top:0;bottom:0;opacity:.9}
.blk{display:grid;grid-template-columns:90px 1fr;gap:8px;padding:8px 0;border-bottom:1px solid var(--line)}
.blk:last-child{border:0}.t{font-variant-numeric:tabular-nums;color:var(--mut)}
.pill{display:inline-block;border-radius:99px;padding:0 8px;font-size:12px;border:1px solid var(--line)}
.warn{color:var(--warn)}details summary{cursor:pointer;color:var(--mut);font-size:13px}
.act{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center}
</style></head><body><main>
<div class="top"><h1>Tracker czasu</h1>
<button id="prev">‹</button><input type="date" id="date"><button id="next">›</button>
<label><input type="checkbox" id="onlywork"> tylko praca</label><span id="state" class="pill"></span></div>
<div class="card"><h2>Oś dnia</h2><div id="tl"></div><div id="legend" class="mut" style="margin-top:6px"></div></div>
<div class="card"><h2>Podsumowanie</h2><div id="sums"></div></div>
<div class="card" id="reviewcard"><h2>Do sprawdzenia <span id="rc"></span></h2><div id="review"></div></div>
<div class="card"><h2>Wszystkie bloki</h2><div id="blocks"></div></div>
<div class="card"><h2>Dopisz czas ręcznie</h2><div class="act">
<input id="mf" type="time"><input id="mt" type="time"><select id="mp"></select>
<input id="mn" placeholder="opis (np. spotkanie u klienta)" style="flex:1;min-width:160px"><button id="madd">Dodaj</button></div></div>
<div class="card"><h2>Zamknięcie dnia</h2><div class="act">
<button class="p" id="approve">Zatwierdź dzień</button><button id="reopen">Odblokuj</button>
<button id="push">Wyślij do programu</button><a id="csv" href="#"><button>Pobierz CSV</button></a>
<button id="ai">Dopasuj AI</button><span id="msg" class="mut"></span></div><div id="entries" style="margin-top:8px"></div></div>
<div class="card"><h2>Ustawienia</h2><details><summary>Projekty, reguły, eksport (plik konfiguracji)</summary>
<p class="mut">Edytujesz JSON: <code>projects</code> (kod, nazwa, marka, słowa kluczowe, foldery), <code>rules</code>, <code>export</code> (adres i token Twojego programu).</p>
<textarea id="cfg" rows="16" style="width:100%;font:13px ui-monospace,monospace;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px" spellcheck="false"></textarea>
<div class="act"><button class="p" id="cfgsave">Zapisz ustawienia</button><span id="cfgmsg" class="mut"></span></div></details></div>
</main><script>
const $=id=>document.getElementById(id);let D=null,colors={};
const pal=["#2f5bd8","#d8572f","#2fa86b","#a02fd8","#d8a82f","#2fa8d8","#d82f7a","#6b7a2f"];
const fmt=s=>{s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h?h+" h "+String(m).padStart(2,"0")+" min":m+" min"};
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const col=c=>c?(colors[c]=colors[c]||pal[Object.keys(colors).length%pal.length]):"#9a9a94";
async function api(p,b){const r=await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{});
 const j=await r.json();if(!r.ok)alert(j.error||"Błąd");return j}
async function load(){D=await api("/api/day?date="+$("date").value);render()}
function label(b){return b.type=="private"?"prywatne":b.type=="unproductive"?"poza pracą":b.type=="unknown"?"nieprzypisane":(b.project||"praca ogólna")}
function render(){
 $("state").textContent=D.approved?"zatwierdzony":"otwarty";
 const [y,m,d]=D.date.split("-").map(Number);const t0=new Date(y,m-1,d).getTime()/1000;
 $("tl").innerHTML=D.blocks.filter(b=>!($("onlywork").checked&&["unproductive","private"].includes(b.type))).map(b=>
  `<div title="${esc(b.from+"–"+b.to+" "+label(b)+" · "+b.app)}" style="left:${(b.start-t0)/864}%;width:${Math.max(.15,(b.end-b.start)/864)}%;background:${col(b.type=="project"||b.type=="general"?b.project:null)}"></div>`).join("");
 $("legend").innerHTML=D.totals.projects.map(p=>`<span style="color:${col(p.code)}">■</span> ${esc(p.code)} `).join(" ");
 const T=D.totals;let h=T.projects.map(p=>`<div class="row"><span><b>${esc(p.name)}</b> <span class="mut">${esc(p.brand)}</span></span><span>${fmt(p.seconds)}</span></div>`).join("");
 h+=Object.entries(T.brands).map(([b,s])=>`<div class="row mut"><span>Marka ${esc(b)}</span><span>${fmt(s)}</span></div>`).join("");
 if(T.general)h+=`<div class="row"><span>Praca ogólna (bez projektu)</span><span>${fmt(T.general)}</span></div>`;
 if(!$("onlywork").checked)h+=`<div class="row mut"><span>Poza pracą</span><span>${fmt(T.unproductive)}</span></div><div class="row mut"><span>Prywatne</span><span>${fmt(T.private)}</span></div>`;
 if(T.unknown)h+=`<div class="row warn"><span>Nieprzypisane</span><span>${fmt(T.unknown)}</span></div>`;
 $("sums").innerHTML=h||'<span class="mut">Brak danych tego dnia</span>';
 const opts='<option value="">— wybierz projekt —</option>'+D.projects.map(p=>`<option value="${esc(p.code)}">${esc(p.code)} · ${esc(p.name)} (${esc(p.brand)})</option>`).join("");
 $("mp").innerHTML=opts;
 const rv=D.blocks.filter(b=>D.review.includes(b.id));$("rc").textContent="("+rv.length+")";
 $("review").innerHTML=rv.map(b=>blockHtml(b,true)).join("")||'<span class="mut">Nic do sprawdzenia</span>';
 $("blocks").innerHTML=D.blocks.filter(b=>!($("onlywork").checked&&["unproductive","private"].includes(b.type))).map(b=>blockHtml(b,false)).join("");
 $("entries").innerHTML=D.entries.length?"<h2>Wpisy do eksportu</h2>"+D.entries.map(e=>`<div class="row"><span>${esc(e.project||"ogólne")} <span class="mut">${esc(e.description)}</span></span><span>${fmt(e.seconds)} · ${e.status}</span></div>`).join(""):"";
 document.querySelectorAll("[data-assign]").forEach(btn=>btn.onclick=()=>assign(btn.dataset.assign,btn.dataset.ctx));
 $("approve").disabled=D.approved;$("reopen").disabled=!D.approved;$("push").style.display=D.export_url_set?"":"none"}
function blockHtml(b,edit){
 const info=[b.app,b.title,b.path,b.url].filter(Boolean).map(esc).join(" · ");
 const opts='<option value="">— projekt —</option>'+D.projects.map(p=>`<option value="${esc(p.code)}" ${p.code==b.project?"selected":""}>${esc(p.code)}</option>`).join("")+'<option value="__general">praca ogólna</option><option value="__unprod">poza pracą</option><option value="__private">prywatne</option>';
 return `<div class="blk"><div class="t">${b.from}–${b.to}<br>${fmt(b.end-b.start)}</div><div>
 <span class="pill" style="border-color:${col(b.project)}">${esc(label(b))}</span> <span class="mut">${b.confidence}% · ${esc(b.source||"")}</span>
 ${b.device?`<span class="pill">${esc(b.device)}</span>`:""}<div class="mut" style="word-break:break-word">${info||esc(b.title)}</div>
 <details><summary>skąd to przypisanie</summary><div class="mut">${esc(b.reason)}</div></details>
 ${D.approved||b.type=="private"?"":`<div class="act"><select id="s${b.id}">${opts}</select>
 ${b.suggest?`<label class="mut"><input type="checkbox" id="r${b.id}" ${edit?"checked":""}> zapamiętaj regułę: ${esc(b.suggest.field)}~</label><input id="p${b.id}" value="${esc(b.suggest.pattern)}" size="22">`:""}
 <button class="p" data-assign="${b.id}">Zapisz</button>${b.device=="ręcznie"?`<button onclick="del(${b.id})">Usuń</button>`:""}</div>`}</div></div>`}
async function assign(id){
 let v=$("s"+id).value,type=null,project=v;
 if(v=="__general"){type="general";project=null}else if(v=="__unprod"){type="unproductive";project=null}else if(v=="__private"){type="private";project=null}
 else if(!v){alert("Wybierz projekt");return}
 const b=D.blocks.find(x=>x.id==id),rc=$("r"+id);
 const rule=rc&&rc.checked?{field:b.suggest.field,pattern:$("p"+id).value}:null;
 await api("/api/assign",{id,project,type,rule});load()}
async function del(id){await api("/api/delete",{id});load()}
$("madd").onclick=async()=>{if(!$("mf").value||!$("mt").value)return alert("Podaj godziny");
 const p=$("mp").value;await api("/api/manual",{date:D.date,from:$("mf").value,to:$("mt").value,project:p||null,type:p?"project":"general",note:$("mn").value});load()};
$("approve").onclick=async()=>{if(D.review.length&&!confirm(D.review.length+" bloków czeka na sprawdzenie. Zatwierdzić mimo to?"))return;await api("/api/approve",{date:D.date});load()};
$("reopen").onclick=async()=>{await api("/api/reopen",{date:D.date});load()};
$("push").onclick=async()=>{const r=await api("/api/push",{date:D.date});$("msg").textContent=r.message;load()};
$("ai").onclick=async()=>{const r=await api("/api/classify",{date:D.date});$("msg").textContent="AI dopasowało: "+r.classified;load()};
$("csv").onclick=e=>{e.target.closest("a").href="/api/export.csv?date="+D.date};
const shift=n=>{const d=new Date($("date").value);d.setDate(d.getDate()+n);$("date").value=d.toISOString().slice(0,10);load()};
api("/api/config").then(r=>$("cfg").value=r.text);
$("cfgsave").onclick=async()=>{const r=await api("/api/config",{text:$("cfg").value});$("cfgmsg").textContent=r.message;if(r.ok)load()};
$("prev").onclick=()=>shift(-1);$("next").onclick=()=>shift(1);$("date").onchange=load;$("onlywork").onchange=render;
$("date").value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);load();setInterval(()=>{if(!D.approved&&!/SELECT|INPUT/.test(document.activeElement.tagName))load()},60000);
</script></body></html>"""
