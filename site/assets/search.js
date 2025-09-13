(function(){
  const input = document.getElementById('search-input');
  const results = document.getElementById('search-results');
  if(!input || !results){ return; }
  let index = [];
  let loaded = false;
  let cacheByWord = new Map();

  function prefix(path){
    return (window.ASSET_PREFIX || '') + path;
  }

  async function loadIndex(){
    if(loaded) return index;
    try{
      const url = prefix('search-index.json');
      // file:// fetch may fail due to CORS in some browsers; fallback to <script> injection
      if(location.protocol === 'file:'){
        await new Promise((resolve, reject)=>{
          const s = document.createElement('script');
          s.src = prefix('search-index.js');
          s.onload = ()=>{ resolve(); };
          s.onerror = reject;
          document.head.appendChild(s);
        });
        if(Array.isArray(window.SEARCH_INDEX)){
          index = window.SEARCH_INDEX;
        } else {
          index = [];
        }
      } else {
        const res = await fetch(url);
        index = await res.json();
      }
      loaded = true;
    }catch(e){ console.warn('search index failed', e); }
    return index;
  }

  function render(items){
    if(!items || items.length === 0){
      results.classList.remove('active');
      results.innerHTML = '';
      return;
    }
    results.classList.add('active');
    const top = items.slice(0, 20)
      .map(it => `<li><a href="${prefix(it.url)}">${escapeHtml(it.title)}</a><div style="color:#9fb3c8;font-size:13px">${escapeHtml(snippet(it.content))}</div></li>`)
      .join('');
    results.innerHTML = `<ul>${top}</ul>`;
  }

  function escapeHtml(s){
    return (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  }

  function snippet(text){
    return (text||'').slice(0,140) + (text && text.length>140 ? '…' : '');
  }

  function tokenize(q){
    return q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  }

  function scoreDoc(doc, tokens, rawQuery){
    let score = 0;
    const title = doc.title.toLowerCase();
    const content = doc.content.toLowerCase();
    const phrase = rawQuery.trim().toLowerCase();
    // Strong boosts for exact title and exact phrase
    if(title === phrase) score += 1000;
    if(title.includes(phrase)) score += 200;
    if(content.includes(phrase)) score += 50;
    for(const t of tokens){
      if(title === t) score += 20;
      if(title.includes(t)) score += 8;
      if(content.includes(t)) score += 1;
    }
    return score;
  }

  function fuzzyCandidates(tokens, rawQuery){
    const key = tokens.join(' ') + '|' + rawQuery.toLowerCase();
    if(cacheByWord.has(key)) return cacheByWord.get(key);
    const res = index.map(doc=>({score:scoreDoc(doc, tokens, rawQuery), doc}))
      .filter(x=>x.score>0)
      .sort((a,b)=> b.score - a.score || a.doc.title.localeCompare(b.doc.title))
      .map(x=>x.doc);
    cacheByWord.set(key, res);
    return res;
  }

  function searchLocal(query){
    const q = query.trim().toLowerCase();
    if(!q) return [];
    const tokens = tokenize(q);
    return fuzzyCandidates(tokens, query);
  }

  input.addEventListener('input', async (e)=>{
    const q = input.value;
    await loadIndex();
    const items = searchLocal(q);
    render(items);
  });

  // Submit behavior: go to top result
  input.form && input.form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    await loadIndex();
    const q = input.value;
    const items = searchLocal(q);
    if(items.length>0){
      location.href = prefix(items[0].url);
    }
  });

  // Dismiss on outside click
  document.addEventListener('click', (e)=>{
    if(!results.contains(e.target) && e.target !== input){
      results.classList.remove('active');
    }
  })
})();


