'use strict';
(()=>{
 const root=document.querySelector('.system-motion');if(!root)return;
 const svg=root.querySelector('svg'),button=document.getElementById('motion-toggle');
 const request=svg.querySelector('#motion-request'),response=svg.querySelector('#motion-return');
 const packet=svg.querySelector('#motion-packet'),scan=svg.querySelector('#motion-scan'),context=svg.querySelector('#motion-context');
 const tokens=[...svg.querySelectorAll('.output-tokens rect')],rows=[...svg.querySelectorAll('.record-row')],stages=[...root.querySelectorAll('[data-stage]')];
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let paused=reduced.matches,visible=false,frame=0,last=0,elapsed=reduced.matches?7100:0;
 const cycle=8000;
 function draw(){
  const t=elapsed%cycle,stage=t<1700?0:t<3600?1:t<5400?2:3;
  root.dataset.stage=String(stage);root.dataset.elapsed=String(Math.round(elapsed));
  stages.forEach((e,i)=>e.classList.toggle('active',i===stage));
  rows.forEach((e,i)=>e.classList.toggle('selected',stage>=1&&i===1));
  packet.style.opacity=(stage===0||stage===2)?'1':'0';scan.style.opacity=stage===1?'1':'0';context.style.opacity=stage>=3?'1':'0';
  if(stage===0||stage===2){const path=stage===0?request:response;const progress=stage===0?t/1700:(t-3600)/1800;const point=path.getPointAtLength(path.getTotalLength()*Math.min(1,progress));packet.setAttribute('x',point.x-3);packet.setAttribute('y',point.y-3);}
  if(stage===1){const x=115+169*(t-1700)/1900;scan.setAttribute('d',`M${x} 75V133`);}
  tokens.forEach((e,i)=>e.classList.toggle('active',stage===3&&(t-5400)>i*360));
 }
 function tick(now){frame=0;if(paused||!visible||document.hidden)return;if(last)elapsed+=Math.min(now-last,60);last=now;draw();frame=requestAnimationFrame(tick);}
 function sync(){if(frame)cancelAnimationFrame(frame);frame=0;last=0;button.textContent=paused?'Play':'Pause';button.setAttribute('aria-label',paused?'Play animation':'Pause animation');root.dataset.paused=String(paused);if(!paused&&visible&&!document.hidden)frame=requestAnimationFrame(tick);}
 button.addEventListener('click',()=>{paused=!paused;sync();});
 new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();},{threshold:.1}).observe(root);
 document.addEventListener('visibilitychange',sync);
 reduced.addEventListener('change',()=>{paused=reduced.matches;if(paused){elapsed=7100;draw();}sync();});
 draw();sync();
})();
