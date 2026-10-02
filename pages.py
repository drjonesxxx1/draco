#!/usr/bin/env python3
"""DRACO theme part 1: base CSS, nav, homepage (hero + chat)."""

BASE_CSS = """
:root{--bg:#07090e;--panel:#0c1017;--panel2:#111725;--line:#1c2436;--txt:#dbe4f0;
--dim:#7d8aa0;--gold:#e8b64c;--gold2:#f5d78a;--green:#3ddc84;--red:#ff5c5c;--mono:ui-monospace,'JetBrains Mono','Fira Code',Menlo,monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:var(--mono);font-size:15px;line-height:1.6;
background-image:radial-gradient(ellipse 80% 50% at 50% -10%,rgba(232,180,76,.07),transparent)}
a{color:var(--gold);text-decoration:none}a:hover{color:var(--gold2)}
nav{display:flex;gap:26px;align-items:center;padding:16px 5vw;border-bottom:1px solid var(--line);
position:sticky;top:0;background:rgba(7,9,14,.92);backdrop-filter:blur(8px);z-index:50}
nav .logo{font-weight:700;font-size:17px;color:var(--gold);letter-spacing:2px}
nav .logo small{color:var(--dim);font-weight:400;letter-spacing:0;margin-left:8px}
nav a{color:var(--dim);font-size:13px;text-transform:uppercase;letter-spacing:1px}
nav a.on,nav a:hover{color:var(--gold)}
main{max-width:1080px;margin:0 auto;padding:40px 5vw 80px}
h1{font-size:34px;line-height:1.2;margin-bottom:10px}
h2{font-size:20px;margin:34px 0 12px;color:var(--gold)}
.dim{color:var(--dim)}.gold{color:var(--gold)}.green{color:var(--green)}
.hero{padding:36px 0 10px}
.badge{display:inline-block;border:1px solid var(--gold);color:var(--gold);border-radius:999px;
padding:3px 14px;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin-bottom:18px}
.stats{display:flex;flex-wrap:wrap;gap:14px;margin:22px 0 8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 20px;min-width:150px}
.stat b{display:block;font-size:22px;color:var(--gold)}
.stat span{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:1px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px;margin-top:18px}
.chat{display:flex;flex-direction:column;height:460px;margin-top:20px}
.chatlog{flex:1;overflow-y:auto;padding:16px;background:var(--bg);border:1px solid var(--line);border-radius:10px}
.msg{margin-bottom:16px;white-space:pre-wrap;word-wrap:break-word}
.msg.user{color:var(--gold2)}
.msg.assistant{color:var(--txt)}
.msg .who{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:3px}
.srcs{font-size:12px;color:var(--dim);border-left:2px solid var(--gold);padding-left:10px;margin-top:8px}
.cursor{display:inline-block;width:8px;height:15px;background:var(--gold);animation:blink 1s steps(1) infinite;vertical-align:text-bottom}
@keyframes blink{50%{opacity:0}}
.chatrow{display:flex;gap:10px;margin-top:12px}
.chatrow input{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:8px;
padding:12px 14px;color:var(--txt);font-family:var(--mono);font-size:14px;outline:none}
.chatrow input:focus{border-color:var(--gold)}
button,.btn{background:var(--gold);color:#14100a;border:none;border-radius:8px;padding:12px 22px;
font-family:var(--mono);font-weight:700;font-size:14px;cursor:pointer;letter-spacing:1px}
button:hover,.btn:hover{background:var(--gold2)}
button:disabled{opacity:.5;cursor:not-allowed}
.btn.ghost{background:transparent;border:1px solid var(--gold);color:var(--gold)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{background:var(--panel2);border:1px solid var(--line);color:var(--dim);border-radius:999px;
padding:6px 14px;font-size:12px;cursor:pointer}
.chip:hover{border-color:var(--gold);color:var(--gold)}
table{width:100%;border-collapse:collapse;margin:14px 0}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);font-size:13px}
th{color:var(--dim);text-transform:uppercase;font-size:11px;letter-spacing:1px}
code,pre{background:var(--panel2);border-radius:6px;font-size:13px}
code{padding:2px 6px}
pre{padding:14px;overflow-x:auto;border:1px solid var(--line);margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.card b{color:var(--gold);font-size:13px}
.card span{display:block;color:var(--dim);font-size:11px;margin-top:4px;text-transform:uppercase;letter-spacing:1px}
footer{border-top:1px solid var(--line);margin-top:60px;padding:26px 5vw;display:flex;
justify-content:space-between;color:var(--dim);font-size:12px;flex-wrap:wrap;gap:10px}
.kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:1px 6px;font-size:12px;background:var(--panel2)}
"""

NAV = """<a class='logo' href='/'>DRACO<small>book-forged oracle</small></a>
<a href='/' class='__ACTIVE__-home'>Oracle</a>
<a href='/library' class='__ACTIVE__-library'>Library</a>
<a href='/api' class='__ACTIVE__-api'>API</a>
<a href='/pricing' class='__ACTIVE__-pricing'>Pricing</a>
<a href='/llms.txt' >llms.txt</a>
<a href='https://buymeacoffee.com/r26xrthzttg' target='_blank' rel='noopener'>☕ BMAC</a>"""

PAGE_HOME = """
<div class='hero'>
 <span class='badge'>◈ Grounded in real books — not vibes</span>
 <h1>The smartest coding AI you can <span class='gold'>prove.</span></h1>
 <p class='dim'>Most AI assistants guess. DRACO retrieves from <b>__STATS__</b> —
 languages, kernels, networks, exploitation, red-team tradecraft — and shows you the exact
 books behind every answer. Check the citations. That's the proof.</p>
 <div class='stats'>
  <div class='stat'><b>{{ books }}</b><span>real books indexed</span></div>
  <div class='stat'><b>{{ chunks }}</b><span>retrievable passages</span></div>
  <div class='stat'><b>{{ mb }}M</b><span>chars of expert text</span></div>
  <div class='stat'><b>&lt;2s</b><span>retrieval + answer start</span></div>
 </div>
</div>

<div class='panel'>
 <h2 style='margin-top:0'>◈ Interrogate the Oracle</h2>
 <p class='dim' style='font-size:13px'>{{ free_day }} free questions a day from the browser, no signup.
 Coding · Linux · networking · security tradecraft.</p>
 <div class='chat'>
  <div class='chatlog' id='log'>
   <div class='msg assistant'><span class='who'>draco</span>Ask me anything from the shelves. I cite my sources — hover the gold bar under each answer to see which books I pulled from.</div>
  </div>
  <div class='chatrow'>
   <input id='q' placeholder='e.g. how does a ret2libc exploit chain work?' autocomplete='off'>
   <button id='go'>ASK ⟶</button>
  </div>
  <div class='chips'>
   <span class='chip'>explain stack buffer overflows with a poc</span>
   <span class='chip'>how do I harden ssh on a public server?</span>
   <span class='chip'>write a python port scanner with threads</span>
   <span class='chip'>what is a kernel panic and how do I debug one?</span>
   <span class='chip'>nmap SYN scan vs connect scan — when and why</span>
  </div>
  <p class='dim' style='font-size:11px;margin-top:8px'><span id='left'></span> <a href='/api'>get a free API key →</a></p>
 </div>
</div>

<h2>◈ Why "book-forged" is different</h2>
<div class='grid'>
 <div class='card'><b>Every claim has a receipt</b><span>answers cite [n] — click through to the source book in /library</span></div>
 <div class='card'><b>No 2021 knowledge cutoff</b><span>fundamentals from the canon: K&R, Tanenbaum, the shellcoders' handbook</span></div>
 <div class='card'><b>Agentic by design</b><span>MCP server + REST API — summon DRACO from Claude, GPT, or any agent</span></div>
 <div class='card'><b>Self-hosted, no telemetry</b><span>runs on bare metal; questions never leave the house</span></div>
</div>

<h2>◈ Summon it as a tool</h2>
<pre>{
  "mcpServers": {
    "draco": { "url": "__BASE__/mcp" }
  }
}</pre>
<p class='dim'>Drop that in any MCP client config. Tools: <code>draco_ask</code>, <code>draco_search</code>, <code>draco_status</code>.</p>

<footer><span>DRACO — the book-forged code oracle</span>
<span><a href='https://buymeacoffee.com/r26xrthzttg'>buymeacoffee.com/r26xrthzttg</a> · <a href='/llms.txt'>agent docs</a></span></footer>

<script>
const log=document.getElementById('log'),q=document.getElementById('q'),go=document.getElementById('go');
let busy=false;
function add(who,cls){const d=document.createElement('div');d.className='msg '+cls;
 d.innerHTML="<span class='who'>"+who+"</span><span class='body'></span>";log.appendChild(d);log.scrollTop=log.scrollHeight;return d.querySelector('.body')}
async function ask(text){
 if(busy||!text.trim())return;busy=true;go.disabled=true;
 add('you','user').textContent=text;
 const body=add('draco','assistant');body.innerHTML='<span class=cursor></span>';
 const srcs=document.createElement('div');srcs.className='srcs';srcs.style.display='none';
 try{
  const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({q:text})});
  const reader=r.body.getReader(),dec=new TextDecoder();let buf='',acc='';
  while(true){const{value,done}=await reader.read();if(done)break;
   buf+=dec.decode(value,{stream:true});const lines=buf.split('\\n');buf=lines.pop()||'';
   for(const line of lines){if(!line.startsWith('data: '))continue;
    const ev=JSON.parse(line.slice(6));
    if(ev.type==='sources'&&ev.sources.length){
     srcs.style.display='block';
     srcs.textContent='📚 '+ev.sources.map(s=>'['+(s.n)+'] '+s.title).join(' · ');
    }else if(ev.type==='token'){acc+=ev.text;body.innerHTML='';
     body.appendChild(document.createTextNode(acc));body.appendChild(document.createElement('span')).className='cursor';
     log.scrollTop=log.scrollHeight;
    }else if(ev.type==='error'){acc+='\n⚠ '+ev.text;}
   }}
 }catch(e){acc+='\n⚠ connection lost';}
 body.innerHTML='';body.appendChild(document.createTextNode(acc||'(no output)'));
 const cur=body.querySelector('.cursor');if(cur)cur.remove();
 body.appendChild(srcs);
 const left=document.getElementById('left');
 fetch('/api/remaining').then(r=>r.json()).then(d=>left.textContent=d.remaining+' free questions left today').catch(()=>{});
 busy=false;go.disabled=false;log.scrollTop=log.scrollHeight;
}
go.onclick=()=>{ask(q.value);q.value=''};
q.addEventListener('keydown',e=>{if(e.key==='Enter'){ask(q.value);q.value=''}});
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>ask(c.textContent));
fetch('/api/remaining').then(r=>r.json()).then(d=>document.getElementById('left').textContent=d.remaining+' free questions left today').catch(()=>{});
</script>
"""
