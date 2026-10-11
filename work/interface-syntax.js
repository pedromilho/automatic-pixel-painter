(() => {
  'use strict';
  const token = '__TOKEN__';
  const pageId = '__PAGE_ID__';
  const el = id => document.getElementById(id);
  const capture = el('capture'), start = el('start'), stop = el('stop');
  const preview = el('preview'), wrap = el('previewwrap'), selection = el('selection'), roiDraft=el('roiDraft');
  const resetZoom=el('resetzoom'), zoomValue=el('zoomvalue');
  const speed = el('speed'), limit = el('limit');
  const roiX=el('roiX'), roiY=el('roiY'), roiXValue=el('roiXValue'), roiYValue=el('roiYValue');
  const roiPosX=el('roiPosX'), roiPosY=el('roiPosY');
  const roiPosXValue=el('roiPosXValue'), roiPosYValue=el('roiPosYValue');
  const roiReset=el('roiReset'), boundsKey='pixel-roi-bounds';
  let plan = null, running = false, busy = false, drag = null;
  let zoom=1, panX=0, panY=0;

  window.addEventListener('pagehide',()=>{
    navigator.sendBeacon('/api/ui-close',new Blob(
      [JSON.stringify({token,page_id:pageId})],{type:'application/json'}));
  });

  async function api(path, body) {
    const options = body === undefined ? {} : {
      method:'POST', headers:{'Content-Type':'application/json','X-Local-Token':token},
      body:JSON.stringify(body)
    };
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Falha na comunicação local');
    return data;
  }
  function message(value, kind='') {
    const box = el('status'); box.textContent=value; box.className='status'+(kind ? ' '+kind : '');
  }
  function controls() {
    capture.disabled=busy || running;
    const mode=document.querySelector('input[name=mode]:checked').value;
    start.disabled=busy || running || !plan || plan.cursor>=plan.count || (mode==='per_pixel' && !plan.picker);
    stop.disabled=!running;
    limit.disabled=busy || running || !plan || plan.cursor>=plan.count;
    roiX.disabled=busy || running || !plan || preview.hidden;
    roiY.disabled=busy || running || !plan || preview.hidden;
    roiPosX.disabled=busy || running || !plan || preview.hidden;
    roiPosY.disabled=busy || running || !plan || preview.hidden;
    roiReset.disabled=busy || running || !plan || preview.hidden;
    document.querySelectorAll('input[name=mode]').forEach(input => input.disabled=running);
  }
  function updateSpeed() {
    const mode = document.querySelector('input[name=mode]:checked').value;
    el('speedvalue').textContent=speed.value+' / 10';
    el('speedhelp').textContent=mode==='specific'
      ? 'Cor específica: ajusta a pausa entre cliques. No nível 10, a pausa programada é de cerca de 0,04 s.'
      : 'Cor por cor: ajusta as pausas do color picker, coleta e pintura.';
  }
  function clampPan() {
    const excessX=Math.max(0,preview.offsetWidth*zoom-wrap.clientWidth);
    const excessY=Math.max(0,preview.offsetHeight*zoom-wrap.clientHeight);
    panX=Math.max(-excessX,Math.min(0,panX));
    panY=Math.max(-excessY,Math.min(0,panY));
  }
  function applyView() {
    preview.style.transform=`translate(${panX}px, ${panY}px) scale(${zoom})`;
    zoomValue.textContent=Math.round(zoom*100)+'%';
    resetZoom.disabled=zoom<=1;
    wrap.classList.toggle('zoomed',zoom>1);
    if (roiDraft.style.display==='block') drawRoiDraft();
  }
  function resetView() {
    zoom=1; panX=0; panY=0;
    applyView();
  }
  function zoomAt(clientX,clientY,nextZoom) {
    const box=wrap.getBoundingClientRect();
    const pointerX=clientX-box.left-wrap.clientLeft;
    const pointerY=clientY-box.top-wrap.clientTop;
    const imageX=(pointerX-panX)/zoom;
    const imageY=(pointerY-panY)/zoom;
    zoom=nextZoom;
    panX=pointerX-imageX*zoom;
    panY=pointerY-imageY*zoom;
    if (zoom===1) { panX=0; panY=0; }
    clampPan(); applyView();
  }
  function syncRoiControls() {
    if (!plan || !plan.roi) return;
    const width=plan.roi[2]-plan.roi[0], height=plan.roi[3]-plan.roi[1];
    roiX.min=10; roiX.max=plan.width-plan.roi[0]; roiX.value=width;
    roiY.min=10; roiY.max=plan.max_y-plan.roi[1]; roiY.value=height;
    roiPosX.min=0; roiPosX.max=plan.width-width; roiPosX.value=plan.roi[0];
    roiPosY.min=0; roiPosY.max=plan.max_y-height; roiPosY.value=plan.roi[1];
    updateRoiValues();
  }
  function updateRoiValues() {
    roiXValue.textContent=roiX.value+' px';
    roiYValue.textContent=roiY.value+' px';
    roiPosXValue.textContent=roiPosX.value+' px';
    roiPosYValue.textContent=roiPosY.value+' px';
  }
  function savedBounds() {
    try {
      const value=JSON.parse(localStorage.getItem(boundsKey));
      if (!Array.isArray(value) || ![2,4].includes(value.length) ||
          !value.every(item=>Number.isFinite(item) && item>=0 && item<=1)) return null;
      if (value.length===4 && (value[0]>=value[2] || value[1]>=value[3])) return null;
      return value;
    } catch { return null; }
  }
  function drawRoiDraft() {
    if (!plan || preview.hidden) return;
    const image=preview.getBoundingClientRect(), box=wrap.getBoundingClientRect();
    const x1=Number(roiPosX.value), y1=Number(roiPosY.value);
    const width=Number(roiX.value), height=Number(roiY.value);
    roiDraft.style.left=(image.left-box.left+x1*image.width/plan.width)+'px';
    roiDraft.style.top=(image.top-box.top+y1*image.height/plan.height)+'px';
    roiDraft.style.width=(width*image.width/plan.width)+'px';
    roiDraft.style.height=(height*image.height/plan.height)+'px';
  }
  function showPlan(next, keepZoom=false) {
    plan=next;
    roiDraft.style.display='none';
    syncRoiControls();
    el('count').textContent=next.count+' quadradinhos detectados';
    el('pickerstatus').textContent=next.picker
      ? 'Color picker localizado em ('+next.picker[0]+', '+next.picker[1]+'). A posição será conferida durante a pintura.'
      : 'Color picker não localizado nesta captura. O modo Cor específica continua disponível.';
    const remaining=next.count-next.cursor;
    el('available').textContent=remaining+' restantes de '+next.count;
    limit.max=Math.max(1,remaining);
    limit.value=Math.max(1,remaining);
    preview.onload=()=>{ preview.hidden=false; el('placeholder').hidden=true; wrap.classList.add('ready'); if (keepZoom) {clampPan();applyView();} else resetView(); controls(); };
    preview.src='/api/preview?v='+next.version;
    message(next.message,next.count ? 'success' : 'error');
    controls();
  }
  function updateStatus(data) {
    running=data.running;
    if (plan) {
      plan.cursor=data.cursor;
      el('available').textContent=data.remaining+' restantes de '+plan.count;
      limit.max=Math.max(1,data.remaining);
      if (!data.running) limit.value=Math.max(1,data.remaining);
    }
    el('bar').style.width=(data.total ? 100*data.completed/data.total : 0)+'%';
    el('progresslabel').textContent=data.completed+' / '+data.total;
    if (data.message) message(data.message, !data.running && data.message.startsWith('Pintura interrompida') ? 'error' : '');
    controls();
  }
  async function task(fn) {
    busy=true; controls();
    try { await fn(); }
    catch (error) { message(error.message,'error'); }
    finally { busy=false; controls(); }
  }
  capture.addEventListener('click',()=>task(async()=>{
    message('Ativando o mapa e capturando a tela...');
    showPlan(await api('/api/capture',{bounds:savedBounds()}));
  }));
  start.addEventListener('click',()=>task(async()=>{
    const mode=document.querySelector('input[name=mode]:checked').value;
    const requested=Number(limit.value);
    const remaining=plan.count-plan.cursor;
    if (!Number.isInteger(requested) || requested<1 || requested>remaining) throw new Error('Escolha entre 1 e '+remaining+' pixels.');
    updateStatus(await api('/api/start',{mode,speed:Number(speed.value),limit:requested,version:plan.version}));
  }));
  stop.addEventListener('click',()=>task(async()=>updateStatus(await api('/api/stop',{}))));
  resetZoom.addEventListener('click',resetView);
  speed.addEventListener('input',updateSpeed);
  document.querySelectorAll('input[name=mode]').forEach(input=>input.addEventListener('change',()=>{updateSpeed();controls();}));
  for (const slider of [roiX,roiY,roiPosX,roiPosY]) {
    slider.addEventListener('input',()=>{updateRoiValues();roiDraft.style.display='block';drawRoiDraft();});
    slider.addEventListener('change',()=>{
      if (!plan) return;
      const x1=Number(roiPosX.value), y1=Number(roiPosY.value);
      const roi=[x1,y1,x1+Number(roiX.value),y1+Number(roiY.value)];
      if (roi.every((value,index)=>value===plan.roi[index])) {roiDraft.style.display='none';return;}
      task(async()=>{
        try {
          showPlan(await api('/api/roi',{roi}),true);
          localStorage.setItem(boundsKey,JSON.stringify([
            plan.roi[0]/plan.width,plan.roi[1]/plan.max_y,
            plan.roi[2]/plan.width,plan.roi[3]/plan.max_y
          ]));
        }
        finally {roiDraft.style.display='none';syncRoiControls();}
      });
    });
  }
  roiReset.addEventListener('click',()=>task(async()=>{
    showPlan(await api('/api/roi',{roi:plan.auto_roi}),true);
    localStorage.removeItem(boundsKey);
  }));

  function imagePoint(event) {
    const rect=preview.getBoundingClientRect();
    const x=Math.max(0,Math.min(plan.width,Math.round((event.clientX-rect.left)*plan.width/rect.width)));
    const y=Math.max(0,Math.min(plan.height,Math.round((event.clientY-rect.top)*plan.height/rect.height)));
    return {x,y};
  }
  function drawDrag(point) {
    const rect=preview.getBoundingClientRect(), box=wrap.getBoundingClientRect();
    const x1=Math.min(drag.start.x,point.x), x2=Math.max(drag.start.x,point.x);
    const y1=Math.min(drag.start.y,point.y), y2=Math.max(drag.start.y,point.y);
    selection.style.display='block';
    selection.style.left=(rect.left-box.left+x1*rect.width/plan.width)+'px';
    selection.style.top=(rect.top-box.top+y1*rect.height/plan.height)+'px';
    selection.style.width=((x2-x1)*rect.width/plan.width)+'px';
    selection.style.height=((y2-y1)*rect.height/plan.height)+'px';
  }
  wrap.addEventListener('wheel',event=>{
    if (!plan || preview.hidden) return;
    event.preventDefault();
    let next=Math.max(1,Math.min(6,zoom*Math.exp(-event.deltaY*0.0015)));
    if (next<1.015) next=1;
    zoomAt(event.clientX,event.clientY,next);
  },{passive:false});
  wrap.addEventListener('pointerdown',event=>{
    if (event.button!==0 || !plan || running || busy || preview.hidden) return;
    if (event.shiftKey) {
      drag={kind:'select',start:imagePoint(event)};
      drawDrag(drag.start);
    } else if (zoom>1) {
      drag={kind:'pan',clientX:event.clientX,clientY:event.clientY,panX,panY};
      wrap.classList.add('panning');
    } else return;
    wrap.setPointerCapture(event.pointerId);
  });
  wrap.addEventListener('pointermove',event=>{
    if (!drag) return;
    if (drag.kind==='pan') {
      panX=drag.panX+event.clientX-drag.clientX;
      panY=drag.panY+event.clientY-drag.clientY;
      clampPan(); applyView();
    } else drawDrag(imagePoint(event));
  });
  wrap.addEventListener('pointerup',event=>{
    if (!drag) return;
    const current=drag; drag=null; wrap.classList.remove('panning');
    if (current.kind==='pan') return;
    const end=imagePoint(event), begin=current.start; selection.style.display='none';
    const roi=[Math.min(begin.x,end.x),Math.min(begin.y,end.y),Math.max(begin.x,end.x),Math.max(begin.y,end.y)];
    if (roi[2]-roi[0]<10 || roi[3]-roi[1]<10) return;
    task(async()=>showPlan(await api('/api/roi',{roi}),true));
  });
  wrap.addEventListener('pointercancel',()=>{drag=null;selection.style.display='none';wrap.classList.remove('panning');});
  window.addEventListener('resize',()=>{if (plan && !preview.hidden) {clampPan();applyView();}});
  setInterval(async()=>{
    if (!running) return;
    try { updateStatus(await api('/api/status')); } catch (error) { message(error.message,'error'); }
  },350);
  updateSpeed(); controls();
  api('/api/plan').then(data=>{ if (data.ready) showPlan(data); }).catch(()=>{});
})()
