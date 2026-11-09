/* Explicitly labelled, browser-local demo. This is not the add-on's database or a live connection. */
(() => {
  const key='watchlists-preview-v1';
  let seed, saved;
  const ready=fetch('static/demo-data.json').then(r=>r.json()).then(data=>{
    seed=data;
    try{saved=JSON.parse(localStorage.getItem(key));}catch{}
    if(!saved||saved.version!==1){
      saved={version:1,profiles:[{id:1,name:'Alex',color:'#d5a377'},{id:2,name:'Sam',color:'#a5b9a8'}],library:{1:{},2:{}},progress:{1:{},2:{}},states:{1:{},2:{}}};
      seed.forEach((s,i)=>{
        if(i<8)saved.library[1][s.show.id]=[s.provider];
        if([0,2,3,5,8].includes(i))saved.library[2][s.show.id]=[s.provider];
        const regular=s.episodes.filter(e=>e.season>0&&e.number);
        regular.slice(0,i===0?10:i===3?3:i===5?6:i===7?9:0).forEach(e=>saved.progress[1][e.id]=true);
        if(i===0)regular.slice(0,4).forEach(e=>saved.progress[2][e.id]=true);
        if(i===5)regular.slice(0,2).forEach(e=>saved.progress[2][e.id]=true);
      });
      localStorage.setItem(key,JSON.stringify(saved));
    }
  });
  const clone=value=>JSON.parse(JSON.stringify(value));
  const library=profile=>Object.entries(saved.library[profile]).map(([id,providers])=>{
    const item=seed.find(s=>s.show.id===Number(id));
    const today=new Date().toISOString().slice(0,10);
    const episodes=item.episodes.filter(e=>e.season>0&&e.number&&e.airdate&&e.airdate<=today);
    const progress=saved.progress[profile];
    return {...item.show,image:item.show.image?.medium,user_status:saved.states[profile][id]||'watching',providers:providers.map(provider=>({provider,source:'manual',on_watchlist:1})),watched:episodes.filter(e=>progress[e.id]).length,total:episodes.length,next_episode:episodes.find(e=>!progress[e.id])||null,upcoming:item.episodes.find(e=>e.season>0&&e.airdate&&e.airdate>today)||null,activity:[]};
  }).sort((a,b)=>a.name.localeCompare(b.name));
  window.WatchAPI=async(path,options={})=>{
    await ready;
    const method=options.method||'GET', body=options.body;
    if(path==='api/profiles')return clone(saved.profiles);
    if(path.startsWith('api/catalog?')){
      const q=new URLSearchParams(path.split('?')[1]).get('q').toLowerCase();
      return clone(seed.map(s=>s.show).filter(s=>s.name.toLowerCase().includes(q)));
    }
    const m=path.match(/^api\/profiles\/(\d+)(.*)$/);
    if(!m)throw new Error('In dieser Vorschau nicht verfügbar.');
    const profile=Number(m[1]), suffix=m[2];
    if(!saved.library[profile])throw new Error('Profil nicht gefunden.');
    const persist=()=>{localStorage.setItem(key,JSON.stringify(saved));return{ok:true};};
    if(!suffix&&method==='PATCH'){
      if(!body.name.trim())throw new Error('Bitte einen Profilnamen eingeben.');
      saved.profiles.find(p=>p.id===profile).name=body.name.trim();return persist();
    }
    if(suffix==='/library'&&method==='GET')return clone(library(profile));
    if(suffix==='/library'&&method==='POST'){
      if(!seed.some(s=>s.show.id===body.show_id))throw new Error('Serie nicht im Beispielkatalog.');
      const current=saved.library[profile][body.show_id]||[];
      if(!current.includes(body.provider))current.push(body.provider);
      saved.library[profile][body.show_id]=current;return persist();
    }
    if(suffix==='/pending')return [];
    if(suffix==='/connections')return Object.keys({netflix:1,prime:1,disney:1,crunchyroll:1}).map(provider=>({provider,source_profile:'',enabled:0,message:'Vorschau: keine Streamingkonten verbunden.',last_sync:null}));
    const showMatch=suffix.match(/^\/library\/(\d+)(.*)$/);
    if(showMatch){
      const id=Number(showMatch[1]), action=showMatch[2], item=seed.find(s=>s.show.id===id);
      if(!item)throw new Error('Serie nicht gefunden.');
      if(!action&&method==='PATCH'){saved.states[profile][id]=body.status;return persist();}
      if(!action&&method==='DELETE'){delete saved.library[profile][id];return persist();}
      if(action==='/refresh')return {ok:true};
      if(action==='/episodes'&&method==='GET')return clone(item.episodes.map(e=>({...e,watched:saved.progress[profile][e.id]?1:0,source:e.id in saved.progress[profile]?'manual':null})));
      if(action==='/episodes'&&method==='PATCH'){
        const e=item.episodes.find(e=>e.id===body.episode_id);
        if(!e)throw new Error('Folge nicht gefunden.');
        const selected=body.through?item.episodes.filter(x=>x.season>0&&(x.season<e.season||(x.season===e.season&&x.number<=e.number))):[e];
        selected.forEach(x=>saved.progress[profile][x.id]=body.watched);return persist();
      }
    }
    throw new Error('Diese Aktion ist im installierten Add-on verfügbar.');
  };
})();
