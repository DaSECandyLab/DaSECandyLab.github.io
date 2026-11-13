(() => {
  'use strict';
  const mascot = document.querySelector('.candy-mascot');
  const input = document.getElementById('query-input');
  const home = document.getElementById('home');
  const motion = document.querySelector('.system-motion');
  const form = document.getElementById('research-query');
  if (!mascot || !input || !home || !form) return;
  const sprite = mascot.querySelector('.candy-sprite');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  // Pose indices: rest, half blink, blink, look left, look right,
  // crouch, hop, landing. Each short action returns to the same rest pose.
  const actions = {
    blink: [[1,55],[2,85],[1,85],[0,0]],
    left: [[0,100],[3,700],[0,180],[1,55],[2,75],[1,75],[0,0]],
    right: [[0,100],[4,700],[0,180],[1,55],[2,75],[1,75],[0,0]],
    curious: [[3,450],[0,200],[4,550],[0,0]],
    hop: [[5,140],[6,160],[7,120],[5,75],[0,0]],
    nod: [[1,120],[7,180],[1,120],[0,0]]
  };
  let frameTimer, idleTimer, visible=false, running=false, busy=false;
  let lastInteraction=-Infinity;
  let pointer=null, gazeRequest=0, currentFrame=0;
  let pendingFeedback=null, feedbackTimer;
  const active=()=>!reduced.matches && !document.hidden && !home.hidden && visible && motion?.dataset.paused!=='true';
  function frame(index) {
    currentFrame=index;
    mascot.dataset.frame=String(index);
    // Blink only the independent eyes; the body stays on its neutral frame.
    const bodyIndex=index===1 || index===2 ? 0 : index;
    sprite.style.backgroundPosition=`${-(bodyIndex%4)*54}px ${-11-Math.floor(bodyIndex/4)*54}px`;
    sprite.style.setProperty('--lid', index===2 ? '.22' : index===1 || index===7 ? '.5' : '1');
    sprite.style.setProperty('--eye-top', (index===5 ? 17.7 : index===6 ? 14.5 : index===7 ? 16.3 : 15)+'px');
    updateGaze();
  }
  function scheduleIdle() {
    clearTimeout(idleTimer);
    if(active())idleTimer=setTimeout(()=>play(pointer || Math.random()<.75?'blink':Math.random()<.5?'left':'right'),6500+Math.random()*6500);
  }
  function play(name, interrupt=false) {
    if(!active() || (busy && !interrupt))return;
    clearTimeout(frameTimer);clearTimeout(idleTimer);
    busy=true;mascot.dataset.action=name;
    const poses=actions[name];let index=0;
    function next() {
      if(!active()){sync();return;}
      const [pose,duration]=poses[index++];frame(pose);
      if(index<poses.length)frameTimer=setTimeout(next,duration);
      else{busy=false;mascot.dataset.action='rest';scheduleIdle();}
    }
    next();
  }
  function react(name, interrupt=false) {
    if(!active() || (!interrupt && performance.now()-lastInteraction<2500))return;
    lastInteraction=performance.now();play(name,interrupt);
  }
  function sync() {
    const enabled=active();mascot.classList.toggle('is-still',!enabled);
    if(!enabled){
      clearTimeout(frameTimer);clearTimeout(idleTimer);busy=false;
      cancelAnimationFrame(gazeRequest);gazeRequest=0;pointer=null;
      frame(0);mascot.dataset.action='rest';
    }else if(!running)scheduleIdle();
    running=enabled;
    if(reduced.matches || document.hidden || home.hidden || motion?.dataset.paused==='true') {
      pendingFeedback=null;clearTimeout(feedbackTimer);
    }else if(enabled && pendingFeedback) {
      const action=pendingFeedback;pendingFeedback=null;clearTimeout(feedbackTimer);
      react(action,true);
    }
  }
  function updateGaze() {
    let x=0,y=0;
    if(active()) {
      if(pointer) {
        const rect=mascot.getBoundingClientRect();
        const dx=pointer.x-(rect.left+rect.width/2);
        const dy=pointer.y-(rect.top+16.5);
        const distance=Math.max(90,Math.hypot(dx,dy));
        x=dx/distance*1.8;y=dy/distance*1.4;
      }else x=currentFrame===3 ? -1.6 : currentFrame===4 ? 1.6 : 0;
    }
    mascot.style.setProperty('--gaze-x',x.toFixed(2)+'px');
    mascot.style.setProperty('--gaze-y',y.toFixed(2)+'px');
  }
  function requestGaze() {
    if(!gazeRequest)gazeRequest=requestAnimationFrame(()=>{gazeRequest=0;updateGaze();});
  }
  function clearGaze() {
    pointer=null;cancelAnimationFrame(gazeRequest);gazeRequest=0;
    mascot.style.setProperty('--gaze-x','0px');
    mascot.style.setProperty('--gaze-y','0px');
  }
  document.addEventListener('pointermove',event=>{
    if(event.pointerType==='touch'){clearGaze();return;}
    if(!active())return;
    pointer={x:event.clientX,y:event.clientY};requestGaze();
  },{passive:true});
  document.addEventListener('pointerleave',clearGaze);
  document.addEventListener('pointercancel',clearGaze);
  document.addEventListener('pointerout',event=>{if(!event.relatedTarget)clearGaze();});
  window.addEventListener('blur',clearGaze);
  window.addEventListener('resize',requestGaze,{passive:true});
  window.addEventListener('scroll',requestGaze,{passive:true});
  input.addEventListener('focus',()=>{if(!pointer)react('left');});
  function searchFeedback(reveal=false) {
    if(reduced.matches || document.hidden || home.hidden || motion?.dataset.paused==='true')return;
    const empty=document.querySelector('#research-result .studio-empty, #research-result .topic-only');
    const action=empty?'curious':'hop';
    pendingFeedback=null;clearTimeout(feedbackTimer);
    const rect=mascot.getBoundingClientRect();
    const fullyVisible=rect.top>=0 && rect.bottom<=innerHeight;
    if(active() && fullyVisible)react(action,true);
    else {
      // Topic links can start below the viewport on phones. Play once visible.
      pendingFeedback=action;
      feedbackTimer=setTimeout(()=>{pendingFeedback=null;},2000);
      if(reveal)form.scrollIntoView({block:'center',behavior:'smooth'});
    }
  }
  form.addEventListener('submit',()=>searchFeedback());
  // app.js registers its search handlers first, so the result is updated here.
  document.addEventListener('click',event=>{
    const trigger=event.target.closest('button[data-jump-query], button[data-prompt]');
    if(trigger)searchFeedback(trigger.hasAttribute('data-jump-query'));
  });
  document.addEventListener('visibilitychange',sync);
  window.addEventListener('hashchange',sync);
  reduced.addEventListener('change',sync);
  if(motion)new MutationObserver(sync).observe(motion,{attributes:true,attributeFilter:['data-paused']});
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting && entries[0].intersectionRatio>=.99;sync();},{threshold:[0,1]}).observe(mascot);
  frame(0);sync();
})();
