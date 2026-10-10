
(() => {
  'use strict';
  const token = '__TOKEN__';
  const el = id => document.getElementById(id);
  const capture = el('capture'), start = el('start'), stop = el('stop');
  const preview = el('preview'), wrap = el('previewwrap'), selection = el('selection');
  const resetZoom=el('resetzoom'), zoomValue=el('zoomvalue');
  const speed = el('speed'), limit = el('limit');
  let plan = null, running = false, busy = false, drag = null;
  let zoom=1, panX=0, panY=0;

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
  function showPlan(next) {
    plan=next;
    el('count').textContent=next.count+' quadradinhos detectados';
    el('pickerstatus').textContent=next.picker
      ? 'Color picker localizado em ('+next.picker[0]+', '+next.picker[1]+'). A posição será conferida durante a pintura.'
      : 'Color picker não localizado nesta captura. O modo Cor específica continua disponível.';
    const remaining=next.count-next.cursor;
    el('available').textContent=remaining+' restantes de '+next.count;
    limit.max=Math.max(1,remaining);
    limit.value=Math.max(1,remaining);
    preview.onload=()=>{ preview.hidden=false; el('placeholder').hidden=true; wrap.classList.add('ready'); resetView(); };
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
    message('Ativando o Wplace e capturando a tela...');
    showPlan(await api('/api/capture',{}));
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
    if (zoom>1 && !event.shiftKey) {
      drag={kind:'pan',clientX:event.clientX,clientY:event.clientY,panX,panY};
      wrap.classList.add('panning');
    } else {
      drag={kind:'select',start:imagePoint(event)};
      drawDrag(drag.start);
    }
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
    task(async()=>showPlan(await api('/api/roi',{roi})));
  });
  wrap.addEventListener('pointercancel',()=>{drag=null;selection.style.display='none';wrap.classList.remove('panning');});
  window.addEventListener('resize',()=>{if (plan && !preview.hidden) resetView();});
  setInterval(async()=>{
    if (!running) return;
    try { updateStatus(await api('/api/status')); } catch (error) { message(error.message,'error'); }
  },350);
  updateSpeed(); controls();
  api('/api/plan').then(data=>{ if (data.ready) showPlan(data); }).catch(()=>{});
})()
