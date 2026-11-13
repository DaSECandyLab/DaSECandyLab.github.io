'use strict';
const $ = (s) => document.querySelector(s);
const escapeHTML = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const topics = {
 storage: {tags:['AI → DB', 'Storage', 'Reinforcement learning'],text:'Can a storage engine learn from its workload? Our work explores learning-based decisions in LSM-tree storage, combining non-volatile memory and SSDs.'},
 operations: {tags:['AI → DB', 'Operations', 'Predictive autoscaling'],text:'Our work covers predictive autoscaling, database configuration tuning, and adaptive stream-processing parallelism.'},
 vector: {tags:['DB → AI', 'Vector databases', 'Similarity search'],text:'Our work studies similarity search over high-dimensional streams and trajectories, including representation learning and locality-sensitive hashing.'},
 optimizer: {tags:['AI → DB', 'Query optimization', 'Cardinality estimation'],text:'Our work explores learned cardinality estimation, query planning, physical design, and join execution.'}
};
let resultView='relations';
let selection={topic:'operations',label:'Autoscaling',kind:'topic'};
const topicLabels={storage:'Storage',operations:'Operations',vector:'Vector search',optimizer:'Optimization'};
function selectTopic(key){selection={topic:key,papers:LAB.papers.filter(p=>p.topicKeys.includes(key)),members:[],label:topicLabels[key],kind:'topic'};renderSelection();}
function runQuery(){
 const value=$('#query-input').value.trim();
 const q=value.toLowerCase();
 const member=LAB.members.find(m=>q.includes(m.name.toLowerCase()));
 if(member){selection={topic:null,papers:LAB.papers.filter(p=>p.memberIds.includes(member.id)),members:[],label:member.name,kind:'author'};renderSelection();return;}
 const aliases=[['operations',/operations|demand|resource|资源/],['vector',/vector|similarity|nearest|向量/],['optimizer',/optimiz|cardinality|优化/],['storage',/storage|lsm|nvm|存储/]];
 const match=aliases.find(([,pattern])=>pattern.test(q));
 if(match){selectTopic(match[0]);return;}
 const terms=q.replace(/[^a-z0-9\u4e00-\u9fff ]/g,' ').split(/\s+/).filter(t=>t&&!['find','show','me','work','papers','paper','on','about','the','by','research','explore','all'].includes(t));
 const found=LAB.papers.filter(p=>terms.every(t=>[p.title,p.label,p.authors,p.venue,p.year,...p.topics].join(' ').toLowerCase().includes(t)));
 selection={topic:null,papers:found,members:[],label:value||'All research',kind:terms.length?'query':'collection'};renderSelection();
}
function renderSelection(){
 const s=selection;
 s.members=LAB.members.filter(m=>s.papers.some(p=>p.memberIds.includes(m.id)));
 $('#query-tokens').innerHTML=`<span>${escapeHTML(s.kind)}</span>${escapeHTML(s.label)}`;
 $('#result-count').textContent=`${s.papers.length} work${s.papers.length===1?'':'s'} · ${s.members.length} connected people`;
 document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===resultView)));
 let html='';
 if(!s.papers.length){html=s.topic?`<div class="topic-only"><span class="tag">Research direction</span><p>${escapeHTML(topics[s.topic].text)}</p><a href="#contact">Contact the lab</a><p class="relation-caption">No linked publications in this collection yet.</p></div>`:'<div class="studio-empty">No matching work in this collection.<button data-prompt="Find work on autoscaling">Try autoscaling</button></div>';}
 else if(resultView==='summary'){
 const copy=s.topic?topics[s.topic].text:`${s.papers.length} publication${s.papers.length===1?'':'s'} linked to ${s.label}.`;
 html=`<p class="result-summary">${escapeHTML(copy)}</p>${s.papers.map(p=>`<a class="result-link" href="#publications/${p.id}">${escapeHTML(p.shortTitle)}<small>${escapeHTML(p.venue)} · ${p.year}</small></a>`).join('')}<p class="linked-people">${s.members.map(m=>`<a href="#members/${m.id}">${escapeHTML(m.name)}</a>`).join(' · ')}</p>`;
 }else{
 html=`<div class="relation-labels"><span>${s.kind==='author'?'Researcher':'Research'}</span><span>Works</span><span>People</span></div><div class="relation-canvas"><svg class="relation-edges" aria-hidden="true"></svg><div class="relation-columns"><div class="relation-column"><span class="relation-node topic" id="graph-root">${escapeHTML(s.label)}</span></div><div class="relation-column">${s.papers.map(p=>`<a href="#publications/${p.id}" class="relation-node work" id="graph-${p.id}">${escapeHTML(p.label)}<small>${escapeHTML(p.venue)} ${p.year}</small></a>`).join('')}</div><div class="relation-column">${s.members.map(m=>`<a class="relation-node person" id="graph-${m.id}" href="#members/${m.id}">${escapeHTML(m.name)}</a>`).join('')}</div></div></div><p class="relation-caption">Follow a connection to a paper or its authors.</p>`;
 }
 const node=$('#research-result');node.innerHTML=html;node.classList.remove('relation-enter');void node.offsetWidth;node.classList.add('relation-enter');requestAnimationFrame(drawRelations);
}
function drawRelations(){const svg=$('.relation-edges');if(!svg)return;const rect=svg.getBoundingClientRect();if(!rect.width||!rect.height)return;svg.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);const paths=[];function edge(from,to){const a=document.getElementById(from).getBoundingClientRect();const b=document.getElementById(to).getBoundingClientRect();const x1=a.right-rect.left,y1=a.top+12-rect.top,x2=b.left-rect.left,y2=b.top+12-rect.top;const mid=(x1+x2)/2;paths.push(`<path data-from="${from}" data-to="${to}" d="M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}"/>`);}selection.papers.forEach(p=>{edge('graph-root','graph-'+p.id);selection.members.filter(m=>p.memberIds.includes(m.id)).forEach(m=>edge('graph-'+p.id,'graph-'+m.id));});svg.innerHTML=paths.join('');}
function explore(key){$('#query-input').value='Explore '+topicLabels[key].toLowerCase();selectTopic(key);}
function paperHTML(p){return `<article class="paper" id="${p.id}"><div class="venue">${escapeHTML(p.venue)}<small>${p.year}${p.status==='published'?'':' · '+escapeHTML(p.status)}</small></div><div><h3><a href="${escapeHTML(p.url)}">${escapeHTML(p.title)}</a></h3><p class="authors">${escapeHTML(p.authors)}</p><p class="paper-topics">${escapeHTML(p.topics.join(' · '))}</p></div><a class="paper-arrow" href="${escapeHTML(p.url)}" aria-label="Read ${escapeHTML(p.shortTitle)}">↗</a></article>`}
function papers(){const term=$('#paper-search').value.trim().toLowerCase();const found=LAB.papers.filter(p=>[p.title,p.label,p.authors,p.venue,p.year,...p.topics].join(' ').toLowerCase().includes(term));$('#all-papers').innerHTML=found.length?found.map(paperHTML).join(''):'<p>No publications match this search. Try a different title, author, or topic.</p>';$('#paper-count').textContent=`${found.length} publication${found.length===1?'':'s'} in this collection`;}
function route(){renderMembers();const [path,id]=(location.hash.slice(1)||'home').split('/');const section=['home','members','publications','contact'].includes(path)?path:'home';document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!==section);document.querySelectorAll('[data-nav]').forEach(a=>{if(a.dataset.nav===section)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});document.title=`${section==='home'?'Home':section[0].toUpperCase()+section.slice(1)} — Candy Lab`;if(section==='publications'&&id){$('#paper-search').value='';papers()}if(id){requestAnimationFrame(()=>{const target=document.getElementById(id);if(target){target.scrollIntoView({block:'center'});target.setAttribute('tabindex','-1');target.focus({preventScroll:true})}})}else if(path==='research')$('#research').scrollIntoView();else window.scrollTo(0,0);}
$('#research-query').addEventListener('submit',e=>{e.preventDefault();runQuery();});
document.addEventListener('click',e=>{const button=e.target.closest('button');if(!button)return;if(button.dataset.prompt){$('#query-input').value=button.dataset.prompt;runQuery();}if(button.dataset.view){resultView=button.dataset.view;renderSelection();}});
document.querySelectorAll('[data-jump-query]').forEach(b=>b.addEventListener('click',()=>{explore(b.dataset.jumpQuery);$('.explorer').scrollIntoView({block:'center'});$('#query-input').focus({preventScroll:true});}));
new ResizeObserver(()=>requestAnimationFrame(drawRelations)).observe($('.query-studio'));
document.fonts.ready.then(drawRelations);
$('#paper-search').addEventListener('input',papers);
let membersRenderedYear;
function memberPortrait(member, advisor = false) {
 const size=advisor?144:240;
 const initials=member.name.split(/\s+/).map(part=>part[0]).slice(0,2).join('');
 const fallback=`<span class="member-placeholder" aria-hidden="true">${escapeHTML(initials)}</span>`;
 return `<div class="member-portrait">${fallback}${member.photo?`<img src="${escapeHTML(member.photo)}" alt="${escapeHTML(member.name)}" ${advisor?'':'loading="lazy"'} width="${size}" height="${size}">`:''}</div>`;
}
function memberCard(member, year) {
 const degree={masters:'Master’s',phd:'PhD'}[member.degree];
 return `<article class="member" id="${escapeHTML(member.id)}">${memberPortrait(member)}<h3>${escapeHTML(member.name)}</h3>${degree?`<p>${degree}</p>`:''}<p class="member-years">${escapeHTML(MemberDirectory.years(member,year))}</p></article>`;
}
function renderMembers() {
 const year=MemberDirectory.currentYear();
 if(membersRenderedYear===year)return;
 const groups=MemberDirectory.groups(LAB.members,year);
 $('#advisor-section').hidden=!groups.advisors.length;
 $('#advisor-list').innerHTML=groups.advisors.map(member=>`<article class="advisor-row" id="${escapeHTML(member.id)}">${memberPortrait(member,true)}<div><h3>${escapeHTML(member.name)}</h3><p>Advisor</p></div></article>`).join('');
 const sections=[['students','Current students','intake'],['alumni','Alumni','graduates'],['incoming','Incoming students','intake']];
 $('#member-list').innerHTML=sections.filter(([key])=>groups[key].length).map(([key,title,suffix])=>`<section class="member-group" aria-labelledby="${key}-heading"><h2 class="member-section-title" id="${key}-heading">${title}</h2>${groups[key].map(group=>`<section class="member-cohort"><h3 class="cohort-heading">${group.year==null?'Year not listed':`${group.year} ${suffix}`}</h3><div class="member-list">${group.members.map(member=>memberCard(member,year)).join('')}</div></section>`).join('')}</section>`).join('');
 $('#member-years-note').hidden=!LAB.members.some(m=>m.yearEvidence?.status==='inferred');
 document.querySelectorAll('#members img').forEach(img=>{
  img.addEventListener('error',()=>img.hidden=true,{once:true});
  if(img.complete&&!img.naturalWidth)img.hidden=true;
 });
 membersRenderedYear=year;
}
renderMembers();
document.addEventListener('visibilitychange',()=>{if(!document.hidden)renderMembers();});
setInterval(renderMembers,60000);
window.addEventListener('hashchange',route);runQuery();papers();route();

function traceNode(target){const node=target.closest('.relation-node');const canvas=$('.relation-canvas');if(!canvas)return;canvas.classList.toggle('tracing',!!node);const linked=new Set(node?[node.id]:[]);canvas.querySelectorAll('path').forEach(path=>{const active=node&&(path.dataset.from===node.id||path.dataset.to===node.id);path.classList.toggle('is-connected',!!active);if(active){linked.add(path.dataset.from);linked.add(path.dataset.to);}});canvas.querySelectorAll('.relation-node').forEach(n=>n.classList.toggle('is-connected',linked.has(n.id)));}
$('#research-result').addEventListener('pointerover',e=>traceNode(e.target));
$('#research-result').addEventListener('pointerleave',()=>traceNode($('#research-result')));
$('#research-result').addEventListener('focusin',e=>traceNode(e.target));
$('#research-result').addEventListener('focusout',()=>traceNode($('#research-result')));
