import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Window} from 'happy-dom';
import * as css from 'css-tree';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const staticDir=path.join(root,'watchlists/app/static');
const seedPath=process.env.WATCHLIST_DEMO_SEED || path.join(root,'preview/demo-data.json');
const seed=JSON.parse(fs.readFileSync(seedPath));
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const until=async predicate=>{for(let i=0;i<100;i++){if(predicate())return;await wait(15);}throw new Error('UI condition timed out');};
const errors=[];
const w=new Window({url:'https://watchlists.test/api/hassio_ingress/test/'});
w.document.write(fs.readFileSync(path.join(staticDir,'index.html'),'utf8').replace('<body>','<body data-demo="true">').replace(/<script[^>]*>.*?<\/script>/gs,''));
w.fetch=async url=>{
  assert.equal(url,'static/demo-data.json');
  return{ok:true,json:async()=>structuredClone(seed)};
};
w.confirm=()=>true;
w.scrollTo=()=>{};
w.navigator.vibrate=()=>{};
w.addEventListener('error',e=>errors.push(e.message));
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
w.eval(fs.readFileSync(path.join(staticDir,'api.js'),'utf8'));
w.eval(fs.readFileSync(path.join(root,'preview/demo.js'),'utf8'));
w.eval(fs.readFileSync(path.join(staticDir,'app.js'),'utf8'));
await until(()=>w.WatchApp?.state.library.length>0);
assert.equal(w.document.querySelector('#demo-banner').hidden,false);
assert.equal(w.WatchApp.state.profiles.length,2);
const firstLibrary=structuredClone(w.WatchApp.state.library);
const shared=firstLibrary.find(s=>seed[0].show.id===s.id);
assert.ok(shared.watched>0);
assert.ok(w.document.querySelectorAll('img[alt^="Cover:"]').length>=8);

// Changing one person's history cannot change the other person's history.
const p1Before=await w.WatchAPI('api/profiles/1/library');
const p2Before=await w.WatchAPI('api/profiles/2/library');
const target=shared.next_episode;
await w.WatchAPI(`api/profiles/1/library/${shared.id}/episodes`,{method:'PATCH',body:{episode_id:target.id,watched:true}});
assert.equal((await w.WatchAPI('api/profiles/1/library')).find(s=>s.id===shared.id).watched,shared.watched+1);
assert.deepEqual(await w.WatchAPI('api/profiles/2/library'),p2Before);
await w.WatchApp.start();

// Tap opens details and displays the actual episode checkboxes.
let btn=w.document.querySelector(`[data-show="${shared.id}"]`);
btn.click();
await until(()=>w.document.querySelector('#season'));
assert.ok(w.document.querySelectorAll('[data-episode]').length>0);
const check=w.document.querySelector('[data-episode]:not(:checked)');
check.checked=true;check.dispatchEvent(new w.Event('change',{bubbles:true}));
await wait(70);
assert.equal((await w.WatchAPI(`api/profiles/1/library/${shared.id}/episodes`)).find(e=>e.id===Number(check.dataset.episode)).watched,1);
await w.WatchApp.closeModal();

// Long hold opens one quick menu. The synthesized click must not replace it with details.
btn=w.document.querySelector(`[data-show="${shared.id}"]`);
btn.dispatchEvent(new w.PointerEvent('pointerdown',{button:0,clientX:30,clientY:30,pointerType:'touch'}));
await wait(590);
assert.ok(w.document.querySelector('#quick-details'));
btn.dispatchEvent(new w.PointerEvent('pointerup',{button:0,clientX:30,clientY:30}));btn.click();
assert.ok(w.document.querySelector('#quick-details'));
assert.equal(w.document.querySelector('#season'),null);
await w.WatchApp.closeModal();

// Scrolling/dragging and pointer cancellation both cancel hold.
for(const cancelType of ['pointermove','pointercancel']){
  btn=w.document.querySelector(`[data-show="${shared.id}"]`);
  btn.dispatchEvent(new w.PointerEvent('pointerdown',{button:0,clientX:30,clientY:30}));
  btn.dispatchEvent(new w.PointerEvent(cancelType,{clientX:30,clientY:65}));
  await wait(590);
  assert.equal(w.document.querySelector('#modal').open,false);
}

// The profile selector switches the visible data rather than just changing its name.
w.document.querySelector('[data-profile="2"]').click();
await until(()=>w.WatchApp.state.profile===2&&w.WatchApp.state.library.length===p2Before.length);
assert.deepEqual(w.WatchApp.state.library,p2Before);

// Search/add works in the preview. Connecting is explicitly unavailable, never fake-connected.
w.document.querySelector('#search-button').click();
w.document.querySelector('#search-query').value='Dark';
w.document.querySelector('#search-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>w.document.querySelector('[data-add]'));
w.document.querySelector('[data-add]').click();
await until(()=>!w.document.querySelector('#modal').open);
assert.ok(w.WatchApp.state.library.some(s=>s.name==='Dark'));
w.document.querySelector('[data-view="connections"]').click();
assert.equal(w.document.querySelectorAll('[data-connect]').length,4);
w.document.querySelector('[data-connect]').click();
await wait(30);
assert.match(w.document.querySelector('#toast').textContent,/nur im installierten Add-on/);
assert.equal(w.document.querySelector('#modal').open,false);

// Provider DOM extraction returns evidence only; unknown percentage remains unknown.
const py=fs.readFileSync(path.join(root,'watchlists/app/providers.py'),'utf8');
const extractor=py.match(/EXTRACT_JS = r"""([\s\S]*?)"""/)[1];
const fixture=new Window({url:'https://www.netflix.com/browse/my-list'});
fixture.document.body.innerHTML='<div class="retable"><article><a href="/title/123"><img alt="Testserie"></a><p>Staffel 2, Folge 3</p><progress max="100" value="96"></progress></article><article><a href="/title/124"><img alt="Ohne Fortschritt"></a></article></div><section class="recommendations"><a href="/title/999"><img alt="Fremde Empfehlung"></a></section>';
const extract=fixture.eval('('+extractor+')');
const extraction=extract({provider:'netflix',section:'history'});
assert.equal(extraction.recognized,true);
const observations=extraction.rows;
assert.equal(observations.length,2);
assert.equal(observations[0].completion,96);
assert.equal(observations[1].completion,null);
assert.ok(!observations.some(o=>o.title==='Fremde Empfehlung'));
fixture.document.body.innerHTML='<article><a href="/title/999"><img alt="Keine bestätigte Liste"></a></article>';
assert.equal(extract({provider:'netflix',section:'watchlist'}).recognized,false);
// New Netflix layouts can use generated classes without the old gallery containers.
fixture.document.body.innerHTML=`<nav><a href="/title/777">Navigation</a></nav><main><header><h1>Meine Liste</h1></header><div class="generated-grid"><div class="random-card"><a href="/watch/101"><img alt="Dr. House" src="https://occ-0-1.1.nflxso.net/house.jpg"></a><a href="/browse/my-list?jbv=100" aria-label="Mehr Infos">Mehr Infos</a></div><div class="random-card"><a href="/title/200"><img alt="Mein Film"></a></div></div><section><h2>Das könnte dir gefallen</h2><a href="/title/999"><img alt="Empfehlung ohne Spezialklasse"></a></section></main><footer><a href="/title/888">Fußzeile</a></footer>`;
let modern=extract({provider:'netflix',section:'watchlist'});
assert.equal(modern.recognized,true);
assert.equal(modern.diagnostics.galleries,0);
assert.equal(modern.diagnostics.my_list_headings,1);
assert.equal(modern.diagnostics.heading_scope,true);
assert.deepEqual(structuredClone(modern.rows.map(r=>[r.title,new URL(r.url).pathname])),[['Dr. House','/title/100'],['Mein Film','/title/200']]);
fixture.document.body.innerHTML='<main><h1>My List</h1><div role="list"><div role="listitem"><a href="/title/300"><img alt="Dritter Titel"></a></div></div></main>';
assert.equal(extract({provider:'netflix',section:'watchlist'}).rows[0].title,'Dritter Titel');
fixture.document.body.innerHTML='<main><h1>Meine Liste</h1><p>Deine Liste ist leer.</p></main>';
modern=extract({provider:'netflix',section:'watchlist'});
assert.equal(modern.recognized,true);assert.equal(modern.rows.length,0);
fixture.document.body.innerHTML='<main><h1>Für dich</h1><a href="/title/999"><img alt="Unbestätigt"></a></main>';
assert.equal(extract({provider:'netflix',section:'watchlist'}).recognized,false);
fixture.document.body.innerHTML='<main><h1>Meine Liste</h1><a href="/title/999"><img alt="Falsche Route"></a></main>';
fixture.happyDOM.setURL('https://www.netflix.com/browse');
assert.equal(extract({provider:'netflix',section:'watchlist'}).recognized,false);
fixture.happyDOM.setURL('https://www.netflix.com/browse/my-list');
const statusCode=py.match(/PAGE_STATUS_JS = r"""([\s\S]*?)"""/)[1];
const status=fixture.eval('('+statusCode+')');
fixture.document.body.textContent='Sicherheitsüberprüfung. Bestätigen Sie, dass Sie ein Mensch sind.';
assert.equal(status().blocked,true);
fixture.document.body.textContent='Meine Watchlist';assert.equal(status().blocked,false);

// Native titles appear without metadata. History and legacy imports do not inflate the default watchlist.
const originalAPI=w.WatchAPI;
const nativeMovie={id:-10,name:'Ein Prime-Film',native:true,media_type:'movie',summary:'Direkt importiert',providers:[{provider:'prime',on_watchlist:1,source:'import'}],source_position:{},movie_watched:false,total:0,watched:0,user_status:'watching'};
const nativeSeries={id:-11,name:'Dr. House',native:true,media_type:'series',summary:'Direkt importiert',providers:[{provider:'netflix',on_watchlist:1,source:'import'}],source_position:{season:2,episode:7,completion:45},total:0,watched:0,user_status:'watching'};
const historyOnly={...nativeSeries,id:-12,name:'Nur im Verlauf',providers:[{provider:'netflix',on_watchlist:0,source:'import'}]};
const legacy={...nativeSeries,id:9001,name:'Früherer Import',native:false,legacy_only:true,providers:[{provider:'netflix',on_watchlist:1,source:'legacy'}]};
const nativeLibrary=[nativeMovie,nativeSeries,historyOnly,legacy];
Object.assign(w.WatchApp.state,{library:nativeLibrary,view:'home',profile:1,provider:'all',status:'all',collection:'watchlist',query:''});
w.WatchAPI=async(path,opts={})=>{
  if(path==='api/profiles/1/library')return structuredClone(nativeLibrary);
  if(path==='api/profiles/1/pending')return [];
  if(path==='api/profiles/1/connections')return [];
  if(path==='api/profiles/1/library/-10/watched'){nativeMovie.movie_watched=opts.body.watched;return{ok:true};}
  if(path==='api/profiles/1/library/-11/position'){nativeSeries.source_position=opts.body;nativeSeries.position_manual=true;return{ok:true};}
  return originalAPI(path,opts);
};
w.WatchApp.render();
assert.equal(w.document.querySelectorAll('[data-show]').length,2);
assert.match(w.document.querySelector('[data-show="-11"]').textContent,/S2 · F7/);
assert.ok(!w.document.querySelector('[data-show="-12"]'));
assert.ok(!w.document.querySelector('[data-show="9001"]'));
w.document.querySelector('[data-show="-10"]').click();
assert.ok(w.document.querySelector('#movie-seen'));
const seen=w.document.querySelector('#movie-seen');seen.checked=true;seen.dispatchEvent(new w.Event('change',{bubbles:true}));
await until(()=>nativeMovie.movie_watched);
await wait(60);
await w.WatchApp.closeModal();
w.document.querySelector('[data-show="-11"]').click();
w.document.querySelector('#native-season').value='3';w.document.querySelector('#native-episode').value='8';
w.document.querySelector('#native-position').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
await until(()=>nativeSeries.source_position.episode===8);
await wait(60);
await w.WatchApp.closeModal();
// A large viewing history is not a bulk metadata to-do list. Watchlist enrichment is collapsed.
const historyPending=Array.from({length:490},(_,i)=>({id:1000+i,provider:'netflix',title:'Nur Verlauf '+i,section:'history',sections:['history'],native_show_id:-12,legacy:false}));
const listPending={id:9,provider:'netflix',title:'Dr. House',section:'watchlist',sections:['watchlist','history'],native_show_id:-11,legacy:false};
Object.assign(w.WatchApp.state,{pending:[...historyPending,listPending],view:'connections'});
w.WatchApp.render();
const metadata=w.document.querySelector('#watchlist-metadata');
assert.ok(metadata);assert.equal(metadata.open,false);
assert.match(metadata.querySelector('summary').textContent,/optional · 1 Titel/);
assert.equal(metadata.querySelectorAll('[data-resolve]').length,1);
assert.ok(!w.document.querySelector('#main').textContent.includes('Nur Verlauf 0'));
// Metadata remains available within a history title's own detail dialog.
Object.assign(w.WatchApp.state,{view:'home',collection:'history'});
w.WatchApp.render();
w.document.querySelector('[data-show="-12"]').click();
assert.ok(w.document.querySelector('#native-metadata'));
await w.WatchApp.closeModal();
Object.assign(w.WatchApp.state,{pending:historyPending,view:'connections'});
w.WatchApp.render();
assert.equal(w.document.querySelector('#watchlist-metadata'),null);
w.WatchAPI=originalAPI;

// CSS parses, mobile adaptations exist, and unsafe text is escaped.
const styles=fs.readFileSync(path.join(staticDir,'app.css'),'utf8');
const cssErrors=[];css.parse(styles,{onParseError:e=>cssErrors.push(e.message)});
assert.deepEqual(cssErrors,[]);
assert.match(styles,/max-width:600px/);
assert.match(styles,/prefers-reduced-motion/);
assert.equal(w.WatchApp.esc('<img onerror="bad">'),'&lt;img onerror=&quot;bad&quot;&gt;');
assert.deepEqual(errors,[]);
await w.happyDOM.close();await fixture.happyDOM.close();
console.log(JSON.stringify({passed:true,checks:['two profile separation','cover rendering','episode editing','tap','hold 550ms and click suppression','drag and cancel','catalog search and add','honest connection demo','scoped DOM extraction excludes recommendations','modern Netflix heading scope and duplicate card links','empty named list accepted','unknown roots and wrong route rejected','security check recognized','native titles without matching','watchlist/history/legacy separated','movie seen status','native episode position','490 history entries excluded from collapsed watchlist metadata','history metadata available per title','CSS parsing','escaping'],browserVisualQA:false},null,2));
