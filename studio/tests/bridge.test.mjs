/** Inspect actual bridge events in an owned iframe, without running an application. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {JSDOM} from 'jsdom';
const script=readFileSync(new URL('../web/preview-bridge.js',import.meta.url),'utf8');
function bridge(t){
  const dom=new JSDOM('<iframe></iframe>',{url:'http://127.0.0.1:3088',runScripts:'outside-only'});t.after(()=>dom.window.close());
  const parent=dom.window,window=parent.document.querySelector('iframe').contentWindow,events=[];
  parent.postMessage=(data)=>events.push(data);
  window.__STUDIO_BRIDGE__={channel:'fixture',parentOrigin:parent.origin};window.CSS={escape:value=>value};
  window.document.body.innerHTML='<button id="customer">客户详情</button><input id="input">';
  window.document.elementFromPoint=()=>window.document.querySelector('#customer');window.eval(script);
  const mode=value=>window.dispatchEvent(new window.MessageEvent('message',{source:parent,origin:parent.origin,data:{type:'studio-mode',channel:'fixture',mode:value,inspect:value!=='experience'}}));
  const pointer=(type,x,y)=>window.document.querySelector('#customer').dispatchEvent(new window.MouseEvent(type,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0}));
  return {window,events,mode,pointer};
}
test('experience clicks reach the application; region drags report coordinates without app clicks',t=>{
  const b=bridge(t);let clicks=0;b.window.document.querySelector('#customer').onclick=()=>clicks++;
  b.pointer('click',10,10);assert.equal(clicks,1);
  b.mode('region');b.pointer('pointerdown',100,100);b.pointer('pointermove',10,20);b.pointer('pointerup',10,20);b.pointer('click',10,20);
  assert.equal(clicks,1);const result=b.events.find(e=>e.type==='studio-select');
  assert.match(result.target,/客户详情/);assert.equal(result.selector,'#customer');
  assert.deepEqual(JSON.parse(result.region),{x:10,y:20,width:90,height:80,viewportWidth:1024,viewportHeight:768,scrollX:0,scrollY:0});
});
test('cancelled region emits no selection; iframe shortcut works outside editable fields',t=>{
  const b=bridge(t);b.mode('region');b.pointer('pointerdown',0,0);b.pointer('pointercancel',30,30);b.pointer('pointerup',30,30);
  assert.equal(b.events.filter(e=>e.type==='studio-select').length,0);
  const key=()=>new b.window.KeyboardEvent('keydown',{bubbles:true,altKey:true,shiftKey:true,code:'KeyA'});
  b.window.document.querySelector('input').dispatchEvent(key());assert.equal(b.events.filter(e=>e.type==='studio-shortcut').length,0);
  b.window.document.querySelector('button').dispatchEvent(key());assert.equal(b.events.filter(e=>e.type==='studio-shortcut').length,1);
});

test('region release cannot activate the underlying button after returning to experience',t=>{
  const b=bridge(t);let clicks=0;b.window.document.querySelector('#customer').onclick=()=>clicks++;
  b.mode('region');b.pointer('pointerdown',0,0);b.pointer('pointerup',50,50);b.mode('experience');b.pointer('click',50,50);
  assert.equal(clicks,0);b.pointer('pointerdown',10,10);b.pointer('pointerup',10,10);b.pointer('click',10,10);assert.equal(clicks,1);
});
