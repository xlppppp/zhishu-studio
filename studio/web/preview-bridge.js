/** Opt-in element/region inspection; experience mode preserves application events. */
(() => {
  'use strict';
  const config=window.__STUDIO_BRIDGE__;
  if(!config || window.parent===window)return;
  let mode='experience',overlay,hovered,drag,suppressClick=false;
  const send=(type,extra={})=>parent.postMessage({type,channel:config.channel,...extra},config.parentOrigin);
  const clear=()=>{if(overlay)overlay.remove();overlay=null;hovered=null;drag=null;};
  const setMode=value=>{mode=value;clear();send('studio-mode',{inspect:mode!=='experience',mode});};
  const describe=element=>{
    const path=[];
    for(let node=element;node && node.nodeType===1 && path.length<6;node=node.parentElement){
      if(node.id){path.unshift('#'+CSS.escape(node.id));break;}
      const siblings=node.parentElement?Array.from(node.parentElement.children).filter(item=>item.tagName===node.tagName):[node];
      path.unshift(node.tagName.toLowerCase()+(siblings.length>1?`:nth-of-type(${siblings.indexOf(node)+1})`:''));
    }
    return {target:(element.tagName.toLowerCase()+(element.id?'#'+element.id:'')+' '+(element.getAttribute('aria-label')||element.innerText||element.textContent||'').trim().slice(0,150)).slice(0,250),selector:path.join(' > '),path:location.pathname+location.search+location.hash};
  };
  const draw=rect=>{
    if(!overlay){overlay=document.createElement('div');overlay.setAttribute('aria-hidden','true');overlay.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;border:2px solid #6958dd;background:rgba(105,88,221,.10);border-radius:4px;box-sizing:border-box';document.documentElement.append(overlay);}
    Object.assign(overlay.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});
  };
  const highlight=element=>{if(!element || element===document.documentElement || element===overlay)return;hovered=element;draw(element.getBoundingClientRect());};
  const rectangle=event=>{
    const x=Math.max(0,Math.min(innerWidth,event.clientX)),y=Math.max(0,Math.min(innerHeight,event.clientY));
    return {left:Math.min(drag.x,x),top:Math.min(drag.y,y),width:Math.abs(x-drag.x),height:Math.abs(y-drag.y)};
  };
  const selectRegion=rect=>{
    const points=[[rect.left+rect.width/2,rect.top+rect.height/2],[rect.left+1,rect.top+1],[rect.left+rect.width-1,rect.top+rect.height-1]];
    const elements=[...new Set(points.map(([x,y])=>document.elementFromPoint(x,y)).filter(element=>element && element!==overlay && element!==document.documentElement))];
    const descriptions=elements.map(describe);
    send('studio-select',{target:'框选区域：'+descriptions.map(item=>item.target).join('；').slice(0,400),selector:descriptions.map(item=>item.selector).join('；').slice(0,300),path:location.pathname+location.search+location.hash,region:JSON.stringify({x:Math.round(rect.left),y:Math.round(rect.top),width:Math.round(rect.width),height:Math.round(rect.height),viewportWidth:innerWidth,viewportHeight:innerHeight,scrollX,scrollY})});
  };
  addEventListener('message',event=>{
    if(event.source!==parent || event.origin!==config.parentOrigin || event.data?.channel!==config.channel || event.data.type!=='studio-mode')return;
    setMode(event.data.mode==='region'?'region':event.data.inspect===true?'inspect':'experience');
  });
  addEventListener('pointermove',event=>{
    if(mode==='region' && drag){event.preventDefault();event.stopImmediatePropagation();draw(rectangle(event));}
    else if(mode==='inspect' && event.target instanceof Element)highlight(event.target);
  },{capture:true,passive:false});
  addEventListener('scroll',()=>{if(mode==='inspect' && hovered)highlight(hovered);},true);
  addEventListener('resize',()=>{if(mode==='inspect' && hovered)highlight(hovered);else if(mode==='region')clear();});
  for(const type of ['pointerdown','pointerup','pointercancel','mousedown','mouseup','touchstart','touchend','click','dblclick','submit','dragstart']){
    addEventListener(type,event=>{
      if(type==='pointerdown' && mode==='experience')suppressClick=false;
      if(type==='click' && suppressClick){suppressClick=false;event.preventDefault();event.stopImmediatePropagation();return;}
      if(mode==='experience')return;
      event.preventDefault();event.stopImmediatePropagation();
      if(mode==='region'){
        if(type==='pointerdown' && event.isPrimary!==false && (event.button===0 || event.button===undefined)){
          drag={x:event.clientX,y:event.clientY};draw({left:drag.x,top:drag.y,width:0,height:0});
          document.documentElement.setPointerCapture?.(event.pointerId);
        }
        if(type==='pointerup' && drag){const rect=rectangle(event);drag=null;if(rect.width>=4 && rect.height>=4){suppressClick=true;selectRegion(rect);}else clear();}
        if(type==='pointercancel')clear();
      }else if(type==='click' && event.target instanceof Element){highlight(event.target);send('studio-select',describe(event.target));}
    },{capture:true,passive:false});
  }
  addEventListener('keydown',event=>{
    if(event.altKey && event.shiftKey && event.code==='KeyA' && !event.repeat && !event.isComposing && !event.target.closest?.('input,textarea,select,[contenteditable]')){
      event.preventDefault();event.stopImmediatePropagation();setMode('region');send('studio-shortcut');return;
    }
    if(mode==='experience')return;
    if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();setMode('experience');}
    else if(mode==='inspect' && (event.key==='Enter' || event.key===' ')){
      event.preventDefault();event.stopImmediatePropagation();if(event.target instanceof Element)send('studio-select',describe(event.target));
    }
  },true);
  send('studio-ready');
})();
