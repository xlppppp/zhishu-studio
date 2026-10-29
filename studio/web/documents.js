/** Sanitize HTML/legacy Markdown and render bounded Mermaid diagrams locally. */
(() => {
  'use strict';
  let diagramLibrary;
  let sequence=0;
  function loadDiagrams() {
    if(!diagramLibrary)diagramLibrary=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src='/lib/mermaid.js';
      script.onload=()=>{window.mermaid.initialize({startOnLoad:false,securityLevel:'strict',htmlLabels:false,suppressErrorRendering:true,maxTextSize:20000,maxEdges:200,flowchart:{htmlLabels:false},theme:'neutral'});resolve(window.mermaid);};
      script.onerror=()=>{script.remove();diagramLibrary=null;reject(new Error('图表库加载失败，请刷新页面重试'));};document.head.append(script);
    });
    return diagramLibrary;
  }
  function content(source) {
    const parsed=window.marked.parse(source,{gfm:true,breaks:false});
    const fragment=window.DOMPurify.sanitize(parsed,{RETURN_DOM_FRAGMENT:true,ALLOW_DATA_ATTR:false,ALLOW_ARIA_ATTR:false,
      ALLOWED_TAGS:['h1','h2','h3','h4','h5','h6','p','br','hr','strong','em','b','i','s','ul','ol','li','blockquote','pre','code','table','thead','tbody','tr','th','td','a','section','article','div','span','details','summary'],ALLOWED_ATTR:['href','title','class','colspan','rowspan']});
    for(const element of fragment.querySelectorAll('[class]')){
      const diagram=(element.matches('pre.mermaid') || element.matches('code.language-mermaid'));
      element.removeAttribute('class');if(diagram)element.className='mermaid-source';
    }
    for(const link of fragment.querySelectorAll('a')){
      const href=link.getAttribute('href')||'';
      if(!/^https?:\/\//i.test(href)){link.removeAttribute('href');continue;}
      link.target='_blank';link.rel='noopener noreferrer';
    }
    return fragment;
  }
  async function diagrams(container) {
    for(const code of container.querySelectorAll('.mermaid-source')){
      if(!code.isConnected)continue;
      const source=code.textContent;
      const host=document.createElement('figure');host.className='document-diagram';
      const status=document.createElement('figcaption');status.setAttribute('role','status');status.textContent='正在绘制图表…';
      const drawing=document.createElement('div');drawing.className='diagram-drawing';
      const details=document.createElement('details'),summary=document.createElement('summary'),raw=document.createElement('pre');summary.textContent='图表原文';raw.textContent=source;details.append(summary,raw);host.append(status,drawing,details);
      const replaced=code.parentElement?.tagName==='PRE'?code.parentElement:code;replaced.replaceWith(host);
      try{
        if(source.length>20000 || /%%\s*\{|^\s*---/.test(source))throw new Error('图表过大或包含不支持的配置，请编辑图表原文');
        const mermaid=await loadDiagrams();if(!host.isConnected)return;
        const result=await mermaid.render('studio-diagram-'+(++sequence),source);
        if(!host.isConnected)return;
        drawing.innerHTML=window.DOMPurify.sanitize(result.svg,{USE_PROFILES:{svg:true,svgFilters:true},FORBID_TAGS:['foreignObject','a'],FORBID_ATTR:['href','xlink:href']});
        drawing.querySelector('svg')?.setAttribute('aria-label','方案图表');status.textContent='';
      }catch(error){if(host.isConnected){status.textContent='图表暂时无法绘制，请查看原文并修改语法。';status.className='notice';details.open=true;}}
    }
  }
  window.StudioDocuments={
    render(root=document){
      for(const element of root.querySelectorAll('[data-document]')){
        if(element.dataset.rendered)continue;
        const source=element.textContent;element.dataset.rendered='true';
        try{element.replaceChildren(content(source));void diagrams(element);}
        catch(error){element.textContent=source;const notice=document.createElement('p');notice.className='notice';notice.textContent='文档渲染失败，以下显示原文；请刷新或编辑原文。';element.prepend(notice);}
      }
    }
  };
})();
