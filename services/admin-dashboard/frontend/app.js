const getToken = () => localStorage.getItem('ADMIN_TOKEN') || '';
const setToken = (t) => { localStorage.setItem('ADMIN_TOKEN', t); }

const apiFetch = async (path, opts={}) => {
  const token = getToken();
  const headers = Object.assign({'Content-Type':'application/json'}, opts.headers||{});
  if (token) headers['X-Admin-Token'] = token;
  const res = await fetch(path, Object.assign({headers}, opts));
  const text = await res.text();
  let data = text;
  try { data = JSON.parse(text); } catch(e){}
  return {status: res.status, data};
}

// UI bindings
document.addEventListener('DOMContentLoaded', () => {
  const tokenInput = document.getElementById('admin-token');
  const saveBtn = document.getElementById('save-token');
  const healthBtn = document.getElementById('check-health');
  const healthPre = document.getElementById('health-result');
  const tenantList = document.getElementById('tenant-list');
  const createTenantBtn = document.getElementById('create-tenant');
  // RAG pagination state is used by the router; declare early
  let ragOffset = 0;

  // routing: show page based on hash
  function showPage(name){
    document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
    const el = document.getElementById('page-' + name);
    if (el) el.style.display = '';
    // highlight nav link
    document.querySelectorAll('nav a').forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#/' + name));
  }
  function route(){
    const h = location.hash.replace('#/','') || 'home';
    const page = h.split('?')[0];
    showPage(page);
    if (h.startsWith('tenants')) loadTenants();
    if (h.startsWith('apikeys')) loadApikeysPage();
    if (h.startsWith('rag-collection')) {
      // when opening collection page, read name and call loader
      const q = h.split('?')[1] || '';
      const params = new URLSearchParams(q);
      const name = params.get('name');
      if (name) {
        // reset ragOffset to 0 when directly navigating
        ragOffset = 0;
        loadCollection(name);
      }
    }
  }
  window.addEventListener('hashchange', route);
  // initial route
  if(!location.hash) location.hash = '#/home';
  route();

  tokenInput.value = getToken();
  saveBtn.onclick = () => { setToken(tokenInput.value.trim()); alert('saved'); loadTenants(); };

  healthBtn.onclick = async () => {
    const r = await apiFetch('/health');
    healthPre.textContent = JSON.stringify(r, null, 2);
  }

  createTenantBtn.onclick = async () => {
    const name = document.getElementById('tenant-name').value.trim();
    const desc = document.getElementById('tenant-desc').value.trim();
    if (!name) return alert('tenant name required');
    const r = await apiFetch('/admin/tenants', {method:'POST', body: JSON.stringify({name, description: desc})});
    if (r.status>=200 && r.status<300) {
      alert('created: save the returned api_key securely (one-time)');
      location.hash = '#/tenants';
      loadTenants();
    } else {
      alert('create failed: ' + JSON.stringify(r.data));
    }
  }

  window.showApiKeys = async (tenantId) => {
    const r = await apiFetch(`/admin/tenants/${tenantId}/apikeys`);
    const area = document.getElementById('apikey-list');
    const createArea = document.getElementById('create-apikey-area');
    createArea.innerHTML = `<button id="create-apikey-btn">建立 API Key</button> <span class="small">(建立會回傳一次性 plaintext)</span>`;
    document.getElementById('create-apikey-btn').onclick = async () => {
      const cr = await apiFetch(`/admin/tenants/${tenantId}/apikeys`, {method:'POST', body: JSON.stringify({name: 'ui-key'})});
      if (cr.status>=200 && cr.status<300) {
        // show plaintext api_key if returned
        const data = cr.data || {};
        const plaintext = data.api_key || data.apiKey || JSON.stringify(data);
        // show modal-like prompt
        if (window.navigator && window.navigator.clipboard) {
          try { await navigator.clipboard.writeText(plaintext); } catch(e){}
        }
        alert('API Key created — save the plaintext now (copied to clipboard if supported): ' + plaintext);
        window.showApiKeys(tenantId);
      } else {
        alert('create key failed: ' + JSON.stringify(cr.data));
      }
    };

    if (r.status>=200 && r.status<300) {
      area.innerHTML = '';
      const list = (Array.isArray(r.data) ? r.data : (r.data || []));
      if (list.length === 0) {
        area.innerHTML = '<div class="small">No API keys for this tenant.</div>';
      }
      list.forEach(k => {
        const el = document.createElement('div'); el.className='tenant';
        el.innerHTML = `<div><div><b>${k.name||k.key_prefix}</b></div><div class='meta small'>id: ${k.key_id} • status: ${k.status}</div></div>`;
        // delete button for api key if key_id available
        const delBtn = document.createElement('button'); delBtn.className='secondary'; delBtn.textContent='刪除';
        delBtn.onclick = async () => {
          if (!confirm('確定要刪除此 API Key?')) return;
          const del = await apiFetch(`/admin/apikeys/${k.key_id}`, {method:'DELETE'});
          if (del.status>=200 && del.status<300) { alert('deleted'); window.showApiKeys(tenantId); }
          else alert('delete failed: ' + JSON.stringify(del.data));
        };
        el.appendChild(delBtn);
        area.appendChild(el);
      });
      // scroll to apikey area
      area.scrollIntoView({behavior:'smooth'});
    } else {
      area.textContent = 'failed to list keys: ' + JSON.stringify(r.data);
    }
  }

  window.reloadTenants = loadTenants;
  async function loadTenants(){
    tenantList.innerHTML = 'loading...';
    const r = await apiFetch('/admin/tenants');
    if (r.status>=200 && r.status<300){
      tenantList.innerHTML = '';
      (r.data || []).forEach(t => {
        const el = document.createElement('div'); el.className='tenant';
        const left = document.createElement('div'); left.innerHTML = `<div><b>${t.name}</b></div><div class='meta small'>${t.tenant_id} • ${t.description || ''}</div>`;
        const right = document.createElement('div');
        const keysBtn = document.createElement('button'); keysBtn.className='secondary'; keysBtn.textContent='API Keys';
        keysBtn.onclick = () => { location.hash = '#/apikeys?tenant=' + t.tenant_id; loadApikeysPage(); };
        const delTenantBtn = document.createElement('button'); delTenantBtn.className='secondary'; delTenantBtn.textContent='刪除 Tenant';
        delTenantBtn.onclick = async () => {
          if (!confirm('確定要標記刪除此 tenant?')) return;
          const resp = await apiFetch(`/admin/tenants/${t.tenant_id}`, {method:'DELETE'});
          if (resp.status>=200 && resp.status<300) { alert('tenant deleted'); loadTenants(); } else alert('delete failed: ' + JSON.stringify(resp.data));
        };
        right.appendChild(keysBtn);
        right.appendChild(delTenantBtn);
        el.appendChild(left); el.appendChild(right);
        tenantList.appendChild(el);
      });
    } else {
      tenantList.innerHTML = 'failed to load tenants: ' + JSON.stringify(r.data);
    }
  }

  // Apikeys page loader
  function getQueryParam(key){
    const h = location.hash.split('?')[1] || '';
    const params = new URLSearchParams(h);
    return params.get(key);
  }
  async function loadApikeysPage(){
    const tenant = getQueryParam('tenant');
    const listArea = document.getElementById('apikey-list');
    if (!tenant){ listArea.innerHTML = '<div class="small">請從 Tenants 頁面選擇一個 tenant。</div>'; return; }
    // show create area
    document.getElementById('apikey-controls').innerHTML = `<button id="create-apikey-btn">建立 API Key for ${tenant}</button>`;
    document.getElementById('create-apikey-btn').onclick = async () => {
      const cr = await apiFetch(`/admin/tenants/${tenant}/apikeys`, {method:'POST', body: JSON.stringify({name: 'ui-key'})});
      if (cr.status>=200 && cr.status<300){ const plaintext = cr.data.api_key || JSON.stringify(cr.data); try { await navigator.clipboard.writeText(plaintext); } catch(e){}; alert('created, plaintext copied if supported: ' + plaintext); loadApikeysPage(); }
      else alert('create failed: ' + JSON.stringify(cr.data));
    };
    // fetch keys
    const r = await apiFetch(`/admin/tenants/${tenant}/apikeys`);
    if (r.status>=200 && r.status<300){
      listArea.innerHTML='';
      (r.data || []).forEach(k => {
        const el = document.createElement('div'); el.className='tenant';
        el.innerHTML = `<div><b>${k.name||k.key_prefix}</b><div class='meta small'>id: ${k.key_id} • status: ${k.status}</div></div>`;
        const del = document.createElement('button'); del.className='secondary'; del.textContent='刪除';
        del.onclick = async () => { if(!confirm('刪除?')) return; const d = await apiFetch(`/admin/apikeys/${k.key_id}`, {method:'DELETE'}); if(d.status>=200&&d.status<300){ alert('deleted'); loadApikeysPage(); } else alert('delete failed: ' + JSON.stringify(d.data)); };
        el.appendChild(del);
        listArea.appendChild(el);
      });
    } else listArea.innerHTML = 'failed: ' + JSON.stringify(r.data);
  }

  // RAG (Qdrant) handlers
  document.getElementById('rag-list-collections').onclick = async () => {
    const res = await apiFetch('/admin/rag/collections');
    // concise summary instead of full JSON
    try {
      let raw = res.data;
      if (raw && raw.collections && Array.isArray(raw.collections)) raw = raw.collections;
      const cols = Array.isArray(raw) ? raw : [];
      document.getElementById('rag-result').textContent = `status=${res.status} · collections=${cols.length}`;
    } catch (e) {
      document.getElementById('rag-result').textContent = `status=${res.status}`;
    }
    const list = document.getElementById('rag-collections-list');
    list.innerHTML = '';
    if (res.status >= 200) {
      let raw = res.data;
      // support { collections: [...] } or direct array
      if (raw && raw.collections && Array.isArray(raw.collections)) raw = raw.collections;
      if (!Array.isArray(raw)) raw = [];
      // if server returns objects, map to names
      const cols = raw.map(c => (typeof c === 'string' ? c : (c.name || c.collection_name || c.id || JSON.stringify(c))));
      cols.forEach(name => {
        const el = document.createElement('div'); el.className='tenant';
        el.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><div><b>${name}</b></div><div></div></div>`;
        const right = document.createElement('div');
        // view button
  const viewBtn = document.createElement('button'); viewBtn.className='secondary'; viewBtn.textContent='View points';
  viewBtn.onclick = () => { location.hash = '#/rag-collection?name=' + encodeURIComponent(name); };
        // delete collection button
        const del = document.createElement('button'); del.className='secondary'; del.textContent='刪除 collection';
        del.onclick = async () => { if (!confirm('刪除 collection ' + name + '?')) return; const d = await apiFetch('/admin/rag/collections/' + encodeURIComponent(name), {method:'DELETE'}); if (d.status>=200) { alert('deleted'); document.getElementById('rag-list-collections').click(); } else alert('delete failed: ' + JSON.stringify(d.data)); };
        right.appendChild(viewBtn);
        right.appendChild(del);
        el.querySelector('div').appendChild(right);
        list.appendChild(el);
      });
    }
  };
  document.getElementById('rag-create-collection').onclick = async () => {
    const name = document.getElementById('rag-collection-name').value.trim();
    if (!name) return alert('collection name required');
    const payload = {name};
    const res = await apiFetch('/admin/rag/collections', {method:'POST', body: JSON.stringify(payload)});
    try {
      document.getElementById('rag-result').textContent = `status=${res.status} · created=${res.data && res.data.created ? res.data.created : 'n/a'}`;
    } catch (e) {
      document.getElementById('rag-result').textContent = `status=${res.status}`;
    }
  };

  function updateRagPageInfo(limit){
    const pageEl = document.getElementById('rag-page-info');
    if (!pageEl) return;
    const l = parseInt(limit) || 100;
    const page = Math.floor(ragOffset / l) + 1;
    pageEl.textContent = `Page ${page}`;
  }

  document.getElementById('rag-prev').onclick = () => {
    const limitVal = parseInt(document.getElementById('rag-limit').value) || 100;
    ragOffset = Math.max(0, ragOffset - limitVal);
    updateRagPageInfo(limitVal);
    const cur = document.getElementById('rag-current-collection').textContent;
    if (cur) loadCollection(cur);
  };
  document.getElementById('rag-next').onclick = () => {
    const limitVal = parseInt(document.getElementById('rag-limit').value) || 100;
    ragOffset = ragOffset + limitVal;
    updateRagPageInfo(limitVal);
    const cur = document.getElementById('rag-current-collection').textContent;
    if (cur) loadCollection(cur);
  };
  const ragBackBtn = document.getElementById('rag-back');
  if (ragBackBtn) ragBackBtn.onclick = () => { location.hash = '#/rag'; };
  document.getElementById('rag-limit').addEventListener('change', () => { ragOffset = 0; updateRagPageInfo(document.getElementById('rag-limit').value); });

  async function loadCollection(name){
    if (!name) return;
    document.getElementById('rag-current-collection').textContent = name;
    const limitVal = parseInt(document.getElementById('rag-limit').value) || 100;
    const res = await apiFetch(`/admin/rag/collections/${encodeURIComponent(name)}/points?limit=${limitVal}&offset=${ragOffset}`);
    try {
      const pts = res.data && Array.isArray(res.data.points) ? res.data.points.length : 0;
      document.getElementById('rag-result').textContent = `status=${res.status} · points=${pts} · offset=${ragOffset}`;
    } catch (e) {
      document.getElementById('rag-result').textContent = `status=${res.status}`;
    }
    const tbody = document.getElementById('rag-points-tbody');
    tbody.innerHTML = '';
    if (res.status >= 200 && res.data && Array.isArray(res.data.points)){
      res.data.points.forEach(p => {
        const tr = document.createElement('tr');

        // normalize id for delete operations (still needed but not shown)
        let rawId = p.id;
        let idDisplay = '';
        try {
          if (rawId === null || rawId === undefined) {
            idDisplay = '';
          } else if (typeof rawId === 'string' || typeof rawId === 'number') {
            idDisplay = String(rawId);
          } else if (typeof rawId === 'object') {
            idDisplay = rawId.id || rawId.point_id || rawId.uuid || rawId.toString();
            if (!idDisplay) idDisplay = JSON.stringify(rawId);
          } else {
            idDisplay = String(rawId);
          }
        } catch (e) {
          idDisplay = String(rawId);
        }

        // extract payload fields
        let payload = p.payload || {};
        try {
          if (typeof payload === 'string') {
            try { payload = JSON.parse(payload); } catch(e) { /* leave as string */ }
          }
        } catch (e) {}

        const docTd = document.createElement('td');
        const textTd = document.createElement('td');
        const metaTd = document.createElement('td');

        const docId = (payload && typeof payload === 'object') ? (payload.doc_id || payload.id || '') : '';
        let textVal = (payload && typeof payload === 'object') ? (payload.text || '') : (payload || '');
        if (typeof textVal !== 'string') textVal = JSON.stringify(textVal);
        if (textVal.length > 300) textVal = textVal.slice(0,300) + '...';

        let metaVal = '';
        try {
          if (payload && typeof payload === 'object') {
            const md = payload.metadata || payload.meta || payload.metadata || {};
            if (md && typeof md === 'object') metaVal = JSON.stringify(md);
            else metaVal = String(md || '');
          }
        } catch (e) { metaVal = ''; }

        docTd.textContent = docId;
        textTd.textContent = textVal;
        metaTd.textContent = metaVal;

        const actionsTd = document.createElement('td');
        const del = document.createElement('button'); del.className='secondary'; del.textContent='Delete';
        del.onclick = async () => {
          if (!confirm('Delete point ' + idDisplay + ' ?')) return;
          const encodedId = encodeURIComponent(idDisplay);
          const d = await apiFetch(`/admin/rag/collections/${encodeURIComponent(name)}/points/${encodedId}`, {method: 'DELETE'});
          if (d.status >= 200 && d.status < 300 && d.data && d.data.deleted) { alert('deleted'); loadCollection(name); }
          else alert('delete failed: ' + JSON.stringify(d.data));
        };
        actionsTd.appendChild(del);

        tr.appendChild(docTd);
        tr.appendChild(textTd);
        tr.appendChild(metaTd);
        tr.appendChild(actionsTd);
        tbody.appendChild(tr);
      });
    }
    updateRagPageInfo(limitVal);
  }

  // Graph (Neo4j) handlers
  document.getElementById('graph-health').onclick = async () => {
    const res = await apiFetch('/admin/graph/health');
    document.getElementById('graph-result').textContent = JSON.stringify(res, null, 2);
  };
  document.getElementById('graph-import-sample').onclick = async () => {
    const res = await apiFetch('/admin/graph/import/sample', {method: 'POST'});
    document.getElementById('graph-result').textContent = JSON.stringify(res, null, 2);
  };
  // pagination state
  let graphOffset = 0;

  function updatePageInfo(limit){
    const pageEl = document.getElementById('graph-page-info');
    if (!pageEl) return;
    const l = parseInt(limit) || 100;
    const page = Math.floor(graphOffset / l) + 1;
    pageEl.textContent = `Page ${page}`;
  }

  // Prev / Next handlers
  const prevBtn = document.getElementById('graph-prev');
  const nextBtn = document.getElementById('graph-next');
  if (prevBtn) prevBtn.onclick = async () => {
    const limitVal = parseInt(document.getElementById('graph-limit').value) || 100;
    graphOffset = Math.max(0, graphOffset - limitVal);
    updatePageInfo(limitVal);
    document.getElementById('graph-list-records').click();
  };
  if (nextBtn) nextBtn.onclick = async () => {
    const limitVal = parseInt(document.getElementById('graph-limit').value) || 100;
    graphOffset = graphOffset + limitVal;
    updatePageInfo(limitVal);
    document.getElementById('graph-list-records').click();
  };

  // when page size changes, reset offset
  const limitInput = document.getElementById('graph-limit');
  if (limitInput) limitInput.addEventListener('change', () => { graphOffset = 0; updatePageInfo(limitInput.value); });

  document.getElementById('graph-list-records').onclick = async () => {
    const label = document.getElementById('graph-label-filter').value.trim();
    const tenantFilter = document.getElementById('graph-tenant-filter').value.trim();
    const limitVal = parseInt(document.getElementById('graph-limit').value) || 100;
    const q = new URLSearchParams();
    if (label) q.set('label', label);
    if (tenantFilter) q.set('tenant_id', tenantFilter);
    q.set('limit', String(limitVal));
    q.set('offset', String(graphOffset));

    const res = await apiFetch('/admin/graph/records?' + q.toString());
    // Avoid dumping large JSON into the page. Show a concise summary instead.
    try {
      const cnt = res.data && Array.isArray(res.data.records) ? res.data.records.length : 0;
      document.getElementById('graph-result').textContent = `status=${res.status} · records=${cnt} · offset=${graphOffset}`;
      updatePageInfo(limitVal);
    } catch (e) {
      document.getElementById('graph-result').textContent = `status=${res.status}`;
    }
    const tbody = document.getElementById('graph-records-tbody');
    tbody.innerHTML = '';
    if (res.status >= 200 && res.data && Array.isArray(res.data.records)){
      res.data.records.forEach(r => {
        const tr = document.createElement('tr');
        const labels = Array.isArray(r.labels) ? r.labels.join(',') : JSON.stringify(r.labels || []);
        const tenantInfo = r.tenant_id || '';
        const preview = r.props_preview ? String(r.props_preview) : '';

        const idTd = document.createElement('td'); idTd.textContent = r.id;
        const labelsTd = document.createElement('td'); labelsTd.textContent = labels;
        const tenantTd = document.createElement('td'); tenantTd.textContent = tenantInfo;
        const previewTd = document.createElement('td'); previewTd.textContent = preview;
        const actionsTd = document.createElement('td');

        const viewBtn = document.createElement('button'); viewBtn.className='secondary'; viewBtn.textContent='View';
        viewBtn.onclick = async () => {
          // fetch full props via cypher read
          const cy = `MATCH (n) WHERE id(n) = $id RETURN n.props_json AS props`;
          const rres = await apiFetch('/admin/graph/cypher', {method:'POST', body: JSON.stringify({cypher: cy, params: {id: r.id}, read: true})});
          if (rres.status >= 200 && rres.data && Array.isArray(rres.data.records) && rres.data.records.length>0){
            const record = rres.data.records[0];
            let props = record.props || record.props_json || record.propsJson || record;

            // If props is a JSON string, parse it to avoid double-encoding (which shows escaped quotes / backslashes)
            try {
              if (typeof props === 'string') {
                const parsed = JSON.parse(props);
                props = parsed;
              }
            } catch (e) {
              // not JSON, leave as-is
            }

            const fullText = JSON.stringify(props, null, 2);
            const maxLen = 2000; // truncate in-modal to avoid huge dumps
            const modalBody = document.getElementById('modal-body');
            // remove any existing download button
            const modal = document.getElementById('graph-props-modal');
            const content = modal.querySelector('.modal-content');
            const existingDl = content.querySelector('.modal-download-btn');
            if (existingDl) existingDl.remove();

            if (fullText.length > maxLen) {
              modalBody.textContent = fullText.slice(0, maxLen) + `\n\n... (truncated, ${fullText.length} chars)`;
              // create download button to get full JSON
              const dl = document.createElement('button');
              dl.className = 'secondary modal-download-btn';
              dl.textContent = 'Download JSON';
              dl.style.marginLeft = '8px';
              dl.onclick = () => {
                const blob = new Blob([fullText], {type: 'application/json'});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `node-${r.id}-props.json`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                setTimeout(() => URL.revokeObjectURL(url), 10000);
              };
              content.appendChild(dl);
            } else {
              modalBody.textContent = fullText;
            }
            // ensure modal is visible and centered (force styles in case CSS not loaded)
            modal.style.display = 'flex';
            modal.style.position = 'fixed';
            modal.style.left = '0';
            modal.style.top = '0';
            modal.style.right = '0';
            modal.style.bottom = '0';
            modal.style.background = 'rgba(15,23,42,0.6)';
            modal.style.alignItems = 'center';
            modal.style.justifyContent = 'center';
            modal.style.zIndex = '9999';
            if (content) {
              content.style.background = '#fff';
              content.style.padding = '16px';
              content.style.borderRadius = '8px';
              content.style.maxWidth = '800px';
              content.style.width = '90%';
            }
          } else {
            alert('failed to load props: ' + JSON.stringify(rres.data));
          }
        };

        const delBtn = document.createElement('button'); delBtn.className='secondary'; delBtn.textContent='Delete';
        delBtn.onclick = async () => {
          if (!confirm('確定要刪除 node ' + r.id + ' ?')) return;
          const d = await apiFetch('/admin/graph/nodes/' + encodeURIComponent(r.id), {method: 'DELETE'});
          if (d.status >= 200 && d.status < 300) { alert('deleted'); document.getElementById('graph-list-records').click(); }
          else alert('delete failed: ' + JSON.stringify(d.data));
        };

        actionsTd.appendChild(viewBtn);
        actionsTd.appendChild(delBtn);

        tr.appendChild(idTd);
        tr.appendChild(labelsTd);
        tr.appendChild(tenantTd);
        tr.appendChild(previewTd);
        tr.appendChild(actionsTd);
        tbody.appendChild(tr);
      });
    }
    // modal close
    const modalCloseBtn = document.getElementById('modal-close');
    if (modalCloseBtn) modalCloseBtn.onclick = () => { document.getElementById('graph-props-modal').style.display = 'none'; };
  };
  document.getElementById('graph-run-cypher').onclick = async () => {
    const cy = document.getElementById('graph-cypher').value.trim();
    if (!cy) return alert('cypher required');
    const res = await apiFetch('/admin/graph/cypher', {method:'POST', body: JSON.stringify({cypher: cy, read: true})});
    document.getElementById('graph-result').textContent = JSON.stringify(res, null, 2);
  };
  document.getElementById('graph-run-cypher-write').onclick = async () => {
    const cy = document.getElementById('graph-cypher').value.trim();
    if (!cy) return alert('cypher required');
    const res = await apiFetch('/admin/graph/cypher', {method:'POST', body: JSON.stringify({cypher: cy, read: false})});
    document.getElementById('graph-result').textContent = JSON.stringify(res, null, 2);
  };

        // ensure modal close works globally and cleans up content
        const globalModalClose = document.getElementById('modal-close');
        if (globalModalClose) {
          globalModalClose.addEventListener('click', () => {
            const modal = document.getElementById('graph-props-modal');
            if (!modal) return;
            modal.style.display = 'none';
            // cleanup modal body and any download btn
            const content = modal.querySelector('.modal-content');
            const body = document.getElementById('modal-body');
            if (body) body.textContent = '';
            const existingDl = content && content.querySelector('.modal-download-btn');
            if (existingDl) existingDl.remove();
          });
        }
  loadTenants();
});
