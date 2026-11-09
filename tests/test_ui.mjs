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
fixture.document.body.innerHTML='<article><a href="/title/123"><img alt="Testserie"></a><p>Staffel 2, Folge 3</p><progress max="100" value="96"></progress></article><article><a href="/title/124"><img alt="Ohne Fortschritt"></a></article><a href="https://evil.test/">Nicht importieren</a>';
const extract=fixture.eval('('+extractor+')');
const observations=extract({provider:'netflix',section:'history'});
assert.equal(observations.length,2);
assert.equal(observations[0].completion,96);
assert.equal(observations[1].completion,null);

// CSS parses, mobile adaptations exist, and unsafe text is escaped.
const styles=fs.readFileSync(path.join(staticDir,'app.css'),'utf8');
const cssErrors=[];css.parse(styles,{onParseError:e=>cssErrors.push(e.message)});
assert.deepEqual(cssErrors,[]);
assert.match(styles,/max-width:600px/);
assert.match(styles,/prefers-reduced-motion/);
assert.equal(w.WatchApp.esc('<img onerror="bad">'),'&lt;img onerror=&quot;bad&quot;&gt;');
assert.deepEqual(errors,[]);
await w.happyDOM.close();await fixture.happyDOM.close();
console.log(JSON.stringify({passed:true,checks:['two profile separation','cover rendering','episode editing','tap','hold 550ms and click suppression','drag and cancel','catalog search and add','honest connection demo','DOM evidence extraction','CSS parsing','escaping'],browserVisualQA:false},null,2));
