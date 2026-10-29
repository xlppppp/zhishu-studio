/** DOM regressions for draft persistence, task intent, and preview ownership. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const script=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const id='a'.repeat(32);
const project={id,name:'DOM fixture',requirements:'synthetic requirement',images:[],plan:{prd:'PRD',frontend:'frontend',backend:'backend',database:'database'},versions:[{number:1,time:1,reason:'fixture',plan:{}}],feedback:[],approved:'approved',built_from:'approved',built_job:'b'.repeat(32),accepted:null,job:{status:'idle'},queue:[],jobHistory:[]};

async function settled(predicate){
  for(let i=0;i<30;i++){if(predicate())return;await new Promise(resolve=>setImmediate(resolve));}
  assert.ok(predicate(),'DOM operation did not settle');
}
async function page(t,options={}){
  const requests=[];
  const dom=new JSDOM(html,{url:`http://127.0.0.1:3088/#project/${id}`,runScripts:'outside-only'});
  t.after(()=>dom.window.close());
  const {window}=dom;
  for(const [key,value] of Object.entries(options.storage||{}))window.localStorage.setItem(key,value);
  window.HTMLElement.prototype.scrollIntoView=function(){};
  window.EventSource=class {constructor(){this.listeners={};window.lastEventSource=this;} addEventListener(name,listener){this.listeners[name]=listener;} close(){} emit(name,value){this.listeners[name]?.({data:JSON.stringify(value)});}};
  window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  window.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new window.Event('close'));};
  window.fetch=async(path,request)=>{
    let value;
    if(path==='/api/status')value={available:true,assistantProtocol:3,source:'fixture',...options.status};
    else if(path==='/api/projects'){if(request?.method==='POST'){requests.push(JSON.parse(request.body));value=options.createProject?await options.createProject(JSON.parse(request.body)):project;}else value=[project];}
    else if(path==='/api/import-requirements'){value=await options.importFile(JSON.parse(request.body));}
    else if(path.endsWith('/runtime')){const current=options.project||project;const available=current.previewAvailable??current.built_from;value=options.runtime||{status:available?'running':'stopped',url:'http://127.0.0.1:39999/?channel=fixture-channel',channel:'fixture-channel',preflight:{ready:Boolean(available),checks:[{name:'运行配置',ok:Boolean(available)}],detail:'缺少配置'}};if(request?.method==='POST'){requests.push({runtimeStart:true});value=options.runtimeResult||{...value,status:'running',url:'http://127.0.0.1:39999/?channel=fixture-channel',channel:'fixture-channel'};}}
    else if(path.endsWith('/conversations')){const body=JSON.parse(request.body);requests.push(body);const current=options.project||project;const conversations=current.conversations||[{id:'legacy',title:'以前的对话'}];value={...current,conversations:body.operation==='rename'?conversations.map(item=>item.id===body.id?{...item,title:body.title}:item):[...conversations,{id:body.id,title:'新对话'}]};}
    else if(path.endsWith('/steer')||path.endsWith('/cancel')){const body=JSON.parse(request.body);requests.push({operation:path.split('/').at(-1),...body});value=options.project||project;if(body.dismissMessage){value={...value,queue:(value.queue||[]).filter(job=>job.id!==body.jobId),chatHistory:(value.chatHistory||[]).filter(message=>message.id!==body.jobId&&message.id!==body.jobId+'-reply')};options.project=value;}}
    else if(path.endsWith('/jobs')){requests.push(JSON.parse(request.body));if(options.jobError)return {ok:false,json:async()=>({error:options.jobError})};value=project;}
    else value=options.project||project;
    return {ok:true,json:async()=>structuredClone(value)};
  };
  for(const name of ['lib/purify.js','lib/marked.js','documents.js'])window.eval(readFileSync(new URL('../web/'+name,import.meta.url),'utf8'));
  window.eval(script);
  await settled(()=>window.document.querySelector('#feedback'));
  const document=window.document;
  if(!options.assistantClosed)document.querySelector('[data-action="toggle-assistant"]').click();
  const click=selector=>{const element=[...document.querySelectorAll(selector)].find(el=>!el.closest('[hidden]'));assert.ok(element,selector);element.click();};
  const input=(selector,value)=>{const element=document.querySelector(selector);element.value=value;element.dispatchEvent(new window.Event('input',{bubbles:true}));};
  return {window,document,click,input,requests};
}

test('switching tabs preserves the mounted preview document',async t=>{
  const p=await page(t);
  p.click('[data-stage="develop"]');
  const frame=p.document.querySelector('#preview');
  const previewWindow=frame.contentWindow;
  p.click('[data-stage="versions"]');
  assert.equal(p.document.querySelector('#preview'),frame);
  p.click('[data-stage="develop"]');
  assert.equal(p.document.querySelector('#preview'),frame);
  assert.equal(frame.contentWindow,previewWindow);
});

test('assistant derives code scope from preview and keeps it on execution page',async t=>{
  const p=await page(t);p.click('[data-stage="develop"]');p.input('#feedback','Change the button only');
  p.click('[data-stage="execution"]');p.click('[data-action="feedback"]');
  await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].kind,'chat');assert.equal(p.requests[0].autoScope,'code');
});

test('feedback and section drafts restore in a fresh page',async t=>{
  const p=await page(t);
  p.input('#feedback','Restore this feedback');
  p.click('[data-edit="prd"]');
  p.input('#section-editor','Unsubmitted PRD');
  p.click('[data-close]');
  p.click('[data-stage="versions"]');
  const key='studio-draft:'+id;
  const restored=await page(t,{storage:{[key]:p.window.localStorage.getItem(key)}});
  assert.equal(restored.document.querySelector('#feedback').value,'Restore this feedback');
  assert.equal(restored.document.querySelector('#feedback-kind'),null);
  restored.click('[data-stage="plan"]');restored.click('[data-edit="prd"]');
  assert.equal(restored.document.querySelector('#section-editor').value,'Unsubmitted PRD');
});

test('unsupported preview is disabled and explains missing prerequisites',async t=>{
  const p=await page(t,{runtime:{status:'stopped',preflight:{ready:false,checks:[],detail:'缺少配置'}}});p.click('[data-stage="develop"]');
  assert.equal(p.document.querySelector('[data-action="runtime-start"]').disabled,true);
  assert.doesNotMatch(p.document.querySelector('#preview-chrome').textContent,/缺少配置/);
  p.click('[data-action="runtime-checks"]');assert.match(p.document.querySelector('#modal').textContent,/缺少配置/);
});

test('storage failures remain visible instead of claiming a saved draft',async t=>{
  const p=await page(t);
  p.window.Storage.prototype.setItem=function(){throw new p.window.DOMException('full','QuotaExceededError');};
  p.input('#feedback','Keep this text');
  assert.match(p.document.querySelector('#draft-status').textContent,/保存失败/);
  assert.equal(p.document.querySelector('#feedback').value,'Keep this text');
});

test('manual placeholder displays a persistent warning and disables approval',async t=>{
  const incomplete=structuredClone(project);
  incomplete.approved=null;incomplete.built_from=null;
  incomplete.plan.prd='产品需求 PRD\n\n待填写：请点击「编辑原文」完善这一部分。';
  const p=await page(t,{project:incomplete});
  assert.equal(p.document.querySelector('[data-action="approve"]').disabled,true);
  assert.match(p.document.querySelector('#review-warning').textContent,/产品需求 PRD/);
});

test('sidebar only contains the assistant and execution has its own tab',async t=>{
  const p=await page(t);const sidebar=p.document.querySelector('.workspace-grid > aside');
  assert.equal(sidebar.querySelectorAll('section.panel').length,1);assert.equal(sidebar.querySelector('#job-status'),null);
  assert.equal(p.document.querySelector('#feedback-kind'),null);
  const tabs=[...p.document.querySelectorAll('[data-stage]')].map(el=>el.dataset.stage);
  assert.ok(tabs.indexOf('execution')>tabs.indexOf('deliver'));
  p.click('[data-stage="execution"]');assert.ok(p.document.querySelector('#job-status'));
});

test('selecting a design section attaches plan context without opening a mode dialog',async t=>{
  const p=await page(t);p.click('[data-feedback="prd"]');
  assert.equal(p.document.querySelector('#modal').open,false);assert.match(p.document.querySelector('#target').value,/产品需求/);
  p.input('#feedback','解释这个需求');p.click('[data-action="feedback"]');
  await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].autoScope,'plan');assert.equal(p.requests[0].kind,'chat');
});

test('HTML and legacy Markdown render without model scripts or workbench actions',async t=>{
  const unsafe='<h2>客户权限</h2><table><tr><th>角色</th><td>销售</td></tr></table><script>window.injected=true</script><div onclick="alert(1)" data-action="build" style="position:fixed">正文</div><a href="javascript:alert(1)">危险链接</a><iframe src="https://example.com"></iframe>';
  const p=await page(t,{project:{...project,plan:{...project.plan,prd:unsafe,frontend:'## 页面列表\n\n- 客户页\n- 跟进页'}}});
  const doc=p.document.querySelector('[data-document]');
  assert.equal(doc.querySelector('h2').textContent,'客户权限');assert.ok(doc.querySelector('table'));
  assert.equal(doc.querySelector('script,iframe,[onclick],[style],[data-action]'),null);
  assert.equal(doc.querySelector('a').hasAttribute('href'),false);
  assert.ok(p.document.querySelectorAll('[data-document]')[1].querySelector('ul'));
  p.click('[data-feedback="prd"]');assert.match(p.document.querySelector('#target').value,/产品需求/);
});

test('fullscreen fallback retains the iframe and places feedback in the fullscreen container',async t=>{
  const p=await page(t);p.click('[data-stage="develop"]');const frame=p.document.querySelector('#preview');
  p.click('[data-action="fullscreen"]');const pane=p.document.querySelector('#preview-pane');
  assert.ok(pane.classList.contains('preview-expanded'));assert.equal(p.document.querySelector('#preview-chrome').hidden,true);assert.equal(p.document.querySelector('#fullscreen-controls').hidden,false);assert.equal(p.document.querySelector('#preview'),frame);
  assert.equal(p.document.querySelector('#modal').parentElement,pane);assert.equal(p.document.querySelector('#toast').parentElement,pane);
  p.click('[data-action="region"]');
  p.window.dispatchEvent(new p.window.MessageEvent('message',{source:frame.contentWindow,origin:'http://127.0.0.1:39999',data:{type:'studio-select',channel:new URL(frame.src).searchParams.get('channel'),target:'框选区域：客户',path:'/customers',region:'{"x":10,"y":20,"width":50,"height":60}'}}));
  await settled(()=>p.document.querySelector('#target').value.includes('框选区域') && p.document.querySelector('#modal').parentElement===p.document.body);
  assert.equal(p.document.querySelector('#modal').open,false);
  p.input('#feedback','这是什么问题？');p.click('[data-action="feedback"]');await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].kind,'chat');assert.match(p.requests[0].target,/width/);
  assert.equal(p.document.querySelector('#modal').parentElement,p.document.body);
  assert.equal(p.document.querySelector('#preview'),frame);assert.equal(p.document.body.classList.contains('preview-open'),false);assert.equal(p.document.querySelector('#preview-chrome').hidden,false);assert.equal(p.document.querySelector('#fullscreen-controls').hidden,true);
});

test('native fullscreen exit clears expanded state without reloading the preview',async t=>{
  const p=await page(t);p.click('[data-stage="develop"]');const pane=p.document.querySelector('#preview-pane'),frame=p.document.querySelector('#preview');
  let full=null;Object.defineProperty(p.document,'fullscreenElement',{get:()=>full});
  pane.requestFullscreen=async()=>{full=pane;p.document.dispatchEvent(new p.window.Event('fullscreenchange'));};
  p.document.exitFullscreen=async()=>{full=null;p.document.dispatchEvent(new p.window.Event('fullscreenchange'));};
  p.click('[data-action="fullscreen"]');await settled(()=>full===pane);
  await p.document.exitFullscreen();assert.equal(pane.classList.contains('preview-expanded'),false);assert.equal(p.document.querySelector('#preview'),frame);
});

test('region shortcut ignores editable fields and forged selection messages',async t=>{
  const p=await page(t);p.click('[data-stage="develop"]');const region=p.document.querySelector('[data-action="region"]');
  p.document.querySelector('#feedback').dispatchEvent(new p.window.KeyboardEvent('keydown',{bubbles:true,altKey:true,shiftKey:true,code:'KeyA'}));
  assert.equal(region.getAttribute('aria-pressed'),'false');
  p.window.dispatchEvent(new p.window.KeyboardEvent('keydown',{altKey:true,shiftKey:true,code:'KeyA'}));
  assert.equal(region.getAttribute('aria-pressed'),'true');
  p.window.dispatchEvent(new p.window.MessageEvent('message',{origin:'https://evil.example',data:{type:'studio-select',target:'forged'}}));
  assert.equal(p.document.querySelector('#modal').open,false);
  p.window.dispatchEvent(new p.window.KeyboardEvent('keydown',{key:'Escape'}));assert.equal(region.getAttribute('aria-pressed'),'false');
});


test('uploaded documents stay as attachments and never replace supplemental input',async t=>{
  const attachment={id:'d'.repeat(32),name:'需求.docx',size:100,expiresAt:Date.now()/1000+1000,imageCount:2,warnings:['正文与图片已保留']};
  const p=await page(t,{importFile:async body=>{if(body.name==='bad.docx')throw new Error('Word 文档损坏');return attachment;}});
  p.click('[data-action="home"]');await settled(()=>p.document.querySelector('#requirements'));p.input('#requirements','我的补充说明');
  const upload=async(name)=>{
    const input=p.document.querySelector('#requirements-file');Object.defineProperty(input,'files',{configurable:true,value:[new p.window.File(['fixture'],name)]});input.dispatchEvent(new p.window.Event('change',{bubbles:true}));
    await settled(()=>!input.disabled && !p.document.querySelector('#import-status').textContent.startsWith('正在暂存'));
  };
  await upload('需求.docx');assert.equal(p.document.querySelector('#requirements').value,'我的补充说明');assert.match(p.document.querySelector('#requirement-uploads').textContent,/2 张嵌入图片/);
  await upload('bad.docx');assert.equal(p.document.querySelector('#requirements').value,'我的补充说明');assert.equal(p.document.querySelectorAll('[data-remove-document]').length,1);
  p.click('[data-action="create"]');p.input('#project-name','文档项目');p.click('#create-project');await settled(()=>p.requests.length===1);
  assert.equal(p.requests[0].requirements,'我的补充说明');assert.deepEqual(p.requests[0].documents,['d'.repeat(32)]);assert.equal(p.requests[0].analyze,true);assert.match(p.requests[0].requestId,/^[a-f0-9]{32}$/);
});

test('staged attachment references restore after refresh and allow document-only intake',async t=>{
  const stored=JSON.stringify({draft:'',documents:[{id:'e'.repeat(32),name:'图文需求.docx',size:50,imageCount:1,expiresAt:Date.now()/1000+1000,warnings:[]}]});
  const p=await page(t,{storage:{'studio-intake':stored}});p.click('[data-action="home"]');await settled(()=>p.document.querySelector('#requirements'));
  assert.match(p.document.querySelector('#requirement-uploads').textContent,/图文需求.docx/);p.click('[data-action="create"]');assert.equal(p.document.querySelector('#modal').open,true);
});

test('preview keeps only shortcut help above the application and excludes task summaries',async t=>{
  const p=await page(t,{project:{...project,job:{status:'completed',message:'LONG_AGENT_IMPLEMENTATION_SUMMARY'}}});
  p.click('[data-stage="develop"]');
  const chrome=p.document.querySelector('#preview-chrome');
  assert.equal(p.document.querySelector('#preview-task-status'),null);
  assert.doesNotMatch(chrome.textContent,/LONG_AGENT_IMPLEMENTATION_SUMMARY|运行准备检查|静态演示不连接后端/);
  assert.match(p.document.querySelector('#preview-help').textContent,/快捷键.*Alt.*Shift.*A/);
  p.click('[data-stage="execution"]');
  assert.match(p.document.querySelector('#job-status').textContent,/LONG_AGENT_IMPLEMENTATION_SUMMARY/);
});

test('workflow model, round, findings and validation evidence are visible without executing report markup',async t=>{
  const job={id:'c'.repeat(32),status:'running',workflowStage:'review',activeModel:'gpt-6.1-sol',reviewRound:2,models:{analysis:'gpt-6.1-sol',development:'claude-sonnet-5-5',review:'gpt-6.1-sol',maxReviewRounds:3},workflowHistory:[{stage:'development',model:'claude-sonnet-5-5',round:0,status:'completed'},{stage:'review',model:'gpt-6.1-sol',round:2,status:'running'}],reviews:[{round:1,model:'gpt-6.1-sol',verdict:'changes_requested',summary:'发现权限问题',findings:[{severity:'high',file:'api.js',line:5,trigger:'跨用户访问',evidence:'<script>bad()</script>',suggestion:'校验归属'}],checks:[{command:'npm test',status:'failed',result:'fixture failure'}]}]};
  const p=await page(t,{project:{...project,job}});
  p.click('[data-stage="execution"]');
  assert.match(p.document.querySelector('#job-status').textContent,/代码审查.*gpt-6.1-sol.*第 2 轮/);
  p.click('[data-review-job]');const dialog=p.document.querySelector('#modal');
  assert.match(dialog.textContent,/api.js:5/);assert.match(dialog.textContent,/校验归属/);assert.match(dialog.textContent,/npm test/);assert.equal(dialog.querySelector('script'),null);
});


test('model retry wait shows its finite budget, countdown and cancel control',async t=>{
  const fixture=structuredClone(project);
  fixture.job={status:'running',message:'等待自动重试',modelRetry:{attempt:1,maximum:3,nextAt:Date.now()/1000+120}};
  const p=await page(t,{project:fixture});
  p.click('[data-stage="execution"]');
  assert.match(p.document.querySelector('#job-status').textContent,/自动重试 1\/3/);
  assert.ok(Number(p.document.querySelector('[data-retry-at]').textContent)>0);
  assert.ok(p.document.querySelector('[data-action="cancel"]'));
});


test('review-pending builds retain preview, block delivery, and continue with prior report',async t=>{
  const fixture=structuredClone(project);
  fixture.job={id:'b'.repeat(32),status:'completed',reviews:[{verdict:'changes_requested'}]};
  fixture.reviewState={status:'blocked',sourceJob:fixture.job.id};
  const p=await page(t,{project:fixture});
  p.click('[data-stage="execution"]');
  assert.match(p.document.querySelector('#job-status').textContent,/修改验证未通过/);
  assert.doesNotMatch(p.document.querySelector('#job-status').textContent,/代码已保留/);
  p.click('[data-stage="develop"]');assert.ok(p.document.querySelector('#preview'));
  assert.match(p.document.querySelector('#preview-review-notice').textContent,/代码已保留/);
  p.click('[data-stage="deliver"]');await settled(()=>p.document.querySelector('[data-action="accept"]'));assert.equal(p.document.querySelector('[data-action="accept"]').disabled,true);
  p.click('[data-stage="execution"]');p.click('[data-action="continue-review"]');await settled(()=>p.document.querySelector('#toast').textContent.includes('已加入定向修复任务'));
  assert.equal(p.requests[0].reviewJobId,fixture.job.id);
  assert.equal(p.requests[0].kind,'iterate');assert.equal(p.requests[0].route,'business');
});

for (const scenario of [
  {name:'analysis without generated code',built_from:null,status:'pending'},
  {name:'approved review',built_from:'approved',status:'passed'},
]) {
  test(`preview review notice stays hidden for ${scenario.name}`,async t=>{
    const fixture=structuredClone(project);
    fixture.built_from=scenario.built_from;
    fixture.reviewState={status:scenario.status};
    const p=await page(t,{project:fixture});
    p.click('[data-stage="execution"]');
    assert.doesNotMatch(p.document.querySelector('#job-status').textContent,/代码已保留/);
    p.click('[data-stage="develop"]');
    assert.equal(p.document.querySelector('#preview-review-notice'),null);
  });
}

for(const mode of ['continue','restart']){
  test(`existing development opens a choice and submits ${mode} explicitly`,async t=>{
    const fixture=structuredClone(project);fixture.hasWorkspaceProgress=true;fixture.previewAvailable=true;
    fixture.built_from=null;fixture.job={status:'cancelled',kind:'build'};
    const p=await page(t,{project:fixture});p.click('[data-stage="develop"]');
    assert.ok(p.document.querySelector('#preview'));
    p.click('[data-action="build"]');
    assert.equal(p.requests.length,0);
    assert.equal(p.document.querySelector('input[name="build-mode"]:checked').value,'continue');
    p.document.querySelector(`input[value="${mode}"]`).checked=true;
    p.click('#confirm-build');await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
    assert.equal(p.requests[0].kind,'build');assert.equal(p.requests[0].buildMode,mode);
  });
}

test('closing the development choice does not submit a model task',async t=>{
  const fixture=structuredClone(project);fixture.hasWorkspaceProgress=true;
  const p=await page(t,{project:fixture});p.click('[data-stage="develop"]');p.click('[data-action="build"]');
  p.click('#modal [data-close]');assert.equal(p.requests.length,0);assert.ok(p.document.querySelector('#preview'));
});

test('connection settings show stage groups, high reasoning, and separate key names',async t=>{
  const p=await page(t,{status:{modelRouting:{analysis:'gpt-6.1-sol',development:'gpt-6.1-sol',review:'gpt-6.1-sol',maxReviewRounds:2,reasoning:'high',stageProviders:{analysis:'gpt-ge-default',development:'gpt-ge-codex',review:'gpt-ge-codex'}}}});
  p.click('[data-action="settings"]');const text=p.document.querySelector('#modal').textContent;
  assert.match(text,/需求分析：gpt-6.1-sol · default/);
  assert.match(text,/开发与修复：gpt-6.1-sol · codex/);
  assert.match(text,/审查：gpt-6.1-sol · codex · 推理 high/);
  assert.match(text,/GPT_GE_DEFAULT_API_KEY/);assert.match(text,/GPT_GE_CODEX_API_KEY/);
});


test('project questions default to chat and retain model selection across navigation',async t=>{
  const p=await page(t,{status:{modelRouting:{analysis:'gpt-6.1-sol',development:'gpt-6.1-sol',review:'gpt-6.1-sol',fallback:{to:'gpt-6-sol'}}}});
  assert.equal(p.document.querySelector('#feedback-kind'),null);
  const model=p.document.querySelector('#chat-model');model.value='gpt-6-sol';model.dispatchEvent(new p.window.Event('change',{bubbles:true}));
  p.input('#feedback','为什么页面报错？');p.click('[data-stage="develop"]');
  assert.equal(p.document.querySelector('#chat-model').value,'gpt-6-sol');
  p.click('[data-action="feedback"]');await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].kind,'chat');assert.equal(p.requests[0].model,'gpt-6-sol');assert.equal(p.requests[0].chatMessage,true);
});

test('chat history escapes model output and preserves failed answers',async t=>{
  const p=await page(t,{project:{...project,chatHistory:[{role:'user',text:'说明问题',kind:'chat',target:'按钮'},{role:'assistant',text:'<script>danger()</script>',status:'failed',model:'gpt-6-sol'}]}});
  const history=p.document.querySelector('#chat-history');
  assert.equal(history.querySelector('script'),null);assert.match(history.textContent,/<script>/);assert.match(history.textContent,/本次未完成/);
});

test('unsupported voice input keeps the message and exposes an actionable explanation',async t=>{
  const p=await page(t);p.input('#feedback','保留草稿');p.click('[data-action="voice"]');
  assert.equal(p.document.querySelector('#feedback').value,'保留草稿');assert.match(p.document.querySelector('#chat-error').textContent,/不支持语音输入/);assert.equal(p.requests.length,0);
});

test('voice transcription remains editable and never auto-submits',async t=>{
  const p=await page(t);let recognition;
  p.window.SpeechRecognition=class {constructor(){recognition=this;}start(){}abort(){}};
  p.input('#feedback','已有文字');p.click('[data-action="voice"]');
  recognition.onresult({results:[[{transcript:'补充语音'}]]});recognition.onend();
  assert.equal(p.document.querySelector('#feedback').value,'已有文字\n补充语音');assert.equal(p.requests.length,0);
  p.click('[data-action="voice"]');recognition.onerror({error:'not-allowed'});recognition.onend();
  assert.match(p.document.querySelector('#chat-error').textContent,/权限被拒绝/);
});


test('chat submission failure retains the draft and shows the restart instruction in place',async t=>{
  const p=await page(t,{jobError:'当前 Worker 尚未启用项目聊天，请重启'});
  p.input('#feedback','说明当前错误');p.click('[data-action="feedback"]');
  await settled(()=>p.document.querySelector('#chat-error').textContent.includes('重启'));
  assert.equal(p.document.querySelector('#feedback').value,'说明当前错误');
});


test('history switches conversations and new conversation starts without previous messages',async t=>{
  const p=await page(t,{project:{...project,conversations:[{id:'legacy',title:'以前的对话'},{id:'d'.repeat(32),title:'地形问题'}],chatHistory:[{conversationId:'legacy',role:'assistant',text:'旧对话回答',status:'completed'},{conversationId:'d'.repeat(32),role:'assistant',text:'地形对话回答',status:'completed'}]}});
  assert.match(p.document.querySelector('#chat-history').textContent,/旧对话回答/);
  p.click('[data-action="chat-history"]');p.click('[data-conversation="'+ 'd'.repeat(32)+'"]');
  assert.match(p.document.querySelector('#chat-history').textContent,/地形对话回答/);assert.doesNotMatch(p.document.querySelector('#chat-history').textContent,/旧对话回答/);
  p.click('[data-action="new-chat"]');await settled(()=>p.document.querySelector('#chat-history').hidden && p.requests.length===1);
  assert.equal(p.document.querySelector('#feedback').value,'');assert.match(p.requests[0].id,/^[a-f0-9]{32}$/);
});


test('development automatically starts runtime once and omits static and stop buttons',async t=>{
  const p=await page(t,{runtime:{status:'stopped',preflight:{ready:true}}});
  p.click('[data-stage="develop"]');await settled(()=>p.requests.some(item=>item.runtimeStart)&&p.document.querySelector('#preview'));
  assert.equal(p.document.querySelector('[data-action="static-preview"]'),null);
  assert.equal(p.document.querySelector('[data-action="runtime-stop"]'),null);
  assert.equal(p.requests.filter(item=>item.runtimeStart).length,1);
  p.click('[data-stage="execution"]');p.click('[data-stage="develop"]');
  assert.equal(p.requests.filter(item=>item.runtimeStart).length,1);
});

test('runtime startup failure remains visible without displaying static preview',async t=>{
  const p=await page(t,{runtime:{status:'stopped',preflight:{ready:true}},runtimeResult:{status:'failed',message:'后端启动失败'}});
  p.click('[data-stage="develop"]');await settled(()=>p.document.querySelector('#preview-screen').textContent.includes('后端启动失败'));
  assert.equal(p.document.querySelector('#preview'),null);
  assert.equal(p.requests.filter(item=>item.runtimeStart).length,1);
});


test('triangle opens the directory and renaming updates the current title without losing messages',async t=>{
  const p=await page(t,{project:{...project,conversations:[{id:'legacy',title:'以前的对话'}],chatHistory:[{conversationId:'legacy',role:'assistant',text:'保留的回答',status:'completed'}]}});
  const toggle=p.document.querySelector('[data-action="chat-history"]');
  assert.equal(toggle.textContent,'▾');assert.equal(toggle.getAttribute('aria-expanded'),'false');
  assert.equal(p.document.querySelector('#conversation-title').textContent,'以前的对话');
  p.click('[data-action="chat-history"]');assert.equal(p.document.querySelector('#conversation-directory').hidden,false);
  p.click('[data-rename-conversation="legacy"]');p.input('#conversation-name','矿山问题排查');p.click('#save-conversation-name');
  await settled(()=>p.document.querySelector('#conversation-title').textContent==='矿山问题排查');
  assert.match(p.document.querySelector('#chat-history').textContent,/保留的回答/);
  assert.equal(p.requests[0].operation,'rename');assert.equal(p.requests[0].baseTitle,'以前的对话');
  p.click('[data-action="chat-history"]');p.document.body.click();assert.equal(p.document.querySelector('#conversation-directory').hidden,true);
});

test('old HTTP service rejects chat locally without replacing the running preview',async t=>{
  const p=await page(t,{status:{assistantProtocol:undefined}});
  p.click('[data-stage="develop"]');
  const frame=p.document.querySelector('#preview');
  p.input('#feedback','请问为什么校验失败');p.click('[data-action="feedback"]');
  await settled(()=>/后台版本不一致/.test(p.document.querySelector('#chat-error').textContent));
  assert.equal(p.requests.length,0);
  assert.equal(p.document.querySelector('#preview'),frame);
  assert.equal(p.document.querySelector('#feedback').value,'请问为什么校验失败');
});

test('question submission preserves the iframe and its current interaction state',async t=>{
  const p=await page(t);p.click('[data-stage="develop"]');
  const frame=p.document.querySelector('#preview');
  p.input('#feedback','解释这个错误，不要修改');p.click('[data-action="feedback"]');
  await settled(()=>p.requests.length===1 && p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].kind,'chat');assert.equal(p.document.querySelector('#preview'),frame);
});


test('ready replacement URL refreshes preview even when lifecycle stays running',async t=>{
  const p=await page(t,{project:{...project,previewRevision:'new'},runtime:{status:'running',url:'http://127.0.0.1:39999/',revision:'old',targetRevision:'new',replacementStatus:'starting',preflight:{ready:true}}});p.click('[data-stage="develop"]');
  const original=p.document.querySelector('#preview');
  p.window.lastEventSource.emit('preview',{status:'running',url:original.src,message:'background update',targetRevision:'new',replacementStatus:'starting'});
  assert.equal(p.document.querySelector('#preview'),original);
  p.window.lastEventSource.emit('preview',{status:'running',url:'http://127.0.0.1:39998/',message:'ready',revision:'new',targetRevision:'new',replacementStatus:null});
  assert.notEqual(p.document.querySelector('#preview'),original);
  assert.equal(p.document.querySelector('#preview').src,'http://127.0.0.1:39998/');
});

test('composer hides redundant headings and removes individual attachments without affecting preview',async t=>{
  const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB';
  const storage={['studio-draft:'+id]:JSON.stringify({conversationId:'legacy',conversationDrafts:{legacy:{note:'分析这些内容',target:'选区一；选区二',contexts:['选区一','选区二'],images:[{name:'one.png',data:image},{name:'two.png',data:image}]}}})};
  const p=await page(t,{storage});p.click('[data-stage="develop"]');
  const frame=p.document.querySelector('#preview');
  assert.equal(p.document.querySelector('#conversation-title').hidden,true);
  assert.equal(p.document.querySelector('.chat-scope'),null);
  assert.equal(p.document.querySelectorAll('.composer-attachment').length,4);
  p.click('[data-remove-chat-image="0"]');p.click('[data-remove-chat-context="0"]');
  assert.equal(p.document.querySelectorAll('.composer-attachment').length,2);
  assert.match(p.document.querySelector('.image-attachment').textContent,/two.png/);
  assert.equal(p.document.querySelector('#target').value,'选区二');
  assert.equal(p.document.querySelector('#feedback').value,'分析这些内容');
  assert.equal(p.document.querySelector('#preview'),frame);
});

test('composer sends selected images and contexts and clears them only after acknowledgement',async t=>{
  const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB';
  const storage={['studio-draft:'+id]:JSON.stringify({conversationId:'legacy',conversationDrafts:{legacy:{note:'分析图片',target:'选区',contexts:['选区'],images:[{name:'one.png',data:image}]}}})};
  const p=await page(t,{storage,status:{chatImageAttachments:1}});
  p.click('[data-action="feedback"]');await settled(()=>p.requests.length===1&&p.document.querySelector('#feedback').value==='');
  assert.equal(p.requests[0].images[0].data,image);assert.deepEqual(p.requests[0].contexts,['选区']);
  assert.equal(p.document.querySelectorAll('.composer-attachment').length,0);
});

test('model popup selects additional models and five reasoning levels without reloading preview',async t=>{
  const p=await page(t,{status:{reasoningSelection:1,modelRouting:{analysis:'gpt-6.1-sol',development:'gpt-6.1-sol',review:'gpt-6.1-sol',assistantModels:['gpt-6.1-sol','gpt-6-sol','gpt-6-astra','claude-sonnet-5-5']}}});
  p.click('[data-stage="develop"]');const frame=p.document.querySelector('#preview');
  p.click('[data-action="model-settings"]');
  assert.equal(p.document.querySelector('#chat-reasoning').value,'2');
  p.input('#chat-reasoning','4');assert.equal(p.document.querySelector('#chat-reasoning').getAttribute('aria-valuetext'),'max');
  p.click('[data-action="model-list"]');p.click('[data-select-chat-model="claude-sonnet-5-5"]');
  assert.match(p.document.querySelector('[data-action="model-settings"]').textContent,/Claude Sonnet 5.5.*max/);
  assert.equal(p.document.querySelector('#preview'),frame);
  p.input('#feedback','解释当前问题');p.click('[data-action="feedback"]');
  await settled(()=>p.requests.length===1);
  assert.equal(p.requests[0].model,'claude-sonnet-5-5');assert.equal(p.requests[0].reasoning,'max');
  assert.equal(JSON.parse(p.window.localStorage.getItem('studio-draft:'+id)).reasoning,'max');
});

test('model popup dismisses outside and preserves the selected reasoning setting',async t=>{
  const p=await page(t);
  p.click('[data-action="model-settings"]');p.input('#chat-reasoning','0');p.document.body.click();
  assert.equal(p.document.querySelector('#model-picker').hidden,true);
  p.click('[data-action="model-settings"]');assert.equal(p.document.querySelector('#chat-reasoning').value,'0');
});

function fileDrop(window,target,files,items=[]){
  const event=new window.Event('drop',{bubbles:true,cancelable:true});
  Object.defineProperty(event,'dataTransfer',{value:{types:['Files'],files,items}});
  target.dispatchEvent(event);return event;
}

test('dropping a photo and a file creates removable cards and sends original attachments',async t=>{
  const p=await page(t,{status:{chatFiles:1,chatImageAttachments:1}});
  p.click('[data-stage="develop"]');const frame=p.document.querySelector('#preview');
  const image=new p.window.File(['photo'],'photo.png',{type:'image/png'});
  const file=new p.window.File(['specific error text'],'errors.log',{type:'text/plain'});
  p.input('#feedback','解释附件');
  const event=fileDrop(p.window,p.document.querySelector('#feedback'),[image,file]);
  assert.equal(event.defaultPrevented,true);
  await settled(()=>p.document.querySelectorAll('.composer-attachment').length===2);
  assert.match(p.document.querySelector('.file-attachment').textContent,/errors.log/);
  assert.equal(p.document.querySelector('#preview'),frame);
  p.click('[data-remove-chat-image="0"]');
  assert.equal(p.document.querySelectorAll('.composer-attachment').length,1);
  p.click('[data-action="feedback"]');await settled(()=>p.requests.length===1&&p.document.querySelectorAll('.composer-attachment').length===0);
  assert.equal(p.requests[0].files[0].name,'errors.log');
  assert.equal(Buffer.from(p.requests[0].files[0].data,'base64').toString(),'specific error text');
  assert.equal(p.document.querySelector('#preview'),frame);
});

test('oversized drop and folder drop preserve the draft and existing attachments',async t=>{
  const p=await page(t);p.input('#feedback','保留文字');
  const file=new p.window.File(['large'],'model.glb');Object.defineProperty(file,'size',{value:65*1024*1024});
  fileDrop(p.window,p.document.querySelector('#feedback'),[file]);
  await settled(()=>/64 MiB/.test(p.document.querySelector('#chat-error').textContent));
  assert.equal(p.document.querySelector('#feedback').value,'保留文字');assert.equal(p.requests.length,0);
  fileDrop(p.window,p.document.querySelector('#feedback'),[],[{webkitGetAsEntry:()=>({isDirectory:true})}]);
  await settled(()=>/不支持文件夹/.test(p.document.querySelector('#chat-error').textContent));
  assert.equal(p.document.querySelector('#feedback').value,'保留文字');
});

test('assistant interruption and queued steering preserve the mounted preview',async t=>{
  const active={id:'c'.repeat(32),kind:'chat',status:'running',conversationId:'legacy',chatMessage:{text:'Original goal'}};
  const queued={id:'d'.repeat(32),kind:'chat',status:'queued',conversationId:'legacy',chatMessage:{text:'New direction'}};
  const current={...project,job:active,queue:[active,queued],chatHistory:[{id:queued.id,role:'user',conversationId:'legacy',text:'New direction',kind:'chat'}]};
  const p=await page(t,{project:current,status:{assistantSteering:1}});p.click('[data-stage="develop"]');
  const frame=p.document.querySelector('#preview');
  assert.equal(p.document.querySelector('.chat-compose').firstElementChild.className,'steering-queue');
  assert.equal(p.document.querySelectorAll('.steering-row').length,1);
  assert.equal(p.document.querySelector('.steering-text').textContent,'New direction');
  assert.equal(p.document.querySelectorAll('#chat-history .chat-user').length,0);
  p.click('[data-steer-message]');await settled(()=>p.document.querySelector('#toast').textContent.includes('引导已保存'));
  assert.deepEqual(p.requests.find(item=>item.operation==='steer'),{operation:'steer',jobId:active.id,messageId:queued.id});
  assert.equal(p.document.querySelector('#preview'),frame);
  p.input('#feedback','Unsent draft');p.click('[data-action="interrupt-assistant"]');
  await settled(()=>p.document.querySelector('#toast').textContent.includes('正在中断当前任务'));
  assert.equal(p.requests.find(item=>item.operation==='cancel').jobId,active.id);
  assert.equal(p.document.querySelector('#feedback').value,'Unsent draft');
  assert.equal(p.document.querySelector('#preview'),frame);
});

test('another conversation cannot interrupt or steer the active assistant',async t=>{
  const p=await page(t,{project:{...project,queue:[{id:'c'.repeat(32),kind:'chat',status:'running',conversationId:'other',chatMessage:{text:'Elsewhere'}}]}});
  assert.equal(p.document.querySelector('[data-action="interrupt-assistant"]'),null);
  assert.equal(p.document.querySelector('[data-steer-message]'),null);
});

test('all-files picker submits GLB, PDF, archives and extensionless binaries unchanged',async t=>{
  const p=await page(t,{status:{chatFiles:1}});
  const picker=p.document.querySelector('#chat-attachment-input');
  assert.equal(picker.accept,'*/*');assert.equal(picker.multiple,true);
  const names=['terrain.glb','reference.pdf','assets.zip','binary'];
  const files=names.map(name=>new p.window.File([new Uint8Array([0,1,254,255])],name,{type:''}));
  Object.defineProperty(picker,'files',{value:files});
  picker.dispatchEvent(new p.window.Event('change',{bubbles:true}));
  await settled(()=>p.document.querySelectorAll('.file-attachment').length===4);
  p.input('#feedback','检查这些附件');p.click('[data-action="feedback"]');
  await settled(()=>p.requests.length===1&&p.document.querySelectorAll('.file-attachment').length===0);
  assert.deepEqual(p.requests[0].files.map(file=>file.name),names);
  for(const file of p.requests[0].files)assert.deepEqual([...Buffer.from(file.data,'base64')],[0,1,254,255]);
});

test('a photo larger than the thumbnail limit is accepted as an ordinary file',async t=>{
  const p=await page(t,{status:{chatFiles:1}});
  const file=new p.window.File(['photo-original'],'large.png',{type:'image/png'});
  Object.defineProperty(file,'size',{value:4*1024*1024});
  fileDrop(p.window,p.document.querySelector('#feedback'),[file]);
  await settled(()=>p.document.querySelectorAll('.file-attachment').length===1);
  assert.equal(p.document.querySelectorAll('.image-attachment').length,0);
  assert.equal(p.document.querySelector('#chat-error').textContent,'');
});

test('deleting a queued guidance row cancels only that message and preserves the draft',async t=>{
  const active={id:'c'.repeat(32),kind:'chat',status:'running',conversationId:'legacy',chatMessage:{text:'Original goal'}};
  const queued={id:'d'.repeat(32),kind:'chat',status:'queued',conversationId:'legacy',chatMessage:{text:'Only this message'}};
  const p=await page(t,{project:{...project,job:active,queue:[active,queued]}});
  p.click('[data-stage="develop"]');const frame=p.document.querySelector('#preview');
  p.input('#feedback','Keep the draft');p.click('.steering-remove');
  await settled(()=>p.requests.some(item=>item.operation==='cancel'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(p.requests.find(item=>item.operation==='cancel').jobId,queued.id);
  assert.equal(p.requests.find(item=>item.operation==='cancel').dismissMessage,true);
  assert.equal(p.document.querySelector('.steering-row'),null);
  assert.doesNotMatch(p.document.querySelector('#chat-history').textContent,/排队任务已取消|本次未完成/);
  assert.equal(p.document.querySelector('#feedback').value,'Keep the draft');
  assert.equal(p.document.querySelector('#preview'),frame);
});

test('a completed modification with blocked review visibly reports verification failure',async t=>{
  const p=await page(t,{project:{...project,job:{id:'c'.repeat(32),kind:'iterate',status:'completed'},reviewState:{status:'blocked'},chatHistory:[{id:'reply',role:'assistant',status:'completed',reviewStatus:'blocked',text:'Changes saved',conversationId:'legacy'}]}});
  assert.match(p.document.querySelector('#chat-history').textContent,/修改验证未通过，不能认定问题已解决/);
  p.click('[data-stage="execution"]');
  assert.match(p.document.querySelector('.status-label').textContent,/修改验证未通过/);
});
