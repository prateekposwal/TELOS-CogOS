// TELOS Brain Visualization Module — Neural Orbit, Pipeline Flow, Root System

// ─── 3-Mode Brain Visualization (single rAF loop) ───
// Pipeline phase names at module scope: the drawing IIFE and the click
// handler both need them (the handler cannot see the IIFE-local `P`).
var _BRAIN_PHASES = ['PERCEIVE','STREAMS','SIMULATE','EVALUATE','SYNTHESIS','SELECT','COUNCIL','ACT','REFLECT'];
var _brainPaused=false;
var _lastHealthData={di:0.5, compute:{c_compute:0.5,c_memory:0.5,c_bandwidth:0.5}};
var _brainOrbitAngle=0;
var _brainPhasePositions=[];
var _hoveredPhase=-1;
var _brainDragState={active:false,startX:0,startY:0,startAngle:0};
(function(){
  var bco=document.getElementById('brain-orbit');
  var bct=document.getElementById('brain-tree');
  if(!bco||!bct)return;
  var co=bco.getContext('2d'), ct=bct.getContext('2d');
  if(!co||!ct)return;
  var P=_BRAIN_PHASES;
  var C=['#4ade80','#60a5fa','#fbbf24','#a78bfa','#f472b6','#fb923c','#34d399','#ff6b6b','#888888'];
  var L_=['Core','Narrative','Mission','Project','Method','Action'];
  var to=0; var _co=co, _bco=bco;
  var tt=0; var _ct=ct, _bct=bct;

  function draw(){
    try{
    // ── Mode 1: Neural Orbit ──
    if(!_brainPaused && !window.__reducedMotion)to+=0.02;
    var diVal=state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:0.5;
    var w=_bco.width=_bco.clientWidth||280,     h=_bco.height=_bco.clientHeight||800;
    var cx=w/2,cy=h/2,R=Math.min(w,h)*0.50;
    var bg=_co.createRadialGradient(cx,cy,0,cx,cy,R*1.4);
    bg.addColorStop(0,'#111122'); bg.addColorStop(1,'#06060a');
    _co.fillStyle=bg; _co.fillRect(0,0,w,h);
    _co.fillStyle='rgba(255,255,255,0.5)'; _co.font='20px sans-serif'; _co.textAlign='center';
    _co.fillText('Neural Orbit - 6 Identity Layers',cx,18);
    var ringClr=diVal>0.8?'74,222,128':diVal>0.5?'251,191,36':'255,68,68';
    for(var li=0;li<L_.length;li++){
      var ri=R*(0.24+li*0.13); _co.beginPath(); _co.arc(cx,cy,ri,0,Math.PI*2);
      _co.strokeStyle='rgba('+ringClr+','+(0.035+li*0.025+diVal*0.04)+')'; _co.lineWidth=1.0; _co.stroke();
      _co.fillStyle='rgba(255,255,255,'+(0.04+li*0.015)+')'; _co.font='12px sans-serif'; _co.textAlign='left';
      _co.fillText(L_[li],cx+ri+8,cy+1);
    }
    _co.beginPath();
    for(var a=0;a<=Math.PI*2;a+=0.05){
      var wv=Math.sin(a*5+to*2)*5+Math.sin(a*8+to*3)*3;
      var wx=cx+Math.cos(a)*(R+wv),wy=cy+Math.sin(a)*(R*0.75+wv*0.75);
      a===0?_co.moveTo(wx,wy):_co.lineTo(wx,wy);
    }
    _co.closePath();
    _co.strokeStyle='rgba('+ringClr+','+(0.1+0.06*Math.sin(to)+diVal*0.08)+')'; _co.lineWidth=2; _co.stroke();
    // AVIKU center label — the identity anchor of the cognitive core
    _co.shadowColor='rgba(0,0,0,0.8)'; _co.shadowBlur=12;
    _co.fillStyle='rgba(255,255,255,0.9)'; _co.font='bold 24px sans-serif'; _co.textAlign='center'; _co.textBaseline='middle';
    _co.fillText('AVIKU',cx,cy);
    _co.shadowBlur=0;
    _co.fillStyle='rgba(255,255,255,0.32)'; _co.font='12px sans-serif';
    _co.fillText('TELOS cognitive core',cx,cy+17);
    var act=_brainPaused?act:Math.floor(to*0.45)%P.length;
    for(var i=0;i<P.length;i++){
      var a1=(i/P.length)*Math.PI*2-Math.PI/2;
      var px1=cx+Math.cos(a1)*R,py1=cy+Math.sin(a1)*R*0.75;
      var a2=((i+1)/P.length)*Math.PI*2-Math.PI/2;
      var px2=cx+Math.cos(a2)*R,py2=cy+Math.sin(a2)*R*0.75;
      _co.beginPath(); _co.moveTo(px1,py1); _co.lineTo(px2,py2);
      _co.strokeStyle='rgba('+ringClr+','+(0.1+0.08*Math.sin(to*0.6+i))+')'; _co.lineWidth=1.0; _co.stroke();
      var da=Math.atan2(py2-py1,px2-px1);
      var ax=px2-Math.cos(da)*10,ay=py2-Math.sin(da)*10;
      _co.beginPath(); _co.moveTo(px2,py2); _co.lineTo(ax-Math.sin(da)*5,ay+Math.cos(da)*5);
      _co.lineTo(ax+Math.sin(da)*5,ay-Math.cos(da)*5); _co.closePath();
      _co.fillStyle='rgba('+ringClr+',0.3)'; _co.fill();
      var tr=(to*0.35+i/P.length)%1;
      var ex=px1+(px2-px1)*tr,ey=py1+(py2-py1)*tr;
      _co.beginPath(); _co.arc(ex,ey,3*(1-Math.abs(tr-0.5)*2),0,Math.PI*2);
      _co.fillStyle='rgba('+ringClr+','+(0.45*(1-Math.abs(tr-0.5)*2))+')'; _co.fill();
    }
    _brainPhasePositions=[];
    for(var i=0;i<P.length;i++){
      var aa=(i/P.length)*Math.PI*2-Math.PI/2+_brainOrbitAngle+Math.sin(to*0.2+i*0.7)*0.01;
      var ppx=cx+Math.cos(aa)*R,ppy=cy+Math.sin(aa)*R*0.75;
      var ia=(i===act),pu=ia?(24+6*Math.sin(to*3))*(0.7+diVal*0.6):(16+5*Math.sin(to*1.5+i*1.1))*(0.7+diVal*0.4);
      _brainPhasePositions.push({x:ppx,y:ppy,name:P[i],color:C[i],index:i,active:ia,size:pu});
      if(ia){
        var ag=_co.createRadialGradient(ppx,ppy,0,ppx,ppy,pu*5);
        ag.addColorStop(0,C[i]+'77'); ag.addColorStop(1,'transparent');
        _co.fillStyle=ag; _co.beginPath(); _co.arc(ppx,ppy,pu*5,0,Math.PI*2); _co.fill();
      }
      var g=_co.createRadialGradient(ppx,ppy,0,ppx,ppy,pu*3);
      g.addColorStop(0,C[i]+'44'); g.addColorStop(1,'transparent');
      _co.fillStyle=g; _co.beginPath(); _co.arc(ppx,ppy,pu*3,0,Math.PI*2); _co.fill();
      _co.fillStyle=C[i]; _co.beginPath(); _co.arc(ppx,ppy,pu,0,Math.PI*2); _co.fill();
      _co.fillStyle='rgba(255,255,255,0.12)';
      _co.beginPath(); _co.arc(ppx-pu*0.2,ppy-pu*0.2,pu*0.25,0,Math.PI*2); _co.fill();
      _co.fillStyle=ia?'#fff':'#bbb'; _co.font=ia?'bold 14px sans-serif':'13px sans-serif';
      _co.textAlign='center'; _co.fillText(P[i],ppx,ppy+pu+12);
    }
    // Draw hover tooltip on orbit phase
    if(_hoveredPhase>=0&&_hoveredPhase<P.length&&_brainPhasePositions[_hoveredPhase]){
      var hp=_brainPhasePositions[_hoveredPhase];
      var hpx=hp.x,hpy=hp.y-24;
      var hw=140,hh=36;
      var hx2=Math.max(2,Math.min(w-hw-2,hpx-hw/2));
      var hy2=Math.max(2,hpy-hh-2);
      _co.save();
      _co.shadowColor='rgba(0,0,0,0.5)';_co.shadowBlur=10;
      _co.fillStyle='rgba(10,10,22,0.92)';_co.strokeStyle='rgba(80,80,140,0.3)';_co.lineWidth=1;
      roundRect(_co,hx2,hy2,hw,hh,6);_co.fill();_co.stroke();
      _co.shadowBlur=0;
      _co.fillStyle='#ddd';_co.font='bold 12px sans-serif';_co.textAlign='left';_co.textBaseline='top';
      _co.fillText(P[_hoveredPhase],hx2+8,hy2+6);
      _co.fillStyle='#888';_co.font='12px sans-serif';
      _co.fillText('DI: '+diVal.toFixed(2)+' | '+P[_hoveredPhase].substring(0,4)+' phase',hx2+8,hy2+22);
      _co.restore();
    }

    // ── Mode 2: Root System ──
    if(!_brainPaused && !window.__reducedMotion)tt+=0.02;
    var diVal2=state.diHistory.length>0?state.diHistory[state.diHistory.length-1]:0.5;
    var ringClr2=diVal2>0.8?'74,222,128':diVal2>0.5?'251,191,36':'255,68,68';
    w=_bct.width=_bct.clientWidth||280; h=_bct.height=_bct.clientHeight||800;
    bg=_ct.createRadialGradient(w/2,h,0,w/2,h,w*0.7);
    bg.addColorStop(0,'#0d0d1a'); bg.addColorStop(1,'#06060a');
    _ct.fillStyle=bg; _ct.fillRect(0,0,w,h);
    _ct.fillStyle='rgba(255,255,255,0.5)'; _ct.font='20px sans-serif'; _ct.textAlign='center';
    _ct.fillText('Root System - 9 Phase Canopy',w/2,18);
    var rx=w/2,ry=h-28,trunkH=h*0.50;
    for(var li=0;li<L_.length;li++){
      var ang=-Math.PI/2+Math.PI*0.15+(li/(L_.length-1))*Math.PI*0.7;
      var len=22+li*10, ex=rx+Math.cos(ang)*len, ey=ry+Math.sin(ang)*len;
      _ct.beginPath(); _ct.moveTo(rx,ry);
      _ct.quadraticCurveTo(rx+Math.cos(ang)*len*0.5,ry+Math.sin(ang)*len*0.5-8,ex,ey);
      _ct.strokeStyle='rgba(100,140,200,'+(0.18+li*0.07)+')'; _ct.lineWidth=1.8-li*0.15; _ct.stroke();
      _ct.fillStyle='rgba(255,255,255,0.45)'; _ct.font='14px sans-serif'; _ct.textAlign='center';
      _ct.fillText(L_[li],ex,ey+14);
    }
    _ct.beginPath(); _ct.moveTo(rx-10,ry);
    _ct.quadraticCurveTo(rx-5,ry-trunkH*0.5,rx-14,ry-trunkH);
    _ct.lineTo(rx+14,ry-trunkH); _ct.quadraticCurveTo(rx+5,ry-trunkH*0.5,rx+10,ry);
    _ct.closePath(); _ct.fillStyle='rgba(50,35,25,0.45)'; _ct.fill();
    var cpY=ry-trunkH-10, cpR=Math.min(w,h)*0.46;
    for(var i=0;i<P.length;i++){
      var ang=-Math.PI+(i/(P.length-1))*Math.PI;
      var bx=rx+Math.cos(ang)*cpR*0.78, by=cpY+Math.sin(ang)*cpR*0.58;
      _ct.beginPath(); _ct.moveTo(rx,ry-trunkH);
      _ct.quadraticCurveTo(rx+Math.cos(ang)*cpR*0.32,cpY+Math.sin(ang)*cpR*0.22-10,bx,by);
      _ct.strokeStyle='rgba(60,80,60,'+(0.18+0.1*Math.sin(tt+i))+')'; _ct.lineWidth=1.2; _ct.stroke();
      var ia=(i===act), pu=ia?28+6*Math.sin(tt*2.5):18+5*Math.sin(tt*1.5+i*0.9);
      if(ia){
        var ag=_ct.createRadialGradient(bx,by,0,bx,by,pu*4);
        ag.addColorStop(0,C[i]+'55'); ag.addColorStop(1,'transparent');
        _ct.fillStyle=ag; _ct.beginPath(); _ct.arc(bx,by,pu*4,0,Math.PI*2); _ct.fill();
      }
      _ct.fillStyle=C[i]; _ct.beginPath(); _ct.arc(bx,by,pu,0,Math.PI*2); _ct.fill();
      _ct.fillStyle='rgba(255,255,255,0.1)';
      _ct.beginPath(); _ct.arc(bx-pu*0.15,by-pu*0.15,pu*0.25,0,Math.PI*2); _ct.fill();
      _ct.fillStyle=ia?'#fff':'#ccc'; _ct.font=ia?'bold 16px sans-serif':'14px sans-serif';
      _ct.textAlign='center'; _ct.fillText(P[i],bx,by+pu+14);
    }
    for(var pi=0;pi<8;pi++){
      var ft=(tt*0.2+pi*0.125)%1;
      _ct.beginPath(); _ct.arc(rx+Math.sin(tt+pi*2)*6*ft,ry-ft*trunkH,0.8,0,Math.PI*2);
      _ct.fillStyle='rgba(150,200,255,'+(0.25*(1-ft))+')'; _ct.fill();
    }
    // Root System ambient particles
    for(var pi2=0;pi2<6;pi2++){
      var ft2=(tt*0.15+pi2*0.167+state.time*0.01)%1;
      var px2=rx+Math.sin(tt*0.3+pi2*2)*cpR*0.6*ft2;
      var py2=ry-ft2*trunkH*0.7-Math.cos(tt*0.2+pi2)*12*ft2;
      _ct.beginPath();_ct.arc(px2,py2,1.2+ft2*1.5,0,Math.PI*2);
      _ct.fillStyle='rgba(150,200,255,'+(0.15*(1-ft2))+')';_ct.fill();
    }
    var bd=document.getElementById('brain-debug');
    if(bd)bd.textContent='Neural Orbit / Root System - active: '+P[act];
    }catch(e){}
    requestAnimationFrame(draw);
  }
  draw();
})();

// ─── Brain orbit mouse drag ───
(function(){
  var boc=document.getElementById('brain-orbit');
  if(!boc)return;
  boc.addEventListener('mousedown',function(e){
    _brainDragState.active=true;
    _brainDragState.startX=e.clientX;
    _brainDragState.startY=e.clientY;
    _brainDragState.startAngle=_brainOrbitAngle;
  });
  window.addEventListener('mousemove',function(e){
    if(!_brainDragState.active)return;
    var dx=e.clientX-_brainDragState.startX;
    _brainOrbitAngle=_brainDragState.startAngle+dx*0.008;
  });
  window.addEventListener('mouseup',function(){_brainDragState.active=false;});
  boc.addEventListener('mousemove',function(e){
    var rect=boc.getBoundingClientRect();
    var mx=e.clientX-rect.left,my=e.clientY-rect.top;
    var found=-1;
    for(var i=0;i<_brainPhasePositions.length;i++){
      var p=_brainPhasePositions[i];
      var d2=(mx-p.x)*(mx-p.x)+(my-p.y)*(my-p.y);
      if(d2<1600){found=i;break;}
    }
    _hoveredPhase=found;
  });
  boc.addEventListener('mouseleave',function(){_hoveredPhase=-1;});
  boc.addEventListener('click',function(e){
    var rect=boc.getBoundingClientRect();
    var mx=e.clientX-rect.left,my=e.clientY-rect.top;
    for(var i=0;i<_brainPhasePositions.length;i++){
      var p=_brainPhasePositions[i];
      var d2=(mx-p.x)*(mx-p.x)+(my-p.y)*(my-p.y);
      if(d2<1600){
        showPhaseDetail(_BRAIN_PHASES[i], i,
          state.diHistory.length > 0 ? state.diHistory[state.diHistory.length-1] : 0.5);
        return;
      }
    }
  });
})();

// ─── Pause/Resume for brain ───
function toggleBrainPause(){
  _brainPaused=!_brainPaused;
  document.querySelectorAll('.brain-pause-btn').forEach(function(btn){btn.textContent=_brainPaused?'▶ Play':'⏸ Pause';});
}

// ─── Fullscreen for brain ───
var _brainFullscreen=false;
function toggleBrainFullscreen(btn){
  _brainFullscreen=!_brainFullscreen;
  // Each mind mode is now its own section/panel — fullscreen the panel the
  // button lives in (fallback: first panel, pre-split behaviour).
  var bp = btn && btn.closest ? btn.closest('.brain-panel') : document.querySelector('.brain-panel');
  if(!bp)return;
  if(_brainFullscreen){
    bp.style.position='fixed';bp.style.top='0';bp.style.left='0';
    bp.style.width='100vw';bp.style.height='100vh';bp.style.zIndex='1000';
    bp.style.margin='0';bp.style.borderRadius='0';
  }else{
    bp.style.position='';bp.style.top='';bp.style.left='';
    bp.style.width='';bp.style.height='';bp.style.zIndex='';
    bp.style.margin='';bp.style.borderRadius='';
  }
}

// ─── Zoom controls ───
var _brainZoom=1;
function zoomBrain(delta){
  _brainZoom=Math.max(0.5,Math.min(3,_brainZoom+delta));
  document.querySelectorAll('.brain-zoom-lvl').forEach(function(el){el.textContent=_brainZoom.toFixed(1)+'×';});
  document.querySelectorAll('.brain-panel .zoom-wrap canvas').forEach(function(c){
    c.style.transform='scale('+_brainZoom+')';
    c.parentNode.style.height=Math.round(540*_brainZoom)+'px';
  });
}
