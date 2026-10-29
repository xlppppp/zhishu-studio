/** Project workbench UI. Server records own project data and task outcomes. */
(() => {
  'use strict';
  const icons = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    sparkle: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="m20 2 1 2 2 1-2 1-1 2-1-2-2-1 2-1Z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5-8 11M3 16l4-4 4 4"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
    code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 4 18 4 18 0V5M3 12c0 4 18 4 18 0"/>',
    monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4m-4 0h8"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    box: '<path d="m12 2 9 5v10l-9 5-9-5V7Zm0 10L3 7m9 5 9-5m-9 5v10M7 4l10 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 3 2 3-2 3 1 2-3-1-3 2-2-2-3-3-1-1-3Z"/>',
    chat: '<path d="M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 0 1-1-4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3Z"/><path d="M7 7h10M7 11h7"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.file}</svg>`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const keys = ['prd', 'frontend', 'backend', 'database'];
  const titles = ['产品需求 PRD', '前端与交互设计', '后端与接口设计', '数据库设计'];
  const sectionIcons = ['file', 'monitor', 'code', 'database'];
  const examples = [
    {name:'客户关系管理系统',desc:'连接客户、销售与每一次商机',tags:['客户管理','销售漏斗','权限管理'],color:'',requirements:'为一家 30 人的企业搭建客户关系管理系统。包含客户档案、联系人、商机跟进、销售漏斗和数据报表。管理员可以分配客户，销售只能查看自己负责的客户。支持按部门统计业绩、搜索筛选及导出客户列表。界面简洁，适配桌面与手机。'},
    {name:'团队项目协作平台',desc:'让任务、进度与团队保持同步',tags:['任务看板','项目管理','团队协作'],color:'teal',requirements:'开发一个团队项目协作平台。支持创建项目、邀请成员、分配任务、看板拖拽、截止时间和评论。包含管理员与普通成员两种角色。首页展示项目进度与待办任务，支持按负责人、状态和日期筛选。'},
    {name:'电商运营管理后台',desc:'从商品到订单，管理日常运营',tags:['商品管理','订单流程','库存管理'],color:'peach',requirements:'为一家小型电商公司开发运营后台。包含商品与分类、库存、订单、发货与销售报表。库存变动需要可追踪，订单支持待付款、待发货、已发货和已完成状态。支持商品搜索、低库存提醒与订单导出。'},
  ];
  const state = {projects:[], project:null, status:null, stage:'plan', assistantOpen:false, conversationMenuOpen:false, uploads:[], draft:'', selected:'整个项目', note:'', stream:null, connection:'connecting', worker:null, submission:null, toast:null, previewMode:'experience', runtimeAttempt:'', previewKind:'runtime', previewChannel:crypto.randomUUID().replaceAll('-',''), runtime:null, feedbackKind:'chat', conversationId:'legacy', conversationDrafts:{}, chatImages:[], chatFiles:[], chatAttaching:false, contexts:[], assistantScope:'plan', chatModel:'', chatReasoning:'high', modelMenu:null, speech:null, speechText:'', speechError:'', chatError:'', taskRoute:'business', sections:{}, draftError:'', runtimeError:'', previewExpanded:false, importing:false, requirementUploads:[], creation:null, intakeError:''};
  const $ = (selector, root=document) => root.querySelector(selector);
  function saveIntake() {
    try{localStorage.setItem('studio-intake',JSON.stringify({draft:state.draft,documents:state.requirementUploads,creation:state.creation}));state.intakeError='';}
    catch(error){state.intakeError='附件已暂存，但浏览器草稿保存失败；请勿刷新页面，或重新上传附件。';}
  }
  function restoreIntake() {
    try{
      const saved=JSON.parse(localStorage.getItem('studio-intake')||'null');if(!saved)return;
      if(typeof saved.draft==='string' && saved.draft.length<=30000)state.draft=saved.draft;
      const documents=Array.isArray(saved.documents)?saved.documents:[];
      state.requirementUploads=documents.filter(item=>typeof item.id==='string' && /^[a-f0-9]{32}$/.test(item.id) && typeof item.name==='string' && item.name.length<=160 && Number.isFinite(item.expiresAt) && item.expiresAt>Date.now()/1000).slice(0,4);
      if(saved.creation && /^[a-f0-9]{32}$/.test(saved.creation.id) && typeof saved.creation.name==='string')state.creation=saved.creation;
      if(documents.length!==state.requirementUploads.length)state.intakeError='部分暂存附件已过期，请重新上传。';
    }catch(error){state.intakeError='无法恢复需求草稿，请重新选择附件。';}
  }
  function documentMarkup() {
    return state.requirementUploads.map(item=>`<div class="requirement-attachment"><div><strong>${escape(item.name)}</strong><p class="hint">已暂存 · ${Number(item.imageCount||0)} 张嵌入图片 · ${(Number(item.size||0)/1024/1024).toFixed(1)} MB</p>${(Array.isArray(item.warnings)?item.warnings:[]).map(value=>`<p class="hint">${escape(value)}</p>`).join('')}</div><a class="btn small" href="/api/requirement-uploads/${item.id}/original" download>原文件</a><button class="btn small" data-remove-document="${item.id}">移除</button></div>`).join('');
  }
  function readDraft(id) {
    try {
      const value=JSON.parse(localStorage.getItem('studio-draft:'+id)||'null');
      if(!value || typeof value!=='object')return null;
      return value;
    } catch(error) {state.draftError='无法读取本地草稿，请勿关闭尚未提交的文字。';return null;}
  }
  function saveDraft() {
    if(!state.project)return;
    state.conversationDrafts[state.conversationId]={note:state.note,target:state.selected,images:state.chatImages,files:state.chatFiles,contexts:state.contexts};
    try {
      localStorage.setItem('studio-draft:'+state.project.id,JSON.stringify({note:state.note,target:state.selected,conversationId:state.conversationId,conversationDrafts:state.conversationDrafts,assistantScope:state.assistantScope,kind:state.feedbackKind,model:state.chatModel,reasoning:state.chatReasoning,route:state.taskRoute,stage:state.stage,sections:state.sections}));
      state.draftError='';
    } catch(error) {state.draftError='本地草稿保存失败，请勿刷新；请复制文字备份，附件可能需要重新添加。';}
    const status=$('#draft-status');if(status)status.textContent=state.draftError||'文字草稿已保存在当前浏览器';
    if(state.draftError && $('#modal-error'))$('#modal-error').textContent=state.draftError;
  }
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '操作失败，请重试');
    return data;
  }
  function toast(message) {
    clearTimeout(state.toast); const el = $('#toast'); el.textContent = message; el.hidden = false;
    state.toast = setTimeout(() => {el.hidden = true;}, 6000);
  }
  function errorText(error) {return error instanceof Error ? error.message : '操作失败，请重试';}
  function projectUrl(action='') {return `/api/projects/${state.project.id}${action ? '/'+action : ''}`;}
  const busy = () => ['queued','running','cancelling'].includes(state.project?.job.status) || Boolean(state.project?.queue?.length);
  const disabled = condition => condition ? 'disabled' : '';
  function layout(content) {
    const ready = state.status?.available;
    const markup = `<div class="layout"><aside class="sidebar"><button class="brand" data-action="home"><span class="brandmark">h</span><div>Harness<span>STUDIO</span></div></button><nav class="nav-group"><div class="nav-label">WORKSPACE</div><button class="nav-item ${!state.project?'selected':''}" data-action="home">${icon('grid')}创作空间</button><button class="nav-item" data-action="projects">${icon('folder')}我的项目 <span class="pill">${state.projects.length}</span></button></nav><div class="nav-group"><div class="nav-label">最近项目</div>${state.projects.slice(0,5).map(p=>`<button class="nav-item project-nav ${state.project?.id===p.id?'selected':''}" data-project="${p.id}">${icon('file')}<span>${escape(p.name)}</span></button>`).join('') || '<div class="hint nav-hint">从一个想法开始</div>'}</div><div class="sidebar-bottom"><div class="connection"><div><span class="dot ${ready?'ok':''}"></span>${ready?(state.status.source==='source'?'已接入本地 Harness':'Harness 命令可用'):'等待连接 Harness'}</div><div class="hint">${ready?'实际运行还需有效模型配置':'方案可手动编辑与保存'}</div><button data-action="settings">查看连接配置 ↗</button></div><div class="profile"><span class="avatar">本</span><div>本地工作空间<br><small>项目保存在这台电脑</small></div></div></div></aside><main class="main"><header class="topbar"><div class="crumb">工作空间 <span>/</span> <b>${state.project?escape(state.project.name):'创作空间'}</b></div><button class="mobile-brand" data-action="home"><span class="brandmark">h</span>Harness Studio</button><div class="top-actions"><span class="pill">LOCAL · 初始版本</span><button class="btn small" data-action="settings">${icon('settings')}连接设置</button><button class="btn primary small" data-action="new">${icon('plus')}新建项目</button></div></header>${content}</main></div>`;
    const oldChat=$('#chat-history');
    const chatBottom=!oldChat||oldChat.scrollHeight-oldChat.scrollTop-oldChat.clientHeight<40;
    const chatScroll=oldChat?.scrollTop||0;
    const app=$('#app');
    if(state.project && app.dataset.project===state.project.id && $('#stage-pane')){
      const template=document.createElement('template');template.innerHTML=markup;
      const fresh=template.content;
      for(const selector of ['.sidebar','.topbar','.project-heading','.stage-nav','.workspace-grid > aside','.assistant-toggle']){
        const current=$(selector), replacement=fresh.querySelector(selector);
        if(current && replacement)current.replaceWith(replacement);
      }
      const warning=$('#review-warning'), nextWarning=fresh.querySelector('#review-warning');
      if(warning)warning.remove();if(nextWarning)document.querySelector('.stage-nav').before(nextWarning);
      const stage=$('#stage-pane'), nextStage=fresh.querySelector('#stage-pane');
      stage.innerHTML=nextStage.innerHTML;stage.hidden=nextStage.hidden;
      const preview=$('#preview-pane'), nextPreview=fresh.querySelector('#preview-pane');
      preview.hidden=nextPreview.hidden;
      if(!nextPreview.hidden){
        const screen=$('#preview-screen'), nextScreen=nextPreview.querySelector('#preview-screen');
        if(screen && nextScreen){
          $('#preview-chrome').replaceWith(nextPreview.querySelector('#preview-chrome'));
          if(screen.dataset.identity!==nextScreen.dataset.identity||!nextScreen.querySelector('iframe'))screen.replaceWith(nextScreen);
        }else preview.innerHTML=nextPreview.innerHTML;
      }
    }else{
      app.innerHTML=markup;app.dataset.project=state.project?.id||'';
    }
    const grid=$('.workspace-grid');if(grid)grid.classList.toggle('assistant-closed',!state.assistantOpen);
    const chat=$('#chat-history');if(chat)chat.scrollTop=chatBottom?chat.scrollHeight:chatScroll;
    window.StudioDocuments?.render(app);
    if(state.previewExpanded)syncFullscreen();
    if(state.conversationMenuOpen)placeConversationMenu();
    if(state.modelMenu)placeModelPicker();
    if(state.stage==='develop')queueMicrotask(()=>ensureRuntime());
  }
  function mock(color) {return `<div class="case-art ${color}"><div class="mock-window"><div class="mock-bar"><i></i><i></i><i></i></div><div class="mock-content"><div class="mock-side"><i></i><i></i><i></i><i></i></div><div class="mock-main"><div class="mock-title"></div><div class="mock-stats"><i></i><i></i><i></i></div><div class="mock-table"><i></i><i></i><i></i><i></i><i></i></div></div></div></div></div>`;}
  function home() {
    stopSpeech();
    state.project = null; stopWatching();
    layout(`<div class="home"><section class="hero"><div class="eyebrow">${icon('sparkle')}FROM IDEA TO APPLICATION</div><h1>让你的想法，<span>成为可用的系统。</span></h1><p>描述需求，带上参考截图。与 Agent 一起设计、开发，直到每个细节都合适。</p><div class="composer"><div class="composer-header">${icon('chat')}你想构建什么？</div><textarea id="requirements" maxlength="30000" aria-label="需求描述" placeholder="填写补充说明，或先上传需求文档。文档内容和图片会随项目一起交给 AI 分析。">${escape(state.draft)}</textarea><div id="requirement-uploads">${documentMarkup()}</div><div id="uploads" class="attachments" ${state.uploads.length?'':'hidden'}>${uploadMarkup()}</div><p id="import-status" class="hint import-status" role="status">${escape(state.intakeError||'附件在本机暂存 24 小时，最多 4 个、每个 30 MB；正文和嵌入图片一并保留。输入框填写补充说明，创建项目时一起提交分析。旧 .doc 请先另存为 .docx。')}</p><div class="composer-footer"><div><button type="button" class="upload-btn" data-action="import-requirements">${icon('file')}导入需求文件</button><input type="file" id="requirements-file" accept=".docx,.md,.markdown,.txt" multiple hidden><label class="upload-btn" for="image-input">${icon('image')}添加参考截图</label><span class="upload-hint">最多 4 张，每张 3 MB</span><input type="file" id="image-input" accept="image/png,image/jpeg,image/webp" multiple hidden></div><button class="btn primary" data-action="create">开始我的项目 ${icon('arrow')}</button></div></div><div class="steps-mini"><span><b>1</b>导入需求与参考</span><i>→</i><span><b>2</b>共创与确认方案</span><i>→</i><span><b>3</b>开发与循环迭代</span><i>→</i><span><b>4</b>打包交付</span></div></section><section class="examples"><div class="section-head"><div><h2>从一个案例开始</h2><p>选择需求示例，加入你的想法。下方为示意图，非已生成系统。</p></div><span class="pill">灵感参考</span></div><div class="cards">${examples.map((e,i)=>`<button class="case" data-example="${i}">${mock(e.color)}<div class="case-info"><h3>${e.name}<span>↗</span></h3><p>${e.desc}</p><div class="tags">${e.tags.map(t=>`<span class="tag">${t}</span>`).join('')}</div></div></button>`).join('')}</div></section><section class="recent" id="recent"><div class="section-head"><h2>我的项目</h2><span class="hint">${state.projects.length} 个项目</span></div>${state.projects.length?state.projects.map(p=>`<button class="project-row" data-project="${p.id}"><span>${icon('folder')}${escape(p.name)}</span><small>${['queued','running','cancelling'].includes(p.job.status)?'任务处理中':p.approved?'方案已确认':'方案设计中'} · ${new Date(p.created*1000).toLocaleDateString('zh-CN')}</small></button>`).join(''):`<div class="empty-projects">${icon('folder')}还没有项目。在上方描述需求，创建你的第一个应用。</div>`}</section></div>`);
  }
  function uploadMarkup() {return state.uploads.map((file,i)=>`<div class="attachment"><img src="${file.data}" alt="参考截图 ${i+1}"><span>${escape(file.name)}</span><button data-remove="${i}" aria-label="移除 ${escape(file.name)}">×</button></div>`).join('');}
  function reviewReport(job) {
    const reports=job.reviews||[];
    modal('模型审查报告',`<p class="hint">报告为模型给出的审查证据，不代表平台独立验证或部署验收。</p>${job.localChecks?.length?`<h3>基础语法检查（不代表功能验证）</h3>${job.localChecks.map(check=>`<p>${escape(check.command)} · ${escape(check.status)}</p><pre class="design-body">${escape(check.result)}</pre>`).join('')}`:''}${reports.length?reports.map(report=>`<section><h3>${escape(({full:'完整审查',changes:'改动审查',recheck:'定向复验',basic:'基础检查'})[report.scope]||'审查')} · 第 ${report.round} 轮 · ${escape(report.model)} · ${escape(({pass:'通过',changes_requested:'需要修复',inconclusive:'证据不足'})[report.verdict])}</h3><p>${escape(report.summary)}</p>${report.findings.map(finding=>`<div class="notice"><strong>${escape(finding.severity)} · ${escape(finding.file)}:${finding.line}</strong><p>触发：${escape(finding.trigger)}</p><p>证据：${escape(finding.evidence)}</p><p>建议：${escape(finding.suggestion)}</p></div>`).join('')}${report.checks.map(check=>`<p><code>${escape(check.command)}</code> · ${escape(({passed:'通过',failed:'失败',not_run:'未执行'})[check.status]||check.status)}</p><pre class="design-body">${escape(check.result)}</pre>`).join('')}</section>`).join(''):'<p>尚无有效审查报告，请查看任务日志。</p>'}<h3>阶段记录</h3>${(job.workflowHistory||[]).map(step=>`<p>${escape(({analysis:'需求分析',development:'代码开发',review:'代码审查',repair:'审查修复'})[step.stage])} · ${escape(step.model)}${step.round?' · 第 '+step.round+' 轮':''} · ${escape(({running:'执行中',completed:'完成',failed:'失败',cancelled:'已取消',interrupted:'结果未知'})[step.status]||step.status)}</p>`).join('')}`);
  }
  function jobMarkup() {
    const job = state.project.job;
    const reviewStatus=state.project.reviewState?.status;
    const reviewPending=['pending','blocked'].includes(reviewStatus);
    const labels = {idle:'尚未提交任务',queued:'等待执行',running:'执行中',cancelling:'正在取消',completed:'任务完成',failed:'执行失败',cancelled:'已取消',interrupted:'结果未知',blocked:'需要重新确认'};
    const connection = state.connection==='open'?'进度已连接':state.connection==='offline'?'连接已断开，正在重连；后台任务继续':'正在连接进度';
    const queued = state.project.queue || [];
    const workerNotice=queued.length && state.worker && !state.worker.online?'<div class="notice">Worker 暂无心跳，任务已保存。请查看 worker.log 或重新启动 Worker；不会自动重复执行结果未知的任务。</div>':'';
    return `${state.runtimeError?`<div class="notice" role="alert">${escape(state.runtimeError)}</div>`:''}${workerNotice}<div class="hint stream-state" role="status">${escape(connection)}</div>${job.activeModel?`<p class="hint">${escape(job.kind==='chat'?'项目问答':({analysis:'需求分析',development:'代码开发',review:'代码审查',repair:'审查修复'})[job.workflowStage]||'任务处理')} · ${escape(job.activeModel)}${job.activeProvider?' · '+escape(job.activeProvider.replace(/^gpt-ge-/,'')):''}${job.reasoning?' · '+escape(job.reasoning):''}${job.reviewRound?' · 第 '+job.reviewRound+' 轮':''}</p>`:''}${job.reviews?.length?`<button class="btn small" data-review-job="${job.id}">查看审查报告 · ${job.reviews.length} 轮</button>`:''}<div class="job-status">${icon(job.status==='completed'?'check':'clock')}<div><h3 class="status-label ${busy()?'busy':''}">${job.kind==='chat'&&job.status==='completed'?'问答完成':job.status==='completed'&&reviewPending?(state.project.reviewState?.status==='blocked'?'修改验证未通过':'修改仍待验证'):labels[job.status] || '状态未知'}</h3><p>${escape(job.message || '提交后会显示真实执行进度')}</p>${job.status==='running'&&job.modelRetry?`<p class="hint">自动重试 ${job.modelRetry.attempt}/${job.modelRetry.maximum} · <span data-retry-at="${Number(job.modelRetry.nextAt)}">${Math.max(0,Math.ceil(job.modelRetry.nextAt-Date.now()/1000))}</span> 秒后重连</p>`:''}${job.timeoutSeconds?`<small class="hint">任务时限 ${Number(job.timeoutSeconds/60).toLocaleString('zh-CN')} 分钟</small><br>`:''}${job.progressAt?`<small class="hint">最近进度 ${new Date(job.progressAt*1000).toLocaleTimeString('zh-CN')}</small>`:''}</div></div>${!busy()&&(reviewPending||job.status==='failed'&&job.reviews?.length)?'<button class="btn small" data-action="continue-review">继续修复审查问题</button>':''}${job.status!=='idle'?'<button class="btn small" data-action="logs">查看任务日志</button>':''}${['running','cancelling','queued'].includes(job.status)?` <button class="btn small danger" data-action="cancel" ${disabled(job.status==='cancelling')}>${job.status==='queued'?'取消排队':'取消任务'}</button>`:''}${queued.length?`<div class="queue-list"><h3>待处理任务 · ${queued.length}</h3>${queued.map(record=>`<div class="queue-row"><span>${escape(record.route==='style'?'样式快速修改':({chat:'项目问答',analyze:'需求分析',revise:'方案修改',build:'开发系统',iterate:'系统迭代'})[record.kind])} · ${labels[record.status]}</span>${record.status==='queued'?`<button class="btn small" data-cancel-job="${record.id}">取消</button>`:''}</div>`).join('')}<p class="hint">关闭网页或重启网页服务不会停止后台任务</p></div>`:''}`;
  }
  function taskHistory() {
    const labels={queued:'排队中',running:'执行中',cancelling:'取消中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'结果未知',blocked:'需确认'};
    return `<section class="panel"><div class="panel-head"><h2>任务记录</h2><span class="pill">最近 20 项</span></div><div class="panel-body">${(state.project.jobHistory||[]).map(record=>`<div class="task-history-row"><strong>${escape(record.route==='style'?'样式快速修改':({chat:'项目问答',analyze:'需求分析',revise:'方案修改',build:'开发系统',iterate:'系统迭代'})[record.kind])} · ${labels[record.status]}</strong><p class="hint">${escape(record.message)}</p><div><button class="btn small" data-job-log="${record.id}">查看日志</button>${record.workflowHistory?.length?`<button class="btn small" data-review-job="${record.id}">审查 / 阶段记录</button>`:''}${['failed','cancelled','interrupted','blocked'].includes(record.status)?` <button class="btn small" data-retry="${record.id}" ${disabled(busy())}>按当前方案重试</button>`:''}</div></div>`).join('')||'<p class="hint">尚未提交后台任务</p>'}</div></section>`;
  }
  function assistantTask() {
    return (state.project.queue||[]).find(job=>['running','cancelling'].includes(job.status)&&job.chatMessage&&(job.conversationId||'legacy')===state.conversationId);
  }
  function queuedChatMessages() {
    return (state.project.queue||[]).filter(job=>job.kind==='chat'&&job.status==='queued'&&job.chatMessage&&(job.conversationId||'legacy')===state.conversationId);
  }
  function steeringQueue() {
    const messages=queuedChatMessages();
    return messages.length?`<div class="steering-queue" aria-label="待发送的引导消息">${messages.map(job=>`<div class="steering-row"><span class="steering-marker" aria-hidden="true">↳</span><span class="steering-text" title="${escape(job.chatMessage.text)}">${escape(job.chatMessage.text)}</span><button class="steering-action" data-steer-message="${job.id}" ${disabled(assistantTask()?.status!=='running')} title="停止当前轮次，并用这条消息引导后续处理">↪ 引导</button><button class="steering-remove" data-cancel-job="${job.id}" aria-label="删除排队消息：${escape(job.chatMessage.text.slice(0,40))}" title="删除排队消息">×</button></div>`).join('')}</div>`:'';
  }
  function chatMessages() {
    const queued=new Set(queuedChatMessages().flatMap(job=>[job.id,job.id+'-reply']));
    const messages=(state.project.chatHistory||[]).filter(message=>(message.conversationId||'legacy')===state.conversationId&&!queued.has(message.id));
    return messages.length?messages.map(message=>`<article class="chat-message ${message.role==='user'?'chat-user':'chat-assistant'}"><div class="chat-message-meta">${message.role==='user'?'你':'项目助手'}${message.model?' · '+escape(message.model):''}${message.role==='user'&&message.kind!=='chat'?' · '+(message.kind==='revise'?'修改方案':'修改系统'):''}</div>${message.target&&message.target!=='整个项目'?`<p class="chat-context">${escape(message.target)}</p>`:''}${(message.images||[]).length?`<div class="chat-message-images">${message.images.map(item=>`<img src="${escape(item.url)}" alt="${escape(item.name)}" loading="lazy">`).join('')}</div>`:''}${(message.files||[]).length?`<div class="chat-message-files">${message.files.map(item=>`<a href="${escape(item.url)}" download="${escape(item.name)}">${icon('file')}${escape(item.name)}</a>`).join('')}</div>`:''}${message.role==='assistant'&&['blocked','pending'].includes(message.reviewStatus)?`<p class="notice" role="status">${message.reviewStatus==='blocked'?'修改验证未通过，不能认定问题已解决':'修改验证不完整，仍需补充验证'}</p>`:''}<div class="chat-message-text" ${message.role==='assistant'&&message.status==='completed'?'data-document':''}>${escape(message.text)}</div>${message.status==='failed'||message.status==='interrupted'||message.status==='cancelled'||message.status==='blocked'?'<p class="error">本次未完成，可保留上下文重新发送</p>':''}</article>`).join(''):'';
  }
  function attachmentSize(size) {return size<1024?size+' B':size<1024*1024?(size/1024).toFixed(1)+' KiB':(size/1024/1024).toFixed(1)+' MiB';}
  function feedbackPanel() {
    const policy=state.status?.modelRouting;
    const models=[...new Set(policy?[...(policy.assistantModels||[]),policy.analysis,policy.development,policy.review,policy.fallback?.to].filter(Boolean):[])];
    const conversation=(state.project.conversations||[]).find(item=>item.id===state.conversationId);
    const cards=[...state.chatFiles.map((item,index)=>`<div class="composer-attachment file-attachment"><span class="attachment-symbol">${icon('file')}</span><span title="${escape(item.name)}">${escape(item.name)}</span><small>${attachmentSize(item.size)}</small><button data-remove-chat-file="${index}" aria-label="移除文件 ${escape(item.name)}" title="移除文件">×</button></div>`),...state.chatImages.map((item,index)=>`<div class="composer-attachment image-attachment"><img src="${escape(item.data)}" alt="${escape(item.name)}"><button data-remove-chat-image="${index}" aria-label="移除图片 ${escape(item.name)}" title="移除图片">×</button><span>${escape(item.name)}</span></div>`),...state.contexts.map((item,index)=>`<div class="composer-attachment context-attachment"><span class="attachment-symbol">${icon('monitor')}</span><span>${escape(item)}</span><button data-remove-chat-context="${index}" aria-label="移除选区 ${index+1}" title="移除选区">×</button></div>`)];
    return `<section class="panel project-chat" aria-label="项目聊天"><div class="panel-head"><h2 class="assistant-heading">项目助手<button class="conversation-triangle" data-action="chat-history" aria-label="历史对话" aria-controls="conversation-directory" aria-expanded="${state.conversationMenuOpen}">▾</button></h2><div class="chat-header-actions"><button class="btn small" data-action="new-chat">新对话</button></div></div>${conversationDirectory()}<div id="conversation-title" hidden>${escape(conversation?.title||'以前的对话')}</div><div class="chat-history" id="chat-history" ${(state.project.chatHistory||[]).some(message=>(message.conversationId||'legacy')===state.conversationId)?'':'hidden'} role="log" aria-label="项目对话记录">${chatMessages()}</div><div class="chat-compose">${steeringQueue()}<div class="codex-composer" aria-label="消息与附件拖放区"><div class="composer-attachments" ${cards.length?'':'hidden'}>${cards.join('')}</div><input id="target" type="hidden" value="${escape(state.selected)}"><label class="sr-only" for="feedback">消息</label><textarea id="feedback" placeholder="提问或描述希望修改的内容…" maxlength="10000">${escape(state.note)}</textarea><div class="chat-tools"><input id="chat-attachment-input" type="file" accept="*/*" multiple hidden><button class="composer-icon" data-action="chat-upload" ${disabled(state.chatAttaching)} aria-label="添加照片或文件" title="添加任意格式文件（含 GLB）；不支持文件夹，附件合计最多 64 MiB">${icon('plus')}</button><label class="sr-only" for="chat-model">本次对话模型</label><select id="chat-model" aria-label="本次对话模型" hidden><option value="">${escape(policy?.analysis||'跟随阶段配置')}</option>${models.map(model=>`<option value="${escape(model)}" ${state.chatModel===model?'selected':''}>${escape(model)}</option>`).join('')}</select><button class="model-settings-button" data-action="model-settings" aria-label="模型与推理强度" aria-controls="model-picker" aria-expanded="${Boolean(state.modelMenu)}">${escape(modelLabel(state.chatModel||policy?.analysis||'默认'))} <span id="reasoning-button-label">${escape(state.chatReasoning)}</span>⌄</button>${modelPicker(models,policy)}<button class="composer-icon" data-action="voice" aria-pressed="${Boolean(state.speech)}" aria-label="${state.speech?'停止语音输入':'开始语音输入'}" title="${state.speech?'停止语音输入':'语音输入'}">${icon('mic')}</button>${assistantTask()?`<button class="composer-icon assistant-interrupt" data-action="interrupt-assistant" aria-label="中断思考" title="中断当前助手任务" ${disabled(assistantTask().status==='cancelling')}>■</button>`:''}<button class="composer-send" data-action="feedback" ${disabled(state.chatAttaching)} aria-label="${busy()?'排队发送':'发送'}" title="发送">↑</button></div></div><div class="chat-error error" id="chat-error" role="alert">${escape(state.speechError||state.chatError)}</div><p class="hint" id="draft-status" role="status">${escape(state.chatAttaching?'正在添加附件…':state.draftError)}</p></div></section>`;
  }
  const reasoningLevels=['low','medium','high','xhigh','max'];
  function modelLabel(name) {
    return ({'gpt-6.1-sol':'GPT-6.1 Sol','gpt-6-sol':'GPT-6 Sol','gpt-6-astra':'GPT-6 Astra','claude-sonnet-5-5':'Claude Sonnet 5.5'})[name]||name;
  }
  function modelPicker(models,policy) {
    const level=reasoningLevels.indexOf(state.chatReasoning);
    return `<div id="model-picker" class="model-picker" role="dialog" aria-label="模型与推理设置" ${state.modelMenu?'':'hidden'}>${state.modelMenu==='models'?`<div class="model-menu-caption">选择模型</div><button class="model-choice default-model" data-select-chat-model=""><span>默认<small>推荐模型集</small></span>${!state.chatModel?'✓':''}</button>${models.map(model=>`<button class="model-choice" data-select-chat-model="${escape(model)}"><span>${escape(modelLabel(model))}</span>${state.chatModel===model?'✓':''}</button>`).join('')}`:`<button class="model-effort-heading" data-action="model-list"><span aria-hidden="true">ϟ</span><span>${escape(modelLabel(state.chatModel||policy?.analysis||'默认'))} <em id="reasoning-menu-label">${escape(state.chatReasoning)}</em> ›</span></button><div class="reasoning-track" style="--effort-fill:${level*25}%"><div class="reasoning-dots" aria-hidden="true">${reasoningLevels.map(()=>'<i></i>').join('')}</div><input id="chat-reasoning" type="range" min="0" max="4" step="1" value="${level}" aria-label="推理强度" aria-valuetext="${escape(state.chatReasoning)}"></div><div class="reasoning-labels">${reasoningLevels.map(value=>`<span>${value}</span>`).join('')}</div>`}</div>`;
  }
  function placeModelPicker() {
    const menu=$('#model-picker'),button=$('[data-action="model-settings"]');if(!menu||!button||!state.modelMenu)return;
    const anchor=button.getBoundingClientRect(),width=Math.min(256,innerWidth-32);
    menu.style.width=width+'px';menu.style.maxHeight=Math.max(100,innerHeight-32)+'px';
    const height=menu.getBoundingClientRect().height;
    menu.style.left=Math.max(16,Math.min(anchor.right-width,innerWidth-width-16))+'px';
    menu.style.top=Math.max(16,Math.min(anchor.top-height-10,innerHeight-height-16))+'px';
  }
  function closeModelPicker() {
    state.modelMenu=null;const menu=$('#model-picker');if(menu)menu.hidden=true;
    $('[data-action="model-settings"]')?.setAttribute('aria-expanded','false');
  }
  function restoreChatAttachments(draft) {
    state.chatImages=Array.isArray(draft?.images)?draft.images.filter(item=>typeof item?.name==='string'&&typeof item?.data==='string'&&/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(item.data)&&item.data.length<=4200000).slice(0,4):[];
    state.chatFiles=Array.isArray(draft?.files)?draft.files.filter(item=>typeof item?.name==='string'&&typeof item?.data==='string'&&/^[A-Za-z0-9+/=]*$/.test(item.data)&&item.data.length<=89478488&&Number.isFinite(item.size)).slice(0,4):[];
    state.contexts=Array.isArray(draft?.contexts)?draft.contexts.filter(item=>typeof item==='string').slice(0,8):state.selected==='整个项目'?[]:[state.selected];
  }
  function attachContext(context) {
    if(!state.contexts.includes(context))state.contexts.push(context);
    state.contexts=state.contexts.slice(-8);state.selected=state.contexts.join('；').slice(0,1000);
  }
  async function addChatFiles(files) {
    if(state.chatAttaching)return;
    const project=state.project.id,conversation=state.conversationId;
    try{
      let imagesCount=state.chatImages.length,filesCount=state.chatFiles.length;
      let total=state.chatFiles.reduce((sum,item)=>sum+item.size,0)+state.chatImages.reduce((sum,item)=>sum+Math.ceil(item.data.split(',')[1].length*3/4),0);
      for(const file of files){
        const photo=file.size<=3*1024*1024&&(['image/png','image/jpeg','image/webp'].includes(file.type)||/\.(png|jpe?g|webp)$/i.test(file.name));
        if(photo){if(++imagesCount>4)throw new Error('最多添加 4 张预览照片');}
        else if(++filesCount>4)throw new Error('最多添加 4 个文件');
        total+=file.size;if(total>64*1024*1024)throw new Error('照片与文件合计不能超过 64 MiB');
      }
      state.chatAttaching=true;state.chatError='';workbench();
      const images=[],attachments=[];
      for(const file of files){
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('附件读取失败，请重新添加'));reader.readAsDataURL(file);});
        const raw=data.split(',')[1];
        const photo=file.size<=3*1024*1024&&(['image/png','image/jpeg','image/webp'].includes(file.type)||/\.(png|jpe?g|webp)$/i.test(file.name));
        if(photo){const kind=file.type==='image/png'||/\.png$/i.test(file.name)?'png':file.type==='image/webp'||/\.webp$/i.test(file.name)?'webp':'jpeg';images.push({name:file.name,data:'data:image/'+kind+';base64,'+raw});}
        else attachments.push({name:file.name,data:raw,size:file.size});
      }
      if(state.project?.id!==project||state.conversationId!==conversation)return;
      state.chatImages.push(...images);state.chatFiles.push(...attachments);saveDraft();
    }catch(error){if(state.project?.id===project&&state.conversationId===conversation)state.chatError=errorText(error);}
    finally{state.chatAttaching=false;if(state.project){workbench();if(state.project.id===project&&state.conversationId===conversation)$('#feedback')?.focus({preventScroll:true});}}
  }
  let chatDragDepth=0;
  function fileDrag(event){return Array.from(event.dataTransfer?.types||[]).includes('Files');}
  document.addEventListener('dragenter',event=>{if(!state.project||!fileDrag(event)||!event.target.closest?.('.project-chat'))return;event.preventDefault();chatDragDepth++;$('.project-chat')?.classList.add('drag-active');});
  document.addEventListener('dragover',event=>{if(!state.project||!fileDrag(event))return;event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect=event.target.closest?.('.project-chat')?'copy':'none';});
  document.addEventListener('dragleave',event=>{if(!event.target.closest?.('.project-chat')||!fileDrag(event))return;if(--chatDragDepth<=0){chatDragDepth=0;$('.project-chat')?.classList.remove('drag-active');}});
  document.addEventListener('drop',async event=>{
    if(!state.project||!fileDrag(event))return;event.preventDefault();chatDragDepth=0;$('.project-chat')?.classList.remove('drag-active');
    if(!event.target.closest?.('.project-chat'))return;
    if(Array.from(event.dataTransfer.items||[]).some(item=>item.webkitGetAsEntry?.()?.isDirectory)){state.chatError='请拖入文件，不支持文件夹';workbench();return;}
    await addChatFiles(Array.from(event.dataTransfer.files||[]));
  });

  function stopSpeech() {
    const speech=state.speech;state.speech=null;if(speech)speech.abort();
  }
  function voiceInput() {
    if(state.speech){stopSpeech();workbench();return;}
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
    if(!Recognition){state.speechError='当前浏览器不支持语音输入，请使用 Chrome 或系统听写';workbench();return;}
    const speech=new Recognition(),project=state.project.id,base=state.note;
    speech.lang='zh-CN';speech.interimResults=true;speech.continuous=false;
    state.speech=speech;state.speechError='';
    speech.onresult=event=>{
      if(state.speech!==speech||state.project?.id!==project)return;
      let words='';for(let i=0;i<event.results.length;i++)words+=event.results[i][0].transcript;
      state.note=(base+(base?'\n':'')+words).slice(0,10000);
      const input=$('#feedback');if(input)input.value=state.note;saveDraft();
    };
    speech.onerror=event=>{if(state.speech!==speech)return;state.speechError=event.error==='not-allowed'?'麦克风权限被拒绝，请在浏览器设置中允许后重试':event.error==='no-speech'?'没有听到语音，请重试':'语音识别失败，请检查网络或改用文字输入';};
    speech.onend=()=>{if(state.speech!==speech)return;state.speech=null;workbench();};
    try{speech.start();workbench();}catch(error){state.speech=null;state.speechError='无法启动语音输入，请检查麦克风权限';workbench();}
  }

  function requirementsPanel() {const p=state.project;return `<section class="panel"><div class="panel-head"><h2>原始需求</h2></div><div class="panel-body"><p class="hint requirements-text">${escape(p.requirements||'补充说明为空，请结合需求附件分析。')}</p>${(p.documents||[]).map(document=>`<div class="requirement-attachment"><div><strong>${escape(document.name)}</strong><p class="hint">${document.images.length} 张嵌入图片</p>${document.warnings.map(warning=>`<p class="hint">${escape(warning)}</p>`).join('')}</div><a class="btn small" href="${projectUrl('documents/'+document.id+'/original')}" download>原文件</a></div>`).join('')}${p.images.length?`<div class="attachments">${p.images.map(img=>`<a class="attachment" href="${projectUrl('references/'+img.file)}" target="_blank" rel="noopener"><img src="${projectUrl('references/'+img.file)}" alt="${escape(img.name)}"></a>`).join('')}</div><p class="hint">截图已保存。实际识图能力取决于模型与工具配置。</p>`:''}</div></section>`;}
  function workbench() {
    const p = state.project;
    const incomplete=keys.filter(key=>p.plan?.[key].includes('待填写：请点击「编辑原文」完善这一部分。'));
    const tabs = [['plan','file','方案设计'],['develop','code','开发与预览'],['versions','clock','版本记录'],['deliver','box','打包交付'],['execution','clock','执行状态']];
    if(state.stage==='plan')state.assistantScope='plan';
    if(state.stage==='develop')state.assistantScope='code';
    let center = '';
    if (state.stage==='plan') {
      center = `<section class="panel"><div class="panel-head"><h2>设计方案 <span class="pill">${p.plan?'V'+p.versions.length:'待生成'}</span></h2><button class="btn small" data-action="analyze" ${disabled(busy())}>${icon('sparkle')}${p.plan?'重新分析需求':'AI 分析需求'}</button></div>${p.plan?keys.map((key,i)=>`<article class="design-card"><div class="design-title"><h3>${icon(sectionIcons[i])}${titles[i]}</h3><div><button class="btn small" data-edit="${key}" ${disabled(busy())}>编辑原文</button> <button class="btn small" data-feedback="${key}">提修改</button></div></div><div class="document-content" data-document>${escape(p.plan[key])}</div></article>`).join(''):`<div class="design-placeholder"><div class="big-icon">${icon('file')}</div><h3>先把想法变成清晰的方案</h3><p>连接 Harness 后生成 PRD、前端、后端与数据库设计。也可以先手动创建方案，再逐步完善。</p><button class="btn" data-action="manual">${icon('plus')}手动创建方案</button></div>`}</section>`;
    } else if (state.stage==='develop') {
      const hasSource=p.previewAvailable??Boolean(p.built_from);
      const hasPreview=state.runtime?.status==='running'&&Boolean(state.runtime.url);
      const live=state.previewKind==='runtime' && state.runtime?.status==='running';
      const source=live?state.runtime.url:'';
      center = `<section class="panel"><div id="preview-chrome"><div class="panel-head"><h2>系统预览</h2><button class="btn primary small" data-action="build" ${disabled(busy() || !p.approved || incomplete.length)}>${icon('code')}${p.hasWorkspaceProgress||p.built_from?'继续 / 重新开发':'开始开发'}</button></div><div class="preview-toolbar preview-controls"><div role="group" aria-label="预览操作模式"><button data-action="experience" aria-pressed="${state.previewMode==='experience'}">体验模式</button><button data-action="inspect" aria-pressed="${state.previewMode==='inspect'}">点选提问</button><button data-action="region" aria-pressed="${state.previewMode==='region'}">框选提问</button></div><div><button data-action="runtime-start" ${disabled(busy() || !state.runtime?.preflight?.ready || (state.runtime?.status==='starting'||state.runtime?.replacementStatus==='starting'||state.runtime?.status==='running'&&!state.runtime?.replacementStatus))}>${state.runtime?.replacementStatus==='failed'?'重试新版本':state.runtime?.status==='running'?'运行中':state.runtime?.status==='starting'?'正在启动…':'重试运行预览'}</button><button data-action="runtime-checks">运行检查</button><button data-action="runtime-logs">预览日志</button><button data-action="refresh-preview">刷新 ↻</button><button data-action="fullscreen" ${disabled(!hasPreview)}>${state.previewExpanded?'退出全屏':'全屏预览'}</button></div></div>${hasSource&&['pending','blocked'].includes(p.reviewState?.status)?'<p class="notice" id="preview-review-notice">代码已保留，审查仍有待处理项；审查通过前不能确认交付</p>':''}${state.runtime?.targetRevision && state.runtime.targetRevision!==state.runtime.revision?`<p class="notice" role="status">${escape(state.runtime.message)}；可查看预览日志</p>`:''}<p class="preview-help" id="preview-help">${previewHelp()}</p></div><div id="preview-screen" data-identity="${escape(p.id+':'+(live?state.runtime.url:'static')+':'+hasPreview)}">${hasPreview?`<iframe id="preview" class="preview" title="生成系统预览" sandbox="allow-scripts${live?' allow-same-origin allow-forms':''}" src="${escape(source)}"></iframe>`:`<div class="design-placeholder"><div class="big-icon">${icon('monitor')}</div><h3>${state.runtime?.status==='starting'?'正在启动运行预览':hasSource?'运行预览尚未就绪':p.approved?'开始开发后自动运行预览':'确认方案后开始开发'}</h3><p role="status">${escape(state.runtimeError||(state.runtime?.status==='failed'?state.runtime.message:hasSource?state.runtime?.preflight?.detail:'完成开发后，将自动启动实际程序'))}</p></div>`}</div></section>`;
    } else if (state.stage==='versions') {
      center = `<section class="panel"><div class="panel-head"><h2>方案版本</h2><span class="pill">${p.versions.length} 个版本</span></div><div class="panel-body">${p.versions.length?p.versions.slice().reverse().map(v=>`<div class="version-row"><div><strong>V${v.number} · ${escape(v.reason)}</strong><p>${new Date(v.time*1000).toLocaleString('zh-CN')}</p></div><button class="btn small" data-version="${v.number}">查看 / 对比 / 恢复</button></div>`).join(''):'<p class="hint">保存或生成方案后，这里会保留完整快照。</p>'}</div></section><section class="panel"><div class="panel-head"><h2>修改记录</h2></div><div class="panel-body">${p.feedback.slice().reverse().map(f=>`<div class="version-row"><div><strong>${escape(f.target)}</strong><p>${escape(f.note)}</p><p>基于 V${f.version} · ${new Date(f.time*1000).toLocaleString('zh-CN')}</p></div></div>`).join('')||'<p class="hint">尚未提交修改意见。</p>'}</div></section>`;
    } else if(state.stage==='execution'){
      center=`<section class="panel"><div class="panel-head"><h2>执行状态</h2></div><div class="panel-body" id="job-status">${jobMarkup()}</div></section>${taskHistory()}`;
    } else {
      center = `<section class="panel"><div class="panel-head"><h2>交付你的应用</h2>${icon('box')}</div><div class="panel-body"><p class="hint">交付包面向安装了 Docker 的服务器，包含已确认设计与生成源码。下载前会检查必要文件。</p><div class="deliverables">${[['code','应用源码','前端、后端与数据库迁移'],['box','容器部署文件','Dockerfile 与 compose.yaml'],['settings','环境变量模板','.env.example，排除实际环境变量文件'],['file','部署与验证说明','README.md 与 VALIDATION.md']].map(([i,t,d])=>`<div class="deliverable">${icon(i)}<div>${t}<small>${d}</small></div></div>`).join('')}</div><div class="notice">当前版本提供源码打包，不代表一键部署已验证。请检查生成的测试报告，并在目标环境验证启动、数据迁移与备份恢复。</div>${p.reviewState?.full===false?'<div class="notice">本轮为局部审查，请先执行交付前完整审查；无需重新开发。</div>':''}<button class="btn" data-action="final-review" ${disabled(busy() || !p.built_from || !p.approved)}>交付前完整审查</button> <button class="btn" data-action="accept" ${disabled(busy() || !p.built_from || !p.approved || p.accepted || ['pending','blocked'].includes(p.reviewState?.status) || p.reviewState?.full===false)}>${icon('check')}${p.accepted?'最终版本已确认':'确认最终版本'}</button> <button class="btn primary" data-action="export" ${disabled(busy() || !p.accepted || ['pending','blocked'].includes(p.reviewState?.status))}>${icon('download')}下载源码交付包</button></div></section>`;
    }
    if(state.stage==='plan')center+=requirementsPanel();
    layout(`<div class="workbench"><div class="project-heading"><div><div class="eyebrow">PROJECT WORKSPACE</div><h1>${escape(p.name)}</h1><p>${p.approved?'当前方案已确认':'需求与方案共创中'} · ${p.images.length} 张参考截图</p></div><button class="btn ${p.approved?'':'primary'}" data-action="approve" ${disabled(!p.plan || busy() || p.approved || incomplete.length)}>${icon('check')}${incomplete.length?'完善草稿后确认':p.approved?'方案已确认':'确认当前方案'}</button></div>${incomplete.length?`<div class="notice" id="review-warning" role="status">请先完善占位草稿：${incomplete.map(key=>titles[keys.indexOf(key)]).join('、')}。点击各部分的「编辑原文」填写后再确认。</div>`:''}<nav class="stage-nav">${tabs.map(([id,i,label])=>`<button data-stage="${id}" class="${state.stage===id?'selected':''}">${icon(i)}${label}</button>`).join('')}</nav>${!state.status?.available?`<div class="notice">${escape(state.status?.detail || 'Harness 尚未就绪，请查看连接设置。')}</div>`:''}<button class="assistant-toggle btn primary" data-action="toggle-assistant" aria-controls="assistant-pane" aria-expanded="${state.assistantOpen}">${icon('chat')}项目助手</button><div class="workspace-grid ${state.assistantOpen?'':'assistant-closed'}"><div class="aside-stack"><div id="stage-pane" ${state.stage==='develop'?'hidden':''}>${state.stage==='develop'?'':center}</div><div id="preview-pane" ${state.stage==='develop'?'':'hidden'}>${state.stage==='develop'?center:''}</div></div><aside class="aside-stack" id="assistant-pane" ${state.assistantOpen?'':'hidden'}>${feedbackPanel()}</aside></div></div>`);
  }
  function modal(title, body, after) {
    const el=$('#modal'); if(el.open) el.close();
    el.innerHTML=`<div class="modal-head"><h2 id="modal-title">${escape(title)}</h2><button data-close aria-label="关闭">×</button></div><div class="modal-body">${body}</div>`;
    el.showModal();window.StudioDocuments?.render(el); if(after) after(el);
  }
  function closeModal() {$('#modal').close();if($('#feedback')){$('#feedback').value=state.note;$('#target').value=state.selected;}}
  function settings() {
    const source=state.status?.source==='source';
    const models=state.status?.modelRouting;
    const routing=models?`<p>需求分析：${escape(models.analysis)}${models.stageProviders?' · '+escape(models.stageProviders.analysis.replace(/^gpt-ge-/,'')):''}<br>开发与修复：${escape(models.development)}${models.stageProviders?' · '+escape(models.stageProviders.development.replace(/^gpt-ge-/,'')):''}<br>审查：${escape(models.review)}${models.stageProviders?' · '+escape(models.stageProviders.review.replace(/^gpt-ge-/,'')):''}${models.reasoning?' · 推理 '+escape(models.reasoning):''} · 最多 ${models.maxReviewRounds} 轮</p><p class="hint">业务开发审查通过后仍需人工验收；样式快速修改不进入模型互审。模型可用性需由 GPT.GE 实际响应验证。</p>`:`<p class="notice">${escape(state.status?.modelRoutingError||'尚未读取模型路由配置')}</p>`;
    modal('连接 DeepSeek Harness', `${routing}<p class="hint">${source?'已选择同目录的 Harness 源码入口，无需全局安装 dsh。':'工作台通过配置的 dsh 入口调用 Harness。'}开发任务仍在各自的项目工作目录中运行。</p><p class="hint">当前启动命令</p><pre class="code">${escape(state.status?.command || '尚未找到可用入口')}</pre>${state.status?.detail?`<div class="notice">${escape(state.status.detail)}</div>`:''}<p class="hint">在启动工作台的终端配置密钥：</p><pre class="code">export GPT_GE_DEFAULT_API_KEY='你的 default 分组令牌'\nexport GPT_GE_CODEX_API_KEY='你的 codex 分组令牌'\npython3 studio/server.py</pre><p class="hint">模型密钥从服务环境或 Harness 自己的凭据配置读取，不保存在浏览器。项目根目录的 .env 不会自动复制到生成项目中。</p><p class="hint">需要指定其他 Harness 安装时，可设置 STUDIO_DSH_COMMAND。完整说明见 studio/README.zh.md。</p><div class="notice info">${state.status?.available?'启动入口已找到；模型连通性尚需实际任务验证。':'启动入口尚未就绪，请按上方提示处理后重启工作台。'} ${state.status?.hasApiKey?'已检测到环境变量中的 API Key。':'未检测到环境变量中的 API Key；Harness 自身的凭据配置仍可能可用。'}</div><p class="hint">${escape(state.status?.imageSupport)}</p>`);
  }
  async function openProject(id) {
    stopSpeech();state.assistantOpen=false;state.conversationMenuOpen=false;state.speechError='';state.chatError='';await leaveFullscreen();stopWatching();
    state.project=await api(`/api/projects/${id}`); state.stage='plan';state.selected='整个项目';state.note='';state.previewMode='experience';state.previewKind='runtime';state.runtimeAttempt='';state.runtimeError='';state.runtime=await api(`/api/projects/${id}/runtime`);
    const draft=readDraft(id);
    state.feedbackKind='chat';
    state.conversationId=(state.project.conversations||[{id:'legacy'}]).some(item=>item.id===draft?.conversationId)?draft.conversationId:'legacy';
    state.assistantScope=draft?.assistantScope==='code'?'code':'plan';
    state.conversationDrafts=draft?.conversationDrafts&&typeof draft.conversationDrafts==='object'?draft.conversationDrafts:{};
    state.chatModel=typeof draft?.model==='string'?draft.model:'';
    state.chatReasoning=reasoningLevels.includes(draft?.reasoning)?draft.reasoning:'high';state.modelMenu=null;
    state.taskRoute=state.feedbackKind==='iterate' && draft?.route==='style'?'style':'business';
    const conversationDraft=state.conversationDrafts[state.conversationId]||draft;
    state.note=typeof conversationDraft?.note==='string'?conversationDraft.note.slice(0,10000):'';
    state.selected=typeof conversationDraft?.target==='string'?conversationDraft.target.slice(0,1000):'整个项目';restoreChatAttachments(conversationDraft);
    state.stage=['plan','develop','versions','deliver','execution'].includes(draft?.stage)?draft.stage:'plan';
    state.sections={};
    for(const key of keys){const edit=draft?.sections?.[key];if(edit && typeof edit.text==='string' && Number.isInteger(edit.baseVersion))state.sections[key]={text:edit.text.slice(0,100000),baseVersion:edit.baseVersion};}
    history.replaceState(null,'',`/#project/${id}`); workbench(); watch();
  }
  async function ensureRuntime(force=false) {
    const project=state.project;
    if(!project||state.stage!=='develop'||busy()||!state.runtime?.preflight?.ready||state.runtime?.status==='starting'||!force&&state.runtime?.status==='running'&&(state.runtime.targetRevision??state.runtime.revision??null)===(project.previewRevision??null))return;
    const attempt=project.id+':'+(project.previewRevision??project.built_job);
    if(!force&&state.runtimeAttempt===attempt)return;
    state.runtimeAttempt=attempt;state.runtimeError='';if(state.runtime?.status!=='running')state.runtime={...state.runtime,status:'starting'};workbench();
    try{
      const runtime=await api(`/api/projects/${project.id}/runtime`,{});
      if(state.project?.id!==project.id)return;
      state.runtime={...state.runtime,...runtime};state.previewKind='runtime';
    }catch(error){if(state.project?.id!==project.id)return;if(state.runtime?.status!=='running')state.runtime={...state.runtime,status:'failed'};state.runtimeError=errorText(error);}
    if(state.project?.id===project.id)workbench();
  }
  function stopWatching() {
    if(state.stream)state.stream.close();state.stream=null;
  }
  function watch() {
    stopWatching();
    if(!state.project)return;
    const id=state.project.id;
    state.connection='connecting';
    const stream=new EventSource(`/api/projects/${id}/events`);
    state.stream=stream;
    let refreshSequence=0;
    const updateStatus=()=>{const host=$('#job-status');if(host)host.innerHTML=jobMarkup();};
    stream.onopen=()=>{if(state.project?.id===id){state.connection='open';updateStatus();}};
    stream.onerror=()=>{if(state.project?.id===id){state.connection='offline';updateStatus();}};
    stream.addEventListener('worker',event=>{if(state.project?.id===id && state.stream===stream){state.worker=JSON.parse(event.data);updateStatus();}});
    stream.addEventListener('preview',event=>{
      if(state.project?.id!==id || state.stream!==stream)return;
      const runtime=JSON.parse(event.data), changed=runtime.status!==state.runtime?.status||runtime.url!==state.runtime?.url||runtime.message!==state.runtime?.message;
      state.runtime={...state.runtime,...runtime};
      if(changed && runtime.status==='running')state.previewKind='runtime';
      if(changed && state.stage==='develop')workbench();
    });
    stream.addEventListener('state',async event=>{
      if(state.project?.id!==id || state.stream!==stream)return;
      try{
        const change=JSON.parse(event.data);
        const before=state.project.job;
        const queueSignature=queue=>(queue||[]).map(record=>record.id+':'+record.status).join(',');
        const queueChanged=queueSignature(state.project.queue)!==queueSignature(change.queue);
        state.project.job=change.job;state.project.queue=change.queue;
        const settled=!['queued','running','cancelling'].includes(change.job.status);
        if(change.planVersion!==state.project.versions.length || before.id!==change.job.id || before.status!==change.job.status || queueChanged || settled){
          const sequence=++refreshSequence;
          const updated=await api(`/api/projects/${id}`);
          if(state.project?.id!==id || state.stream!==stream || sequence!==refreshSequence)return;
          state.runtime=await api(`/api/projects/${id}/runtime`);
          if(state.project?.id!==id || state.stream!==stream || sequence!==refreshSequence)return;
          state.project=updated;
          state.projects=state.projects.map(project=>project.id===updated.id?{...project,job:updated.job,approved:updated.approved}:project);
          workbench();
          if(before.status!==updated.job.status && settled && updated.job.status!=='idle' && updated.job.kind!=='chat')toast(updated.job.message);
        }else updateStatus();
      }catch(error){toast(errorText(error)+'；请重新打开项目查看结果');}
    });
  }
  function submissionId(signature) {
    if(state.submission?.signature!==signature)state.submission={signature,id:crypto.randomUUID().replaceAll('-','')};
    return state.submission.id;
  }
  async function startJob(kind,note,target,buildMode) {
    if(kind==='chat'){
      const server=await api('/api/status');
      if(server.reasoningSelection!==1&&state.chatReasoning!=='high')throw new Error('后台尚未加载强度切换功能，请在任务结束后重启工作台和 Worker；当前草稿已保留');
      if(state.chatFiles.length&&server.chatFiles!==1)throw new Error('后台尚未加载文件附件功能，请在任务结束后重启工作台和 Worker；当前草稿保留');
      if(state.chatImages.length&&server.chatImageAttachments!==1)throw new Error('后台尚未加载图片消息功能，请重启工作台和 Worker 后发送；图片和文字已保留');
      if(server.assistantProtocol!==3)throw new Error('网页与后台版本不一致，请在当前任务结束后重启工作台和 Worker，再刷新页面发送；当前预览未被停止');
    }
    const sendingConversation=state.conversationId;
    const sendingImages=state.chatImages.slice(),sendingFiles=state.chatFiles.slice(),sendingContexts=state.contexts.slice();
    const route=kind==='iterate'?state.taskRoute:'business';
    const body={kind,note,target,route,...(['chat','revise','iterate'].includes(kind)?{reasoning:state.chatReasoning}:{}),...(kind==='chat'&&sendingImages.length?{images:sendingImages}:{}),...(kind==='chat'&&sendingFiles.length?{files:sendingFiles}:{}),...(kind==='chat'&&sendingContexts.length?{contexts:sendingContexts}:{}),enqueue:busy(),...(['chat','revise','iterate'].includes(kind)?{chatMessage:true,conversationId:state.conversationId,...(kind==='chat'?{autoScope:state.assistantScope}:{})}:{}),...(state.chatModel?{model:state.chatModel}:{}),...(buildMode?{buildMode}:{})};
    body.requestId=submissionId(JSON.stringify({project:state.project.id,kind,note,target,route,buildMode,images:sendingImages,files:sendingFiles,contexts:sendingContexts,model:state.chatModel,reasoning:state.chatReasoning,conversationId:state.conversationId,autoScope:state.assistantScope}));
    state.project=await api(projectUrl('jobs'),body);state.submission=null;if(['chat','revise','iterate'].includes(kind) && state.conversationId===sendingConversation && state.note===note && (kind==='chat'||state.feedbackKind===kind && state.taskRoute===route)){state.note='';state.chatImages=state.chatImages.filter(item=>!sendingImages.includes(item));state.chatFiles=state.chatFiles.filter(item=>!sendingFiles.includes(item));state.contexts=state.contexts.filter(item=>!sendingContexts.includes(item));state.selected=state.contexts.join('；').slice(0,1000)||'整个项目';saveDraft();}workbench();watch();toast(kind==='chat'?'问题已发送，回答会保存在对话中':'修改任务已保存到后台队列');
  }
  function chooseBuild() {
    if(!state.project.hasWorkspaceProgress&&!state.project.built_from&&!state.project.previewAvailable)return startJob('build',undefined,undefined,'continue');
    modal('选择开发方式',`<p>检测到已有代码或页面，请选择如何继续</p><div class="field"><label class="build-choice"><input type="radio" name="build-mode" value="continue" checked> 基于已有进度继续（推荐）</label><p class="hint">保留现有页面和功能，结合已有记录补齐未完成部分；使用新的执行任务，不保证从原模型步骤恢复</p></div><div class="field"><label class="build-choice"><input type="radio" name="build-mode" value="restart"> 重新开发</label><p class="hint">先完整备份当前工作区，再从空白工作区按已确认方案生成；备份只保存在本机，不会包含在交付包内</p></div><p id="modal-error" class="error" role="alert"></p><div class="modal-footer"><button class="btn" data-close>取消</button><button class="btn primary" id="confirm-build">开始开发</button></div>`,el=>{
      $('input[name="build-mode"]:checked',el).focus();
      $('#confirm-build',el).onclick=async()=>{const button=$('#confirm-build',el);button.disabled=true;try{await startJob('build',undefined,undefined,$('input[name="build-mode"]:checked',el).value);closeModal();}catch(error){$('#modal-error',el).textContent=errorText(error);}finally{button.disabled=false;}};
    });
  }
  function editSection(key) {
    const index=keys.indexOf(key), draft=state.sections[key], base=draft?.baseVersion??state.project.versions.length;
    modal('编辑 · '+titles[index], `<div class="field"><label for="section-editor">直接修改原文，保存后生成新版本</label><textarea class="editor" id="section-editor" maxlength="100000">${escape(draft?.text??state.project.plan[key])}</textarea></div><p class="hint">保存会取消当前方案的确认状态，需要重新确认后才能开发。编辑草稿会保存在当前浏览器。</p>${draft && base!==state.project.versions.length?'<div class="notice">草稿基于旧版本，不能直接保存覆盖当前方案。请复制草稿后，点击放弃草稿并重新编辑。</div>':''}<div class="error" id="modal-error" role="alert"></div><div class="modal-footer"><button class="btn" data-close>取消</button><button class="btn" id="discard-section">放弃草稿</button><button class="btn primary" id="save-section">保存新版本</button></div>`,el=>{
      $('#section-editor',el).oninput=()=>{state.sections[key]={text:$('#section-editor',el).value,baseVersion:base};saveDraft();};
      $('#discard-section',el).onclick=()=>{delete state.sections[key];saveDraft();editSection(key);};
      $('#save-section',el).onclick=async()=>{const button=$('#save-section',el);button.disabled=true;try{state.project=await api(projectUrl('plan'),{plan:{...state.project.plan,[key]:$('#section-editor',el).value},baseVersion:base});delete state.sections[key];saveDraft();closeModal();workbench();toast('已保存新版本，请重新确认方案');}catch(error){$('#modal-error',el).textContent=errorText(error);}finally{button.disabled=false;}};
    });
  }
  function feedbackModal(target,kind='revise') {
    state.assistantOpen=true;attachContext(target);state.assistantScope=kind==='revise'?'plan':'code';state.feedbackKind='chat';saveDraft();
    workbench();$('#feedback')?.focus();$('#feedback')?.scrollIntoView({block:'nearest'});
  }
  function conversationDirectory() {
    return `<div class="conversation-menu" id="conversation-directory" role="dialog" aria-label="对话目录" ${state.conversationMenuOpen?'':'hidden'}><div class="conversation-list">${(state.project.conversations||[{id:'legacy',title:'以前的对话'}]).slice().reverse().map(item=>`<div class="conversation-directory-row"><button class="conversation-row" data-conversation="${escape(item.id)}" ${item.id===state.conversationId?'aria-current="true"':''}><span>${escape(item.title)}</span><small>${item.created?new Date(item.created*1000).toLocaleString('zh-CN'):''}</small></button><button class="btn small" data-rename-conversation="${escape(item.id)}" aria-label="重命名 ${escape(item.title)}">重命名</button></div>`).join('')}</div></div>`;
  }
  function placeConversationMenu() {
    const menu=$('#conversation-directory'),button=$('[data-action="chat-history"]');if(!menu||!button)return;
    const anchor=button.getBoundingClientRect();const width=Math.min(330,innerWidth-32);
    menu.style.width=width+'px';menu.style.maxHeight=Math.min(380,innerHeight-32)+'px';
    const height=menu.getBoundingClientRect().height;
    menu.style.left=Math.max(16,Math.min(anchor.right-width,innerWidth-width-16))+'px';
    menu.style.top=Math.max(16,Math.min(anchor.bottom+6,innerHeight-height-16))+'px';
  }
  function closeConversationDirectory() {
    state.conversationMenuOpen=false;const menu=$('#conversation-directory');if(menu)menu.hidden=true;
    $('[data-action="chat-history"]')?.setAttribute('aria-expanded','false');
  }
  function conversationHistory() {
    state.conversationMenuOpen=!state.conversationMenuOpen;workbench();
    if(state.conversationMenuOpen)$('#conversation-directory button')?.focus();
  }
  function renameConversation(identifier) {
    const conversation=state.project.conversations?.find(item=>item.id===identifier);if(!conversation)return;
    closeConversationDirectory();
    modal('重命名对话',`<div class="field"><label for="conversation-name">对话标题</label><input id="conversation-name" maxlength="80" value="${escape(conversation.title)}"></div><div id="rename-error" class="error" role="alert"></div><div class="modal-footer"><button class="btn" data-close>取消</button><button class="btn primary" id="save-conversation-name">保存</button></div>`,el=>{
      $('#conversation-name',el).focus();
      $('#save-conversation-name',el).onclick=async()=>{const button=$('#save-conversation-name',el);button.disabled=true;try{state.project=await api(projectUrl('conversations'),{id:identifier,operation:'rename',baseTitle:conversation.title,title:$('#conversation-name',el).value});closeModal();workbench();}catch(error){$('#rename-error',el).textContent=errorText(error);}finally{button.disabled=false;}};
    });
  }
  async function newConversation() {
    stopSpeech();closeConversationDirectory();saveDraft();
    const identifier=crypto.randomUUID().replaceAll('-','');
    state.project=await api(projectUrl('conversations'),{id:identifier});
    state.conversationId=identifier;state.note='';state.selected='整个项目';state.chatImages=[];state.chatFiles=[];state.contexts=[];state.chatError='';saveDraft();workbench();
  }

  function manual() {
    modal('创建可编辑的方案', `<p class="hint">先创建四部分空白草稿，随后逐项编辑。此操作不会调用 AI。</p><div class="modal-footer"><button class="btn" data-close>取消</button><button class="btn primary" id="create-plan">创建草稿</button></div>`,el=>{
      $('#create-plan',el).onclick=async()=>{try{const plan=Object.fromEntries(keys.map((key,i)=>[key,`${titles[i]}\n\n待填写：请点击「编辑原文」完善这一部分。\n\n原始需求：\n${state.project.requirements}`]));state.project=await api(projectUrl('plan'),{plan,baseVersion:state.project.versions.length});closeModal();workbench();}catch(error){toast(errorText(error));}};
    });
  }
  function createProject() {
    if(state.importing){toast('正在提取需求文件，请稍候');return;}
    state.draft=$('#requirements')?.value || state.draft;
    if(!state.draft.trim() && !state.requirementUploads.length){toast('请填写补充需求或上传需求文档');$('#requirements')?.focus();return;}
    modal('为你的项目命名',`<div class="field"><label for="project-name">项目名称</label><input id="project-name" maxlength="100" placeholder="例如：星云客户管理系统"></div><p class="hint">将一并保存 ${state.requirementUploads.length} 份需求文档、输入框补充说明与 ${state.uploads.length} 张参考截图，并加入 AI 需求分析队列。</p><div class="error" id="modal-error" role="alert"></div><div class="modal-footer"><button class="btn" data-close>返回</button><button class="btn primary" id="create-project">创建并分析 ${icon('arrow')}</button></div>`,el=>{
      $('#create-project',el).onclick=async()=>{
        const button=$('#create-project',el);button.disabled=true;
        try{
          const name=$('#project-name',el).value;
          if(!state.creation || state.creation.name!==name)state.creation={id:crypto.randomUUID().replaceAll('-',''),name};saveIntake();
          const p=await api('/api/projects',{name,requirements:state.draft,documents:state.requirementUploads.map(item=>item.id),images:state.uploads,analyze:true,requestId:state.creation.id});
          state.projects=await api('/api/projects');state.uploads=[];state.requirementUploads=[];state.draft='';state.creation=null;saveIntake();closeModal();await openProject(p.id);
          toast(p.analysisError?'项目已保存，分析未启动：'+p.analysisError:'项目与附件已保存，需求分析已加入队列');
        }catch(error){$('#modal-error',el).textContent=errorText(error);}finally{button.disabled=false;}
      };
    });
  }
  async function download() {
    const response=await fetch(projectUrl('export'));
    if(!response.ok){const result=await response.json();throw new Error(result.error);}
    const url=URL.createObjectURL(await response.blob()); const anchor=document.createElement('a');anchor.href=url;anchor.download='harness-project-'+state.project.id.slice(0,8)+'.zip';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出源码包；部署验证请查看交付说明');
  }
  const actions={
    home:async()=>{await leaveFullscreen();state.projects=await api('/api/projects');history.replaceState(null,'','/');home();},
    projects:async()=>{await leaveFullscreen();state.projects=await api('/api/projects');home();$('#recent').scrollIntoView({behavior:'smooth'});},
    new:async()=>{await leaveFullscreen();state.projects=await api('/api/projects');home();$('#requirements').focus();},
    settings, create:createProject, manual,
    'import-requirements':()=>{if(!state.importing)$('#requirements-file')?.click();},
    analyze:()=>startJob('analyze'), build:chooseBuild,
    approve:async()=>{state.project=await api(projectUrl('approve'),{baseVersion:state.project.versions.length});workbench();toast('当前方案已确认，可到开发与预览启动任务');},
    feedback:async()=>{if(state.chatAttaching)return;stopSpeech();state.chatError='';state.speechError='';$('#chat-error').textContent='';try{await startJob('chat',$('#feedback').value,$('#target').value);}catch(error){state.chatError=errorText(error);$('#chat-error').textContent=state.chatError;}},
    'interrupt-assistant':async()=>{const job=assistantTask();if(!job)return;state.project=await api(projectUrl('cancel'),{jobId:job.id});workbench();watch();toast('正在中断当前任务，已发布预览保持运行');},
    'toggle-assistant':()=>{state.assistantOpen=!state.assistantOpen;if(!state.assistantOpen){stopSpeech();closeConversationDirectory();closeModelPicker();}workbench();if(state.assistantOpen)$('#feedback')?.focus();else $('.assistant-toggle')?.focus();},
    'chat-history':conversationHistory,
    'new-chat':newConversation,
    voice:voiceInput,
    'model-settings':()=>{const opening=!state.modelMenu;closeConversationDirectory();state.modelMenu=opening?'effort':null;workbench();if(opening)$('#chat-reasoning')?.focus({preventScroll:true});},
    'model-list':()=>{state.modelMenu='models';workbench();$('#model-picker button')?.focus({preventScroll:true});},
    'chat-upload':()=>$('#chat-attachment-input')?.click(),
    'clear-context':()=>{state.contexts=[];state.selected='整个项目';saveDraft();workbench();},
    logs:async()=>{const log=await api(projectUrl('logs'));modal('最近一次任务日志',`<p class="hint">显示日志末尾。日志可能包含需求或工具输出，请勿公开分享。</p><pre class="log">${escape(log.text)}</pre>`);},
    cancel:async()=>{state.project=await api(projectUrl('cancel'),{});workbench();toast('已保存取消请求，已有代码会保留');},
    export:download,
    'final-review':async()=>{state.project=await api(projectUrl('jobs'),{kind:'iterate',route:'business',finalReview:true,note:'交付前完整审查当前代码，不重新开发。',target:'当前系统',requestId:submissionId(JSON.stringify({project:state.project.id,finalReview:state.project.built_job}))});state.submission=null;workbench();watch();toast('完整审查已加入队列，沿用现有代码');},
    'continue-review':async()=>{state.project=await api(projectUrl('jobs'),{kind:'iterate',route:'business',reviewJobId:state.project.reviewState?.sourceJob||state.project.job.id,note:'根据上一份审查报告继续修复当前代码；保留已完成功能和已通过检查，不重新生成整个系统。',target:'审查遗留问题',requestId:submissionId(JSON.stringify({project:state.project.id,reviewJobId:state.project.reviewState?.sourceJob||state.project.job.id}))});state.submission=null;workbench();watch();toast('已加入定向修复任务，保留现有代码');},
    accept:async()=>{state.project=await api(projectUrl('accept'),{jobId:state.project.built_job});workbench();toast('最终版本已确认，可以导出交付包');},
    experience:()=>setPreviewMode('experience'),
    inspect:()=>setPreviewMode('inspect'),
    region:()=>setPreviewMode('region'),
    fullscreen:toggleFullscreen,
    'runtime-start':()=>ensureRuntime(true),
    'runtime-checks':()=>{const runtime=state.runtime,check=runtime?.preflight;modal('运行预览检查',`${state.runtimeError?`<div class="notice" role="alert">${escape(state.runtimeError)}</div>`:''}<p>${escape(runtime?.message||'尚未启动运行预览')}</p>${check?`<h3>准备检查 · ${check.ready?'通过':'需处理'}</h3>${check.checks.map(item=>`<p>${item.ok?'✓':'待处理'} ${escape(item.name)}</p>`).join('')}<p>${escape(check.detail)}</p>`:'<p>暂无检查信息，请重新打开项目。</p>'}<p class="hint">静态演示不连接后端。运行预览使用独立数据库，外部网络、定时任务及推送已关闭。</p>`);},
    'runtime-logs':async()=>{const log=await api(projectUrl('runtime-logs'));modal('运行预览日志',`<pre class="log">${escape(log.text)}</pre>`);},
    'refresh-preview':()=>{const frame=$('#preview');if(frame)frame.src=frame.src.split('&t=')[0]+(frame.src.includes('?')?'&':'?')+'t='+Date.now();else toast('尚未生成预览');},
  };
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button,a');
    if(!button || button.disabled)return;
    try{
      if(button.hasAttribute('data-close')){closeModal();return;}
      if(button.dataset.selectChatModel!==undefined){state.chatModel=button.dataset.selectChatModel;saveDraft();state.modelMenu='effort';workbench();$('#chat-reasoning')?.focus({preventScroll:true});return;}
      if(button.dataset.removeChatFile!==undefined){state.chatFiles.splice(Number(button.dataset.removeChatFile),1);saveDraft();workbench();return;}
      if(button.dataset.removeChatImage!==undefined){state.chatImages.splice(Number(button.dataset.removeChatImage),1);saveDraft();workbench();return;}
      if(button.dataset.removeChatContext!==undefined){state.contexts.splice(Number(button.dataset.removeChatContext),1);state.selected=state.contexts.join('；').slice(0,1000)||'整个项目';saveDraft();workbench();return;}
      if(button.dataset.steerMessage){const job=assistantTask();if(!job)return;button.disabled=true;try{const server=await api('/api/status');if(server.assistantSteering!==1)throw new Error('请重启工作台后使用引导，消息与预览已保留');state.project=await api(projectUrl('steer'),{jobId:job.id,messageId:button.dataset.steerMessage});workbench();watch();toast('引导已保存，当前轮次退出后继续处理');}catch(error){state.chatError=errorText(error);$('#chat-error').textContent=state.chatError;}finally{button.disabled=false;}return;}
      if(button.dataset.cancelJob){state.project=await api(projectUrl('cancel'),{jobId:button.dataset.cancelJob,...(button.classList.contains('steering-remove')?{dismissMessage:true}:{})});workbench();return;}
      if(button.dataset.reviewJob){const job=state.project.job.id===button.dataset.reviewJob?state.project.job:state.project.jobHistory.find(item=>item.id===button.dataset.reviewJob);if(job)reviewReport(job);return;}
      if(button.dataset.jobLog){const log=await api(projectUrl('logs')+'?jobId='+button.dataset.jobLog);modal('任务日志',`<pre class="log">${escape(log.text)}</pre>`);return;}
      if(button.dataset.retry){const signature=JSON.stringify({project:state.project.id,retry:button.dataset.retry});state.project=await api(projectUrl('retry'),{jobId:button.dataset.retry,requestId:submissionId(signature),enqueue:busy()});state.submission=null;workbench();watch();toast('已按当前方案重新加入队列');return;}
      if(button.dataset.project){await openProject(button.dataset.project);return;}
      if(button.dataset.renameConversation){renameConversation(button.dataset.renameConversation);return;}
      if(button.dataset.conversation){closeConversationDirectory();stopSpeech();saveDraft();state.conversationId=button.dataset.conversation;const draft=state.conversationDrafts[state.conversationId];state.note=draft?.note||'';state.selected=draft?.target||'整个项目';restoreChatAttachments(draft);state.chatError='';saveDraft();closeModal();workbench();return;}
      if(button.dataset.stage){if(button.dataset.stage!=='develop'&&state.previewExpanded)await leaveFullscreen();state.stage=button.dataset.stage;if(state.stage==='develop')state.runtimeAttempt='';saveDraft();workbench();return;}
      if(button.dataset.edit){editSection(button.dataset.edit);return;}
      if(button.dataset.section){feedbackModal(titles[keys.indexOf(button.dataset.section)]);return;}
      if(button.dataset.feedback){feedbackModal(titles[keys.indexOf(button.dataset.feedback)]);return;}
      if(button.dataset.example!==undefined){state.draft=examples[Number(button.dataset.example)].requirements;state.creation=null;saveIntake();$('#requirements').value=state.draft;$('#requirements').focus();window.scrollTo({top:0,behavior:'smooth'});toast('已填入案例需求，可继续修改并添加参考截图');return;}
      if(button.dataset.removeDocument){await api('/api/requirement-uploads/'+button.dataset.removeDocument+'/remove',{});state.requirementUploads=state.requirementUploads.filter(item=>item.id!==button.dataset.removeDocument);state.creation=null;saveIntake();$('#requirement-uploads').innerHTML=documentMarkup();return;}
      if(button.dataset.remove!==undefined){state.uploads.splice(Number(button.dataset.remove),1);state.creation=null;saveIntake();$('#uploads').innerHTML=uploadMarkup();$('#uploads').hidden=!state.uploads.length;return;}
      if(button.dataset.version){
        const v=state.project.versions.find(v=>v.number===Number(button.dataset.version));
        const previous=state.project.versions.find(version=>version.number===v.number-1);
        modal('方案 V'+v.number,`${keys.map((key,i)=>`<h3>${titles[i]}</h3><div class="document-content" data-document>${escape(v.plan[key])}</div>${previous && previous.plan[key]!==v.plan[key]?`<details><summary>对比上一版 V${previous.number}</summary><div class="document-content" data-document>${escape(previous.plan[key])}</div></details>`:''}`).join('')}<div class="modal-footer"><button class="btn" data-close>关闭</button><button class="btn primary" id="restore-version" ${disabled(busy())}>恢复为新版本</button></div>`,el=>{$('#restore-version',el).onclick=async()=>{try{state.project=await api(projectUrl('plan'),{plan:v.plan,baseVersion:state.project.versions.length});closeModal();workbench();toast('已恢复为新版本，旧记录继续保留');}catch(error){toast(errorText(error));}};});return;
      }
      if(button.dataset.action && actions[button.dataset.action]){button.disabled=true;try{await actions[button.dataset.action]();}finally{button.disabled=false;}}
    }catch(error){toast(errorText(error));}
  });
  document.addEventListener('click',event=>{if(state.conversationMenuOpen&&!event.target.closest?.('#conversation-directory,[data-action="chat-history"]'))closeConversationDirectory();});
  document.addEventListener('click',event=>{if(state.modelMenu&&!event.target.closest?.('#model-picker,[data-action="model-settings"]'))closeModelPicker();});
  window.addEventListener('resize',closeModelPicker);
  document.addEventListener('scroll',event=>{if(state.modelMenu&&!event.target.closest?.('#model-picker'))placeModelPicker();},true);
  window.addEventListener('resize',closeConversationDirectory);
  document.addEventListener('scroll',event=>{if(state.conversationMenuOpen&&!event.target.closest?.('#conversation-directory'))closeConversationDirectory();},true);
  document.addEventListener('input',event=>{if(event.target.id==='chat-reasoning'){state.chatReasoning=reasoningLevels[Number(event.target.value)];event.target.setAttribute('aria-valuetext',state.chatReasoning);$('#reasoning-button-label').textContent=state.chatReasoning;$('#reasoning-menu-label').textContent=state.chatReasoning;$('.reasoning-track').style.setProperty('--effort-fill',Number(event.target.value)*25+'%');saveDraft();return;}if(event.target.id==='requirements'){state.draft=event.target.value;state.creation=null;saveIntake();}if(['feedback','modal-note'].includes(event.target.id)){state.note=event.target.value;saveDraft();}if(event.target.id==='target'){state.selected=event.target.value;saveDraft();}});
  document.addEventListener('change',async event=>{
    if(event.target.id==='chat-attachment-input'){await addChatFiles(Array.from(event.target.files));event.target.value='';return;}
    if(event.target.id==='chat-model'){state.chatModel=event.target.value;saveDraft();workbench();return;}
    if(event.target.id==='requirements-file'){await importRequirements(event.target);return;}
    if(event.target.id!=='image-input')return;
    try{
      const files=Array.from(event.target.files);
      if(state.uploads.length+files.length>4)throw new Error('最多添加 4 张参考截图');
      const uploads=[];
      for(const file of files){
        if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>3*1024*1024)throw new Error('仅支持 PNG、JPEG、WebP，每张不超过 3 MB');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('无法读取截图，请重新选择'));reader.readAsDataURL(file);});uploads.push({name:file.name,data});
      }
      state.uploads.push(...uploads);state.creation=null;saveIntake();$('#uploads').innerHTML=uploadMarkup();$('#uploads').hidden=false;
    }catch(error){toast(errorText(error));}finally{event.target.value='';}
  });
  async function importRequirements(input) {
    if(state.importing)return;
    const files=Array.from(input.files);if(!files.length)return;
    const status=$('#import-status');state.importing=true;input.disabled=true;
    const create=$('[data-action="create"]');if(create)create.disabled=true;
    const added=[];let committed=false;
    if(status)status.textContent='正在暂存原文件并整理正文、图片…';
    try{
      if(state.requirementUploads.length+files.length>4)throw new Error('最多暂存 4 份需求文档，请先移除不用的附件');
      for(const file of files)if(!/\.(docx|md|markdown|txt)$/i.test(file.name) || file.size>30*1024*1024)throw new Error('支持 .docx、.md、.markdown、.txt，每个不超过 30 MB；旧 .doc 请先另存为 .docx');
      for(const file of files){
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('无法读取文件，请重新选择'));reader.readAsDataURL(file);});
        const result=await api('/api/import-requirements',{name:file.name,data});
        if(typeof result.id!=='string' || !/^[a-f0-9]{32}$/.test(result.id) || !Number.isFinite(result.expiresAt))throw new Error('服务尚未启用附件缓存，请重启 Studio 服务后重新上传');
        added.push({id:result.id,name:result.name,size:result.size,expiresAt:result.expiresAt,imageCount:result.imageCount,warnings:result.warnings});
      }
      state.requirementUploads.push(...added);state.creation=null;saveIntake();committed=true;
      const host=$('#requirement-uploads');if(host)host.innerHTML=documentMarkup();
      if(status)status.textContent=state.intakeError||'附件已暂存；输入框可填写补充说明，点击开始我的项目后再统一分析。';
      toast('已暂存 '+files.length+' 份文档，尚未调用 AI');
    }catch(error){
      if(!committed)for(const item of added){try{await api('/api/requirement-uploads/'+item.id+'/remove',{});}catch(cleanupError){state.intakeError='部分临时附件未清理，将在过期后移除。';}}
      if(status)status.textContent=errorText(error)+'；已有附件与补充文字保留。';toast(errorText(error));
    }finally{state.importing=false;input.disabled=false;input.value='';if(create)create.disabled=false;}
  }
  function previewHelp() {
    return '快捷键：⌥ / Alt + Shift + A 框选提问 · Esc 取消';
  }
  function syncFullscreen() {
    const pane=$('#preview-pane');if(!pane)return;
    pane.classList.toggle('preview-expanded',state.previewExpanded);
    const chrome=$('#preview-chrome');if(chrome)chrome.hidden=state.previewExpanded;
    let controls=$('#fullscreen-controls');
    if(state.previewExpanded && !controls){
      controls=document.createElement('div');controls.id='fullscreen-controls';controls.className='fullscreen-controls';
      controls.innerHTML='<details><summary>修改页面</summary><div class="fullscreen-modify"><button data-action="experience">体验模式</button><button data-action="inspect">点选提问</button><button data-action="region">框选提问</button><p>⌥ / Alt + Shift + A 框选；Esc 取消</p></div></details><button data-action="fullscreen">退出全屏</button>';
      pane.append(controls);
    }
    if(controls){controls.hidden=!state.previewExpanded;for(const action of ['experience','inspect','region'])controls.querySelector(`[data-action="${action}"]`)?.setAttribute('aria-pressed',String(state.previewMode===action));}

    document.body.classList.toggle('preview-open',state.previewExpanded);
    const dialog=$('#modal');const parent=state.previewExpanded?pane:document.body;
    if(dialog.parentElement!==parent){const open=dialog.open;if(open)dialog.close();parent.append(dialog);if(open)dialog.showModal();}
    const notification=$('#toast');if(notification.parentElement!==parent)parent.append(notification);
    for(const button of document.querySelectorAll('[data-action="fullscreen"]'))button.textContent=state.previewExpanded?'退出全屏':'全屏预览';
  }
  async function leaveFullscreen() {
    if(document.fullscreenElement && document.exitFullscreen)await document.exitFullscreen();
    state.previewExpanded=false;syncFullscreen();
  }
  async function toggleFullscreen() {
    if(state.previewExpanded){await leaveFullscreen();return;}
    const pane=$('#preview-pane');if(!$('#preview'))return;
    state.previewExpanded=true;syncFullscreen();
    if(pane.requestFullscreen){try{await pane.requestFullscreen();}catch(error){toast('浏览器未允许全屏，已展开为窗口预览。');}}
  }
  document.addEventListener('fullscreenchange',()=>{
    if(!document.fullscreenElement && state.previewExpanded){state.previewExpanded=false;syncFullscreen();}
  });
  function setPreviewMode(mode) {
    state.previewMode=mode;
    const live=state.previewKind==='runtime' && state.runtime?.status==='running';
    $('#preview')?.contentWindow.postMessage({type:'studio-mode',channel:live?state.runtime.channel:state.previewChannel,inspect:mode!=='experience',mode},live?new URL(state.runtime.url).origin:'*');
    for(const action of ['experience','inspect','region'])for(const button of document.querySelectorAll(`[data-action="${action}"]`))button.setAttribute('aria-pressed',String(mode===action));
    const menu=$('#fullscreen-controls details');if(menu)menu.open=false;
    const help=$('#preview-help');if(help)help.textContent=previewHelp();
  }
  window.addEventListener('message',async event=>{
    const live=state.previewKind==='runtime' && state.runtime?.status==='running';
    if(event.source!==$('#preview')?.contentWindow || event.origin!==(live?new URL(state.runtime.url).origin:'null') || event.data?.channel!==(live?state.runtime.channel:state.previewChannel))return;
    if(event.data.type==='studio-ready')setPreviewMode(state.previewMode);
    if(event.data.type==='studio-mode' && !event.data.inspect && state.previewMode!=='experience')setPreviewMode('experience');
    if(event.data.type==='studio-shortcut' && state.stage==='develop')setPreviewMode('region');
    if(event.data.type==='studio-select' && state.previewMode!=='experience' && typeof event.data.target==='string'){
      const context=[event.data.target,event.data.selector,event.data.path,event.data.region].filter(value=>typeof value==='string').join(' | ').slice(0,1000);
      setPreviewMode('experience');state.assistantOpen=true;attachContext(context);state.assistantScope='code';state.feedbackKind='chat';state.taskRoute='business';saveDraft();if(state.previewExpanded)await leaveFullscreen();workbench();$('#feedback')?.focus();$('#feedback')?.scrollIntoView({block:'nearest'});
    }
  });
  window.addEventListener('keydown',event=>{
    if(event.target.id==='feedback' && event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();$('#chat-error').textContent='';Promise.resolve(actions.feedback()).catch(error=>{$('#chat-error').textContent=errorText(error);});return;}
    if(event.key==='Escape'){
      if(state.modelMenu){closeModelPicker();$('[data-action="model-settings"]')?.focus();}
      if(state.conversationMenuOpen){closeConversationDirectory();$('[data-action="chat-history"]')?.focus();}
      if(state.previewMode!=='experience')setPreviewMode('experience');
      else if(state.previewExpanded && !$('#modal').open)void leaveFullscreen();
    }
    if(event.altKey && event.shiftKey && event.code==='KeyA' && !event.repeat && !event.isComposing && !event.target.closest?.('input,textarea,select,[contenteditable]') && !$('#modal').open && state.stage==='develop' && $('#preview')){event.preventDefault();setPreviewMode('region');$('#preview').focus();}
  });
  $('#modal').addEventListener('click',event=>{if(event.target===$('#modal')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});
  $('#modal').addEventListener('close',()=>{if($('#feedback')){$('#feedback').value=state.note;$('#target').value=state.selected;}});
  window.addEventListener('beforeunload',stopWatching);
  async function init(){
    restoreIntake();
    try{[state.status,state.projects]=await Promise.all([api('/api/status'),api('/api/projects')]);const match=location.hash.match(/^#project\/([a-f0-9]{32})$/);if(match)await openProject(match[1]);else home();}
    catch(error){layout(`<div class="home"><div class="notice">${escape(errorText(error))}。请确认本地服务正在运行，然后刷新页面。</div></div>`);}
  }
  const retryClock=setInterval(()=>{
    for(const el of document.querySelectorAll('[data-retry-at]'))el.textContent=String(Math.max(0,Math.ceil(Number(el.dataset.retryAt)-Date.now()/1000)));
  },1000);
  window.addEventListener('beforeunload',()=>clearInterval(retryClock));
  init();
})();
