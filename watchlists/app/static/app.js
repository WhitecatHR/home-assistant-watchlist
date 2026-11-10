(() => {
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names = {netflix:'Netflix',prime:'Prime Video',disney:'Disney+',crunchyroll:'Crunchyroll'};
  const state = {profile:1,profiles:[],library:[],connections:[],pending:[],view:'home',provider:'all',status:'all',collection:'watchlist',query:'',generation:0};
  const api = (...args) => window.WatchAPI(...args);
  const base = () => `api/profiles/${state.profile}`;
  const epName = ep => ep ? `S${ep.season} · F${ep.number}` : 'Auf dem aktuellen Stand';
  const tags = show => show.providers.map(p=>`<span class="provider-tag" style="--provider:var(--${p.provider})">${esc(names[p.provider])}</span>`).join('');
  const demo = () => document.body.dataset.demo === 'true';
  const sourcePosition = show => {
    const p=show.source_position || {};
    if(show.media_type==='movie')return show.movie_watched?'Film gesehen':show.movie_progress_set?'Film noch nicht gesehen':p.completion!=null?`Film · ${Math.round(p.completion)} %`:'Film · Stand unbekannt';
    if(p.episode!=null)return `${p.completion>=90?'Zuletzt gesehen':'Aktuell'}: S${p.season??'?'} · F${p.episode}`;
    if(p.episode_title)return `${p.season!=null?'Staffel '+p.season+' · ':''}${p.episode_title}`;
    return 'Folgenstand unbekannt';
  };
  const modal = $('#modal');
  let remoteTimer, remoteUrl, lastFocus, toastTimer,modalEpoch=0;

  function toast(message, undo) {
    clearTimeout(toastTimer);
    const box=$('#toast'); box.textContent=message; box.hidden=false;
    if (undo) {
      const btn=document.createElement('button'); btn.textContent='Rückgängig';
      btn.onclick=()=>run(async()=>{await undo(); box.hidden=true;}); box.append(btn);
    }
    toastTimer=setTimeout(()=>box.hidden=true,undo?9000:5500);
  }

  async function run(work, button) {
    if (button) button.disabled=true;
    try { return await work(); } catch(error) { toast(error.message || 'Bitte erneut versuchen.'); }
    finally { if (button?.isConnected) button.disabled=false; }
  }

  function openModal(title, body) {
    modalEpoch++;
    stopPolling(); lastFocus=document.activeElement;
    $('#modal-content').innerHTML=`<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="close" aria-label="Schließen">×</button></div><div class="modal-body">${body}</div>`;
    $('.close',modal).onclick=closeModal;
    if (!modal.open) modal.showModal();
    document.body.style.overflow='hidden';
  }

  async function closeModal() {
    modalEpoch++;
    const remote=remoteUrl; remoteUrl=null; stopPolling();
    modal.close(); document.body.style.overflow=''; lastFocus?.focus();
    if (remote && !demo()) await run(()=>api(remote,{method:'DELETE'}));
  }
  modal.addEventListener('cancel',e=>{e.preventDefault();closeModal();});
  modal.addEventListener('click',e=>{if(e.target===modal && e.clientX>0){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});

  async function load() {
    const generation=++state.generation;
    const path=base();
    const [library,connections,pending]=await Promise.all([api(`${path}/library`),api(`${path}/connections`),api(`${path}/pending`)]);
    if(generation!==state.generation)return;
    Object.assign(state,{library,connections,pending}); render();
  }

  function renderProfiles() {
    $('#profiles').innerHTML=state.profiles.map(p=>`<button class="profile" data-profile="${p.id}" aria-pressed="${p.id===state.profile}" aria-label="Profil ${esc(p.name)}"><span class="avatar" style="--person:${esc(p.color)}">${esc(p.name.charAt(0).toUpperCase())}</span><span class="name">${esc(p.name)}</span></button>`).join('');
    $$('.profile').forEach(btn=>btn.onclick=()=>run(async()=>{
      if(Number(btn.dataset.profile)===state.profile)return;
      await closeModal(); state.profile=Number(btn.dataset.profile); state.query=''; renderProfiles(); await load();
    }));
  }

  function card(show) {
    const pct=show.total ? Math.round(show.watched/show.total*100) : 0;
    return `<article class="poster-card"><button class="poster-button" data-show="${show.id}" aria-label="${esc(show.name)}, ${esc(show.native||show.media_type==='movie'?sourcePosition(show):epName(show.next_episode))}">
      ${show.image ? `<img src="${esc(show.image)}" alt="Cover: ${esc(show.name)}" loading="lazy" draggable="false">` : `<div class="poster-placeholder">${esc(show.name)}</div>`}
      ${show.user_status==='paused'?'<span class="poster-label">Pausiert</span>':show.upcoming?'<span class="poster-label">Weitere Folgen angekündigt</span>':''}
      <span class="poster-info"><strong>${esc(show.native||show.media_type==='movie'||(Object.keys(show.source_position||{}).length&&!show.manual_episode_progress)?sourcePosition(show):show.watched?epName(show.next_episode):show.activity?.length?'Sehverlauf vorhanden':'Noch nicht begonnen')}</strong><small>${show.native?'Direkt aus dem Anbieterprofil':show.media_type==='movie'?'Film':show.watched+' / '+show.total+' Folgen gesehen'}</small></span>
      <span class="poster-progress"><span style="width:${pct}%"></span></span></button><h3 class="poster-title">${esc(show.name)}</h3><div class="provider-tags">${tags(show)}</div></article>`;
  }

  function bindCards() {
    $$('.poster-button').forEach(btn=>{
      const show=state.library.find(x=>x.id===Number(btn.dataset.show));
      let timer, origin, held=false;
      const cancel=()=>{clearTimeout(timer);timer=null;};
      btn.addEventListener('pointerdown',e=>{if(e.button!==0)return; held=false; origin={x:e.clientX,y:e.clientY};timer=setTimeout(()=>{held=true;quick(show);navigator.vibrate?.(20);},550);});
      btn.addEventListener('pointermove',e=>{if(origin&&Math.hypot(e.clientX-origin.x,e.clientY-origin.y)>10)cancel();});
      btn.addEventListener('pointerup',cancel);btn.addEventListener('pointercancel',cancel);btn.addEventListener('pointerleave',cancel);
      btn.addEventListener('click',()=>{if(held){held=false;return;}run(()=>detail(show));});
      btn.addEventListener('contextmenu',e=>{e.preventDefault();cancel();quick(show);});
    });
  }

  function render() {
    renderProfiles();
    $$('.dock button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
    if(state.view==='connections'){renderConnections();return;}
    const profile=state.profiles.find(p=>p.id===state.profile);
    const main=$('#main');
    let library=state.library.filter(s=>(state.provider==='all'||s.providers.some(p=>p.provider===state.provider)) && (state.status==='all'||(state.status==='planned'?s.watched===0&&!s.native:s.user_status===state.status)) && s.name.toLowerCase().includes(state.query.toLowerCase()) && (state.collection==='legacy'?s.legacy_only:state.collection==='all'?true:!s.legacy_only&&(state.collection==='watchlist'?s.providers.some(p=>p.on_watchlist):s.providers.some(p=>!p.on_watchlist)||s.activity?.length||s.source_position?.provider_id)));
    const continuing=library.filter(s=>s.watched>0&&s.next_episode&&s.user_status==='watching').sort((a,b)=>b.watched-a.watched);
    const featured=continuing[0] || library[0];
    const home=state.view==='home';
    main.innerHTML=`<section class="intro"><div><div class="eyebrow">${esc(profile.name)}s Film- und Serienwelt</div><h1>${home?'Heute geht’s weiter.':'Deine Merkliste.'}</h1><p>${home?'Alles, was du schauen möchtest. Dein eigener Stand.':'Filme, Serien und Dienste an einem Ort.'}</p></div><span class="pill">${library.length} Titel · 4 Dienste</span></section>
      ${home&&featured?`<section class="hero">${featured.image?`<img class="hero-visual" src="${esc(featured.image)}" alt="">`:''}<div class="hero-copy"><div class="kicker">${tags(featured)}<span>· ${featured.watched?'Weiterschauen':'Für deinen nächsten Serienabend'}</span></div><h2>${esc(featured.name)}</h2><p>${esc(featured.summary?.slice(0,170)||'Dein nächster Serienabend wartet.')}…</p><button class="primary" id="hero-open">${featured.next_episode?epName(featured.next_episode)+' · Folgen öffnen':'Serie öffnen'} <span>↗</span></button></div></section>`:''}
      <div class="section-heading"><h2>${home?'Dein Regal':'Deine Titel'}</h2><button class="text-button" id="add-link">＋ Titel hinzufügen</button></div>
      <select id="collection-filter" aria-label="Listenquelle"><option value="watchlist">Merkliste</option><option value="history">Sehverlauf</option><option value="legacy">Frühere Importe prüfen</option><option value="all">Alles anzeigen</option></select>
      <div class="filters" aria-label="Nach Dienst filtern"><button class="filter ${state.provider==='all'?'active':''}" data-filter="all">Alle Dienste</button>${Object.entries(names).map(([k,v])=>`<button class="filter ${state.provider===k?'active':''}" data-filter="${k}">${v}</button>`).join('')}</div>
      ${!home?`<div class="actions"><input class="search-filter" id="library-search" type="search" value="${esc(state.query)}" placeholder="In deiner Liste suchen" aria-label="In deiner Liste suchen"><select class="status-select" id="status-filter" aria-label="Serienstatus"><option value="all">Alle Status</option><option value="planned">Noch nicht begonnen</option><option value="watching">Am Schauen</option><option value="paused">Pausiert</option><option value="finished">Abgeschlossen</option></select></div><br>`:''}
      ${library.length?`<div class="cover-grid">${library.map(card).join('')}</div><p class="source-note" style="margin-top:24px">Antippen für Folgen · Gedrückt halten für Schnellaktionen. Ein manuell zugeordneter Dienst bestätigt keine Übernahme in dessen Merkliste.</p>`:`<div class="empty"><h2>${state.library.length?'Hier ist gerade nichts.':'Platz für deine Lieblingsserien.'}</h2><p>${state.library.length?'Passe deine Filter an.':'Suche eine Serie und ordne sie einem Dienst zu. Du kannst sofort deinen eigenen Folgenstand pflegen.'}</p><button class="primary" id="empty-add">Erste Serie hinzufügen</button></div>`}`;
    $('#hero-open')?.addEventListener('click',()=>run(()=>detail(featured)));
    $('#add-link').onclick=()=>search(); $('#empty-add')?.addEventListener('click',()=>search());
    $('#collection-filter').value=state.collection;$('#collection-filter').onchange=e=>{state.collection=e.target.value;render();};
    $$('[data-filter]').forEach(b=>b.onclick=()=>{state.provider=b.dataset.filter;render();});
    if($('#status-filter')){$('#status-filter').value=state.status;$('#status-filter').onchange=e=>{state.status=e.target.value;render();};}
    $('#library-search')?.addEventListener('input',e=>{const pos=e.target.selectionStart;state.query=e.target.value;render();const input=$('#library-search');input.focus();input.setSelectionRange(pos,pos);});
    bindCards();
  }

  async function detail(show, selectedSeason) {
    if(show.native || show.media_type==='movie'){nativeDetail(show);return;}
    const path=base(), profile=state.profile;
    const episodes=await api(`${path}/library/${show.id}/episodes`);
    if(profile!==state.profile)return;
    const seasons=[...new Set(episodes.map(e=>e.season))];
    const season=selectedSeason??show.next_episode?.season??seasons.find(s=>s>0)??0;
    openModal(show.name,`<div class="modal-summary">${show.image?`<img src="${esc(show.image)}" alt="Cover: ${esc(show.name)}">`:'<div></div>'}<div><div class="provider-tags">${tags(show)}</div><p style="margin:14px 0">${esc(show.summary?.slice(0,450)||'Keine Beschreibung vorhanden.')}</p><span class="pill">${show.watched} von ${show.total} ausgestrahlten Folgen gesehen</span></div></div>
      <div class="actions"><button class="secondary" id="detail-quick">Schnellaktionen</button><button class="text-button" id="refresh-show">Folgen aktualisieren</button></div>
      ${show.providers.map(p=>`<p class="source-note">${esc(names[p.provider])}: ${p.source==='manual'?'manuell zugeordnet, keine Änderung beim Streamingdienst':p.on_watchlist?'auf der Anbieter-Merkliste beobachtet':'aus dem Sehverlauf importiert'}</p>`).join('')}
      ${show.activity?.length?`<div class="notice">Letzte importierte Aktivität: ${show.activity.map(a=>`${esc(names[a.provider])} · ${a.payload.season!=null?`S${a.payload.season} · F${a.payload.episode}`:'Folge nicht eindeutig erkannt'} · ${a.payload.completion==null?'Abschluss unbekannt':Math.round(a.payload.completion)+' %'}`).join('<br>')}. Nur eindeutig zugeordnete Folgen ab 90 % werden automatisch als gesehen markiert.</div>`:''}
      <div class="episode-head"><h3 style="margin:0">Deine Folgen</h3><select id="season" aria-label="Staffel wählen">${seasons.map(s=>`<option value="${s}" ${s===season?'selected':''}>${s===0?'Specials':'Staffel '+s}</option>`).join('')}</select></div>
      <div class="episode-list">${episodes.filter(e=>e.season===season).map(e=>`<div class="episode-row"><label><input type="checkbox" data-episode="${e.id}" ${e.watched?'checked':''} aria-label="${esc(e.name)} gesehen"><span><strong>${e.number??'S'} · ${esc(e.name)}</strong><small>${e.airdate?esc(e.airdate):'Ausstrahlung unbekannt'}${e.source==='manual'?' · selbst markiert':''}</small></span></label>${e.number&&e.season>0?`<button class="through" data-through="${e.id}">Bis hier gesehen</button>`:''}</div>`).join('') || '<p class="muted">Keine Episoden im Katalog gefunden.</p>'}</div>`);
    $('#season').onchange=e=>run(()=>detail(show,Number(e.target.value)));
    $('#detail-quick').onclick=()=>quick(show);
    $('#refresh-show').onclick=e=>run(async()=>{await api(`${path}/library/${show.id}/refresh`,{method:'POST'});await load();await detail(state.library.find(x=>x.id===show.id),season);toast('Episoden aktualisiert.');},e.currentTarget);
    $$('[data-episode]',modal).forEach(input=>input.onchange=()=>run(async()=>{
      const watched=input.checked;input.disabled=true;
      try{await api(`${path}/library/${show.id}/episodes`,{method:'PATCH',body:{episode_id:Number(input.dataset.episode),watched}});await load();toast(watched?'Folge als gesehen markiert.':'Folge wieder offen.',async()=>{await api(`${path}/library/${show.id}/episodes`,{method:'PATCH',body:{episode_id:Number(input.dataset.episode),watched:!watched}});await load();await detail(state.library.find(x=>x.id===show.id),season);});}
      catch(e){input.checked=!watched;throw e;}finally{input.disabled=false;}
    }));
    $$('[data-through]',modal).forEach(btn=>btn.onclick=()=>run(async()=>{
      if(!confirm('Alle regulären Folgen bis einschließlich dieser Folge für dein Profil als gesehen markieren?'))return;
      await api(`${path}/library/${show.id}/episodes`,{method:'PATCH',body:{episode_id:Number(btn.dataset.through),watched:true,through:true}});
      await load();await detail(state.library.find(x=>x.id===show.id),season);toast('Dein Folgenstand wurde aktualisiert.');
    },btn));
  }

  function quick(show) {
    if(show.native || show.media_type==='movie'){nativeDetail(show);return;}
    const path=base();
    openModal(show.name,`<p class="muted">Schnellaktionen für ${esc(state.profiles.find(p=>p.id===state.profile).name)}</p><div class="quick-actions">${show.next_episode?`<button id="next-watched">✓ ${epName(show.next_episode)} als gesehen markieren</button>`:''}<button id="quick-details">Folgen und Fortschritt öffnen</button><button data-status="${show.user_status==='paused'?'watching':'paused'}">${show.user_status==='paused'?'▶ Weiter verfolgen':'Ⅱ Serie pausieren'}</button><button data-status="finished">Als abgeschlossen kennzeichnen</button><button id="quick-remove" class="danger">Aus meiner Übersicht entfernen</button></div>`);
    $('#next-watched')?.addEventListener('click',e=>run(async()=>{await api(`${path}/library/${show.id}/episodes`,{method:'PATCH',body:{episode_id:show.next_episode.id,watched:true}});await closeModal();await load();toast('Folge gesehen.',async()=>{await api(`${path}/library/${show.id}/episodes`,{method:'PATCH',body:{episode_id:show.next_episode.id,watched:false}});await load();});},e.currentTarget));
    $('#quick-details').onclick=()=>run(()=>detail(show));
    $$('[data-status]',modal).forEach(btn=>btn.onclick=()=>run(async()=>{await api(`${path}/library/${show.id}`,{method:'PATCH',body:{status:btn.dataset.status}});await closeModal();await load();},btn));
    $('#quick-remove').onclick=e=>run(async()=>{if(!confirm('Serie aus deiner Übersicht entfernen? Dein gesehener Fortschritt bleibt gespeichert.'))return;await api(`${path}/library/${show.id}`,{method:'DELETE'});await closeModal();await load();},e.currentTarget);
  }

  function search(observation) {
    openModal(observation?'Katalogdaten ergänzen':'Film oder Serie suchen',`<p class="muted">${observation?`Gefunden bei ${esc(names[observation.provider])}: ${esc(observation.title)}. ${observation.count||1} zusammengehörige Einträge werden gemeinsam zugeordnet. Der Titel bleibt auch ohne Katalogdaten in deiner Liste.`:'Filme suchen wir über Cinemeta, Serien über TVmaze. Die Dienstzuordnung bleibt lokal.'}</p><select id="catalog-kind" aria-label="Film oder Serie"><option value="series">Serien</option><option value="movie">Filme</option></select><form id="search-form" class="search-form"><input id="search-query" type="search" required minlength="2" maxlength="100" placeholder="Titel …" value="${esc(observation?.search_query||observation?.title||'')}" aria-label="Serientitel"><button class="primary">Suchen</button></form>${observation?'':`<select id="add-provider" class="compact-select" aria-label="Dienst zuordnen">${Object.entries(names).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>`}<div id="search-results" class="results"></div>`);
    if(observation&&state.library.find(s=>s.id===observation.native_show_id)?.media_type==='movie')$('#catalog-kind').value='movie';
    const epoch=modalEpoch,profilePath=base();
    $('#search-form').onsubmit=e=>{e.preventDefault();const q=$('#search-query').value;run(async()=>{
      $('#search-results').innerHTML='<p class="muted">Titel werden gesucht …</p>';
      const results=await api(`api/catalog?q=${encodeURIComponent(q)}&kind=${$('#catalog-kind').value}`);
      if(epoch!==modalEpoch||!modal.open)return;
      $('#search-results').innerHTML=results.map(s=>`<article class="result">${s.image?.medium?`<img src="${esc(s.image.medium)}" alt="Cover: ${esc(s.name)}">`:'<div></div>'}<div><h3>${esc(s.name)}</h3><small>${esc(s.premiered?.slice(0,4)||'Jahr unbekannt')} · ${esc(s.type||'Serie')}</small></div><button class="secondary" data-add="${s.id}">${observation?'Zuordnen':'Hinzufügen'}</button></article>`).join('')||'<p class="muted">Kein passender Titel gefunden. Versuche auch den Originaltitel.</p>';
      $$('[data-add]',modal).forEach(btn=>btn.onclick=()=>run(async()=>{
        const body={show_id:Number(btn.dataset.add),provider:observation?.provider||$('#add-provider').value};
        await api(observation?`${profilePath}/pending/${observation.id}`:`${profilePath}/library`,{method:'POST',body});
        await closeModal();await load();toast(observation?'Import zugeordnet.':'Serie zu deiner Übersicht hinzugefügt.');
      },btn));
    },$('button',e.currentTarget));};
    $('#search-query').focus();
  }

  function nativeDetail(show){
    const path=`${base()}/library/${show.id}`,p=show.source_position||{},pending=state.pending.find(o=>o.native_show_id===show.id&&!o.legacy);
    openModal(show.name,`<div class="modal-summary">${show.image?`<img src="${esc(show.image)}" alt="Cover: ${esc(show.name)}">`:'<div></div>'}<div><div class="provider-tags">${tags(show)}</div><p>${esc(show.summary||'')}</p><strong>${esc(sourcePosition(show))}</strong><p class="source-note">${show.position_manual?'Dein manuell gesetzter Stand hat Vorrang.':p.completion!=null?Math.round(p.completion)+' % laut Anbieter.':'Der Anbieter hat noch keinen eindeutigen Folgenabschluss geliefert.'}</p></div></div>
      ${show.native?`<label>Medientyp <select id="native-kind"><option value="unknown">Noch nicht bestimmt</option><option value="series">Serie</option><option value="movie">Film</option></select></label>`:''}
      ${show.media_type==='movie'?`<label class="episode-row"><input type="checkbox" id="movie-seen" ${show.movie_watched?'checked':''}> Film gesehen</label>`:show.native?`<form id="native-position"><h3>Deinen Folgenstand korrigieren</h3><div class="actions"><label>Staffel <input id="native-season" type="number" min="0" max="999" required value="${p.season??''}" style="width:95px"></label><label>Folge <input id="native-episode" type="number" min="1" max="9999" required value="${p.episode??''}" style="width:95px"></label></div><label class="episode-row"><input type="checkbox" id="native-complete" ${p.completion>=90?'checked':''}> Diese Folge vollständig gesehen</label><button class="primary">Stand speichern</button>${show.position_manual?'<button type="button" class="secondary" id="native-auto">Wieder Anbieterstand verwenden</button>':''}</form>`:''}
      <div class="actions" style="margin-top:24px">${pending?'<button class="secondary" id="native-metadata">Katalogdaten ergänzen (optional)</button>':''}<button class="text-button danger" id="native-remove">Aus meiner Übersicht entfernen</button></div>`);
    const epoch=modalEpoch;
    if($('#native-kind')){$('#native-kind').value=show.media_type;$('#native-kind').onchange=e=>run(async()=>{if(e.target.value==='unknown')return;await api(path+'/kind',{method:'PATCH',body:{media_type:e.target.value}});await load();nativeDetail(state.library.find(s=>s.id===show.id));});}
    $('#movie-seen')?.addEventListener('change',e=>{const watched=e.target.checked;run(async()=>{await api(path+'/watched',{method:'PATCH',body:{watched}});await load();if(epoch===modalEpoch&&modal.open)nativeDetail(state.library.find(s=>s.id===show.id));});});
    if($('#native-position'))$('#native-position').onsubmit=e=>{e.preventDefault();run(async()=>{await api(path+'/position',{method:'PATCH',body:{season:Number($('#native-season').value),episode:Number($('#native-episode').value),completion:$('#native-complete').checked?100:0}});await load();nativeDetail(state.library.find(s=>s.id===show.id));toast('Dein persönlicher Folgenstand ist gespeichert.');},$('button',e.currentTarget));};
    $('#native-auto')?.addEventListener('click',()=>run(async()=>{await api(path+'/position',{method:'PATCH',body:{clear:true}});await load();nativeDetail(state.library.find(s=>s.id===show.id));}));
    $('#native-metadata')?.addEventListener('click',()=>search(pending));
    $('#native-remove').onclick=()=>run(async()=>{await api(path,{method:'DELETE'});await closeModal();await load();});
  }

  function renderConnections() {
    const p=state.profiles.find(p=>p.id===state.profile);
    const pendingRows=rows=>rows.map(o=>`<div class="pending-row"><div><h3>${esc(o.title)}</h3><small>${esc(names[o.provider])} · ${(o.sections||[o.section]).map(s=>s==='watchlist'?'Merkliste':'Verlauf').join(' + ')} · ${o.count||1} Einträge</small><p class="source-note">${(o.examples||[]).map(esc).join('<br>')}</p></div><div><button class="secondary" data-resolve="${o.id}">${o.legacy?'Prüfen':'Metadaten (optional)'}</button>${o.legacy?`<button class="text-button" data-dismiss="${o.id}">Ausblenden</button>`:''}</div></div>`).join('');
    const fresh=state.pending.filter(o=>!o.legacy),legacy=state.pending.filter(o=>o.legacy);
    $('#main').innerHTML=`<section class="intro"><div><div class="eyebrow">Deine Verbindungen</div><h1>Ein Zuhause für alles.</h1><p>Die Streamingprofile von ${esc(p.name)}. Getrennt von der zweiten Person.</p></div><span class="pill">Lokale Speicherung</span></section><div class="notice"><strong>Browserimporte · experimentell</strong><br>Der Browser läuft auf eurem Home-Assistant-Rechner. Melde dich hier selbst an und wähle dein Streamingprofil. Die vier Websiteadapter wurden noch nicht mit euren Konten geprüft. Disney+-Folgenstände sind in dieser Version manuell. Fehlende oder unklare Daten werden nicht als gesehen verbucht.</div><div class="connection-grid">${state.connections.map(c=>`<article class="connection"><div class="connection-header"><h3 style="color:var(--${c.provider})">${esc(names[c.provider])}</h3><span class="connection-status">${c.source_profile?'Profil bestätigt':'Noch offen'}</span></div><small>${c.source_profile?`Streamingprofil: ${esc(c.source_profile)}`:'Eigenes Browserprofil für diese Person und diesen Dienst'}</small><p>${esc(c.message)}</p><div class="actions"><button class="primary" data-connect="${c.provider}">${c.source_profile?'Anmeldung öffnen':'Verbinden'}</button><button class="secondary" data-sync="${c.provider}" ${c.source_profile?'':'disabled'}>Jetzt einlesen</button>${c.source_profile?`<button class="text-button" data-disconnect="${c.provider}">Trennen</button>`:''}</div><p class="source-note" style="min-height:0;margin-bottom:0">${c.last_sync?'Zuletzt eingelesen: '+esc(new Date(c.last_sync).toLocaleString('de-DE')):'Noch kein erfolgreicher Import'} · ${c.enabled?'Zeitplan aktiv':'Zeitplan aus'}</p></article>`).join('')}</div>
      ${fresh.length?`<section><div class="section-heading"><h2>Katalogdaten ergänzen</h2><span class="pill">Optional · ${fresh.length} Titel</span></div><p class="muted">Neu eingelesene Titel sind bereits in deiner Liste. Eine Zuordnung ergänzt Cover und Episodeninformationen. Staffel- und Folgeneinträge werden zusammengefasst.</p>${pendingRows(fresh)}</section>`:''}
      ${legacy.length?`<details style="margin-top:30px"><summary>Frühere Importe aus Version 0.1 prüfen (${legacy.length} Titel)</summary><p class="muted">Diese Einträge stammen aus dem früheren, unbestätigten Import. Sie sind erhalten und werden nicht als neue Watchlist vorausgesetzt. Nach dem Update zuerst neu einlesen.</p>${pendingRows(legacy)}</details>`:''}
      <section class="settings-row"><label for="profile-name">Dein Profilname</label><input id="profile-name" value="${esc(p.name)}" maxlength="40"><button class="secondary" id="save-name">Speichern</button><a class="text-button" href="api/export" download id="export-data">Daten exportieren ↗</a></section><p class="source-note">Beide Profile sind für berechtigte Nutzer dieser Home-Assistant-Oberfläche zugänglich. Getrennte Fortschritte sind keine zusätzliche Zugriffssperre. Browser-Anmeldungen und Cookies sind im Datenexport nicht enthalten.</p>`;
    $$('[data-connect]').forEach(btn=>btn.onclick=()=>run(()=>connect(btn.dataset.connect),btn));
    $$('[data-sync]').forEach(btn=>btn.onclick=()=>run(async()=>{toast('Die Website wird eingelesen. Das kann etwas dauern.');let r;try{r=await api(`${base()}/connections/${btn.dataset.sync}/sync`,{method:'POST'});}finally{await load();}toast(r.message);},btn));
    $$('[data-disconnect]').forEach(btn=>btn.onclick=()=>run(async()=>{if(!confirm('Anmeldung für dieses Profil und diesen Dienst lokal löschen? Importierte Serien und Fortschritte bleiben bestehen.'))return;await api(`${base()}/connections/${btn.dataset.disconnect}`,{method:'DELETE'});await load();},btn));
    $$('[data-resolve]').forEach(btn=>btn.onclick=()=>search(state.pending.find(o=>o.id===Number(btn.dataset.resolve))));
    $$('[data-dismiss]').forEach(btn=>btn.onclick=()=>run(async()=>{await api(`${base()}/pending/${btn.dataset.dismiss}`,{method:'DELETE'});await load();},btn));
    $$('.connection').forEach((card,i)=>{
      const c=state.connections[i],button=document.createElement('button');button.className='text-button';button.textContent='Importdetails';
      button.onclick=()=>{let report={};try{report=JSON.parse(c.last_report||'{}');}catch{}openModal(names[c.provider]+' · Importdetails',`<p class="muted">Dieser Bericht enthält Bereiche, Zähler und Fehlermeldungen. Keine Cookies oder Anmeldetokens.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(report,null,2))}</pre>`);};card.append(button);
    });
    $('#save-name').onclick=e=>run(async()=>{await api(base(),{method:'PATCH',body:{name:$('#profile-name').value}});state.profiles=await api('api/profiles');render();toast('Profilname gespeichert.');},e.currentTarget);
    if(demo())$('#export-data').onclick=e=>{e.preventDefault();toast('Der Datenexport ist im installierten Add-on verfügbar.');};
  }

  function stopPolling(){clearTimeout(remoteTimer);remoteTimer=null;}
  async function connect(provider) {
    if(demo()){toast('Kontoanmeldung ist nur im installierten Add-on möglich. Diese Vorschau verwendet Beispieldaten.');return;}
    const path=`${base()}/connections/${provider}`;
    const c=state.connections.find(c=>c.provider===provider);
    openModal(`${names[provider]} verbinden`,`<p class="muted">1. Im Bild anmelden und das richtige Streamingprofil wählen.<br>2. Zum Tippen zuerst ein Feld im Bild antippen, dann Text unten eingeben.<br>3. Den Profilnamen unten bestätigen. Dein Passwort wird nicht in der App-Datenbank gespeichert.</p><div class="zoom-row"><span>Ansicht vergrößern</span><input type="range" id="remote-zoom" min="30" max="100" value="45" aria-label="Browseransicht vergrößern"></div><div class="remote" id="remote-frame"><img id="remote-image" width="576" alt="Anmeldeseite des Streamingdienstes auf eurem lokalen Rechner"></div><p class="source-note" id="remote-status">Browser wird gestartet …</p><form class="remote-entry" id="remote-input"><input id="remote-text" type="password" autocomplete="off" placeholder="Text ins ausgewählte Feld" aria-label="Text für das ausgewählte Browserfeld"><button class="primary">Senden</button></form><div class="remote-controls"><button data-key="Tab">Nächstes Feld</button><button data-key="Enter">Enter</button><button data-key="Backspace">⌫</button><button data-key="ControlOrMeta+A">Alles auswählen</button><button data-scroll="-650">↑ Seite</button><button data-scroll="650">↓ Seite</button><button data-section="watchlist">Merkliste öffnen</button>${provider!=='disney'?'<button data-section="history">Verlauf öffnen</button>':''}</div><form id="binding" class="binding-form"><label for="source-profile">Name des ausgewählten Streamingprofils</label><input type="text" id="source-profile" required maxlength="80" value="${esc(c.source_profile)}" placeholder="z. B. dein Profilname"><label><input type="checkbox" id="auto-sync" ${c.enabled?'checked':''}> Regelmäßig einlesen (standardmäßig alle 6 Stunden)</label><p class="source-note">Die Bestätigung ist deine Zuordnung. Die Websiteadapter können den Profilnamen noch nicht zuverlässig selbst verifizieren.</p><button class="primary">Profil bestätigen und schließen</button></form>`);
    await api(`${path}/browser`,{method:'POST'});remoteUrl=`${path}/browser`;
    const image=$('#remote-image'), status=$('#remote-status');
    let screenshotUrl;
    const update=async()=>{
      if(!remoteUrl || !image.isConnected)return;
      try{
        const response=await fetch(`${remoteUrl}?t=${Date.now()}`,{cache:'no-store',credentials:'same-origin'});
        if(!response.ok){const r=await response.json();throw new Error(r.detail);}
        const blob=await response.blob();if(!image.isConnected)return;
        const old=screenshotUrl;screenshotUrl=URL.createObjectURL(blob);image.src=screenshotUrl;if(old)URL.revokeObjectURL(old);
        const browserStatus=await api(`${remoteUrl}/status`);
        status.textContent=browserStatus.message || 'Browser läuft auf eurem Home-Assistant-Rechner. Vergrößern und scrollen ist möglich.';
      }catch(e){status.textContent=e.message;}
      if(remoteUrl)remoteTimer=setTimeout(update,2000);
    };
    const act=body=>run(()=>api(`${path}/browser/action`,{method:'POST',body}));
    let origin;
    image.addEventListener('pointerdown',e=>origin={x:e.clientX,y:e.clientY});
    image.addEventListener('pointercancel',()=>origin=null);
    image.addEventListener('pointerup',e=>{if(!origin||Math.hypot(e.clientX-origin.x,e.clientY-origin.y)>10)return;origin=null;const r=image.getBoundingClientRect();act({kind:'click',x:Math.min(1279,Math.max(0,Math.round((e.clientX-r.left)/r.width*1280))),y:Math.min(899,Math.max(0,Math.round((e.clientY-r.top)/r.height*900)))});});
    $('#remote-zoom').oninput=e=>image.style.width=`${1280*Number(e.target.value)/100}px`;
    $('#remote-input').onsubmit=e=>{e.preventDefault();const input=$('#remote-text');const text=input.value;input.value='';act({kind:'type',text});};
    $$('[data-key]',modal).forEach(b=>b.onclick=()=>act({kind:'key',key:b.dataset.key}));
    $$('[data-scroll]',modal).forEach(b=>b.onclick=()=>act({kind:'scroll',dy:Number(b.dataset.scroll)}));
    $$('[data-section]',modal).forEach(b=>b.onclick=()=>act({kind:'section',section:b.dataset.section}));
    $('#binding').onsubmit=e=>{e.preventDefault();run(async()=>{await api(path,{method:'PATCH',body:{source_profile:$('#source-profile').value,enabled:$('#auto-sync').checked}});await closeModal();await load();toast('Profil bestätigt. Jetzt kannst du den ersten Import prüfen.');},$('button',e.currentTarget));};
    await update();
  }

  $$('.dock button').forEach(btn=>btn.onclick=()=>{state.view=btn.dataset.view;render();window.scrollTo({top:0,behavior:'auto'});});
  $('#search-button').onclick=()=>search();
  $('.brand').onclick=e=>{e.preventDefault();state.view='home';render();};
  async function start(){try{state.profiles=await api('api/profiles');if(demo())$('#demo-banner').hidden=false;await load();}catch(e){$('#main').innerHTML=`<div class="error-box">${esc(e.message)}<br><button class="secondary" id="retry">Erneut versuchen</button></div>`;$('#retry').onclick=start;}}
  window.WatchApp={state,start,render,detail,quick,search,closeModal,esc};
  start();
})();
