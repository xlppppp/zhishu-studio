/** Diagram outcomes retain source and reject executable markup. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {JSDOM} from 'jsdom';
async function documentView(t,source,render){
  const dom=new JSDOM('<main data-document></main>',{url:'http://127.0.0.1:3088',runScripts:'outside-only'});t.after(()=>dom.window.close());
  const {window}=dom;window.document.querySelector('main').textContent=source;
  for(const name of ['lib/purify.js','lib/marked.js','documents.js'])window.eval(readFileSync(new URL('../web/'+name,import.meta.url),'utf8'));
  const append=window.document.head.append.bind(window.document.head);
  window.document.head.append=element=>{append(element);window.mermaid={initialize(config){assert.equal(config.htmlLabels,false);assert.equal(config.securityLevel,'strict');},render};element.onload();};
  window.StudioDocuments.render();
  for(let n=0;n<30 && window.document.querySelector('figcaption')?.textContent==='正在绘制图表…';n++)await new Promise(resolve=>setImmediate(resolve));
  return window.document;
}
test('diagram success sanitizes SVG and retains editable source',async t=>{
  const doc=await documentView(t,'<pre class="mermaid">flowchart LR\n A --&gt; B</pre>',async()=>({svg:'<svg xmlns="http://www.w3.org/2000/svg"><text onload="alert(1)">A</text><script>alert(1)</script><foreignObject><div>bad</div></foreignObject></svg>'}));
  assert.ok(doc.querySelector('.diagram-drawing svg'));assert.equal(doc.querySelector('svg script,svg foreignObject,svg [onload]'),null);
  assert.match(doc.querySelector('details pre').textContent,/A --> B/);assert.equal(doc.querySelector('figcaption').textContent,'');
});
test('syntax failure shows source and a persistent actionable error',async t=>{
  const doc=await documentView(t,'```mermaid\nbad syntax\n```',async()=>{throw new Error('parse failed');});
  assert.match(doc.querySelector('figcaption').textContent,/修改语法/);assert.equal(doc.querySelector('details').open,true);assert.equal(doc.querySelector('details pre').textContent,'bad syntax\n');
});
test('diagram configuration cannot override the host renderer',async t=>{
  let called=false;const doc=await documentView(t,'```mermaid\n%%{init: {}}%%\nflowchart LR\n A-->B\n```',async()=>{called=true;return {svg:'<svg></svg>'};});
  assert.equal(called,false);assert.equal(doc.querySelector('details').open,true);
});
