#!/usr/bin/env python3
"""DRACO theme part 2: library, pricing, api pages. Jinja vars injected by app.render()."""

PAGE_LIBRARY = """
<h1>The Hoard</h1>
<p class='dim'>__STATS__. Every passage DRACO cites comes from these shelves. Downloads are
free for personal use — this is the library, open to the public.</p>
<h2>◈ Collections</h2>
<table>
<tr><th>Collection</th><th>Contents</th></tr>
<tr><td><b class='gold'>library_linux</b></td><td>The coding canon: C/C++, Python, Perl, PHP, Java, assembly, SQL/databases, web, Unix/Linux internals, networks &amp; security, math, Apache, Windows/M$.</td></tr>
<tr><td><b class='gold'>hackerpack</b></td><td>The Hacker Pro Pack: exploitation, malware, network attacks, crypto, wireless, OSINT, lockpicking-of-the-digital-kind, and the classics of the scene.</td></tr>
</table>
<h2>◈ Browse the shelves</h2>
<div class='chips' id='filters'></div>
<input id='f' placeholder='filter by title…' style='width:100%;margin:12px 0;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:11px 14px;color:var(--txt);font-family:var(--mono);outline:none'>
<p class='dim' id='count'></p>
<div class='grid' id='books'></div>
<footer><span>DRACO — the book-forged code oracle</span><span><a href='https://buymeacoffee.com/r26xrthzttg'>☕ buymeacoffee.com/r26xrthzttg</a></span></footer>
<script>
let all=[];
const grid=document.getElementById('books'),f=document.getElementById('f'),count=document.getElementById('count');
const catLabel={library_linux:'coding',hackerpack:'hacking'};
async function load(){
 const r=await fetch('/api/library');const d=await r.json();all=d.books||[];
 const cats=[...new Set(all.map(b=>b.category))];
 document.getElementById('filters').innerHTML='<span class=chip data-c=ALL>all</span>'+
  cats.map(c=>'<span class=chip data-c="'+c+'">'+(catLabel[c]||c)+'</span>').join('');
 document.querySelectorAll('#filters .chip').forEach(ch=>ch.onclick=()=>render(ch.dataset.c));
 render('ALL');
}
function render(cat){
 const q=f.value.toLowerCase();
 const rows=all.filter(b=>(cat==='ALL'||b.category===cat)&&b.title.toLowerCase().includes(q));
 count.textContent=rows.length+' of '+all.length+' books';
 grid.innerHTML=rows.map(b=>"<div class='card'><b>"+esc(b.title)+"</b><span>"+
  (catLabel[b.category]||b.category)+" · "+b.format+" · "+(b.mb)+'MB</span>'+
  (b.download?"<a href='"+b.download+"'>download →</a>":"")+"</div>").join('');
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
f.oninput=()=>render(document.querySelector('#filters .chip[data-c].on')?.dataset.c||'ALL');
document.querySelectorAll('#filters .chip').forEach(ch=>{ch.onclick=()=>{
 document.querySelectorAll('#filters .chip').forEach(x=>x.classList.remove('on'));ch.classList.add('on');render(ch.dataset.c)}});
load();
</script>
"""

PAGE_PRICING = """
<h1>Pricing</h1>
<p class='dim'>No subscriptions. No accounts-with-email-verification loops. Bitcoin only,
self-hosted BTCPay — no card processor ever sees you or us.</p>
<div class='stats'>
 <div class='stat' style='min-width:280px'><b style='color:var(--green)'>FREE</b><span>{{ free_monthly }} API credits / month + {{ free_day }} web questions / day</span></div>
 <div class='stat' style='min-width:280px'><b>1 credit</b><span>= 1 ask (RAG + citations) or 1 search</span></div>
</div>
<h2>◈ Credit packs — one-time, never expire</h2>
<table>
<tr><th>Pack</th><th>Price</th><th>Credits</th><th>$/credit</th><th></th></tr>
{% for name, p in plans.items() %}
<tr><td><b>{{ name }}</b></td><td>${{ '%.2f'|format(p.usd) }}</td><td>{{ p.credits }}</td><td>${{ '%.3f'|format(p.usd / p.credits) }}</td>
<td><button onclick='buy("{{ name }}")'>BUY ⟶</button></td></tr>
{% endfor %}
</table>
<p class='dim' id='inv'></p>
<h2>◈ Why paid tiers exist</h2>
<div class='grid'>
 <div class='card'><b>GPU time is real</b><span>every answer runs retrieval + local inference on bare metal — electricity isn't free</span></div>
 <div class='card'><b>The free tier stays free</b><span>{{ free_monthly }}/mo forever, no card, email is just your key-recovery address</span></div>
 <div class='card'><b>Zero data resale</b><span>we sell answers, not you. no telemetry, no logs sold, ever</span></div>
 <div class='card'><b>Bitcoin only</b><span>pay from any wallet, no chargebacks, no KYC, invoices live ~15 min</span></div>
</div>
<footer><span>DRACO — the book-forged code oracle</span><span><a href='https://buymeacoffee.com/r26xrthzttg'>☕ buymeacoffee.com/r26xrthzttg</a></span></footer>
<script>
async function buy(plan){
 const el=document.getElementById('inv');el.textContent='Creating Bitcoin invoice…';
 const key=prompt('Your DRACO API key (signup free at /api):');
 if(!key)return;
 const r=await fetch('/api/create-invoice',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({plan:plan,api_key:key})});
 const d=await r.json();
 if(d.checkout_url){el.innerHTML="<a href='"+d.checkout_url+"' target=_blank>⚡ Pay "+d.amount+" BTC — open invoice →</a>";}
 else el.textContent='⚠ '+(d.error||'invoice failed');
}
</script>
"""

PAGE_API = """
<h1>API</h1>
<p class='dim'>One endpoint, RAG-grounded answers with citations. Free {{ free_monthly }} calls/month.
Works with curl, any HTTP client, or as an MCP tool for your agents.</p>

<h2>◈ Get your key</h2>
<div class='chatrow' style='max-width:520px'>
 <input id='email' type='email' placeholder='you@domain.tld'>
 <button onclick='signup()'>GET KEY</button>
</div>
<pre id='keyout' style='display:none'></pre>

<h2>◈ Ask</h2>
<pre>curl -s -X POST {{ base }}/api/ask \\
  -H 'Content-Type: application/json' \\
  -d '{"q": "explain integer overflow with C poc", "api_key": "sk-draco-..."}'</pre>
<p class='dim'>→ <code>{"answer": "...", "sources": [{"title": "...", "category": "..."}]}</code></p>

<h2>◈ Search the library raw</h2>
<pre>curl -s "{{ base }}/api/search?q=tcp+syn+flood&k=5" \\
  -H 'X-API-Key: sk-draco-...'</pre>

<h2>◈ Usage &amp; credits</h2>
<pre>curl -s {{ base }}/api/my-usage -H 'X-API-Key: sk-draco-...'</pre>

<h2>◈ MCP (for Claude / GPT / any agent)</h2>
<pre>{
  "mcpServers": {
    "draco": { "url": "{{ base }}/mcp" }
  }
}</pre>
<p class='dim'>Tools: <code>draco_ask</code> · <code>draco_search</code> · <code>draco_status</code>.
Machine-readable docs: <a href='/llms.txt'>llms.txt</a> · <a href='/openapi.json'>openapi.json</a> ·
<a href='/.well-known/ai-plugin.json'>ai-plugin.json</a></p>

<h2>◈ Rate limits &amp; rules</h2>
<table>
<tr><th>Tier</th><th>Limits</th></tr>
<tr><td>Web (no key)</td><td>{{ free_day }} questions/day per IP</td></tr>
<tr><td>Free API</td><td>{{ free_monthly }}/month, then buy credits</td></tr>
<tr><td>Paid credits</td><td>1 credit = 1 ask/search, never expire</td></tr>
<tr><td>Admin</td><td>unlimited — <a href='mailto:drjones@thetempleofdoom.com'>contact</a></td></tr>
</table>
<footer><span>DRACO — the book-forged code oracle</span><span><a href='https://buymeacoffee.com/r26xrthzttg'>☕ buymeacoffee.com/r26xrthzttg</a></span></footer>
<script>
async function signup(){
 const out=document.getElementById('keyout');out.style.display='block';
 out.textContent='minting key…';
 const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({email:document.getElementById('email').value})});
 const d=await r.json();
 out.textContent=d.api_key?("YOUR KEY (save it now):\n\n"+d.api_key+"\n\nfree tier: "+d.free_monthly+" credits/month")
   :('⚠ '+(d.error||'failed'));
}
</script>
"""
