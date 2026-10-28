// Generated from reconstruction/editor/editor.html by reconstruction/ovh/build_web.py.
(() => {
let active = null;
window.doemoEditor = {
  mount: async function(host, initial, user, onChange) {
    const root = host.shadowRoot || host.attachShadow({mode:'open'});
    root.innerHTML = "<style>\n:host{font:14px system-ui;color:#e8eef6;background:#101925}*{box-sizing:border-box}body{margin:0}header{height:68px;display:flex;align-items:center;gap:24px;padding:12px 22px;border-bottom:1px solid #334052}header strong{font-size:22px;letter-spacing:2px}header span{color:#b7c6d8}.badge{background:#493714;color:#ffd38a;border-radius:16px;padding:6px 12px;font-size:12px}main{display:grid;grid-template-columns:290px 1fr;height:782px}aside{padding:16px;overflow:auto;border-right:1px solid #334052}label{display:block;margin:10px 0;color:#bccadb}button,select,input{font:inherit;border-radius:5px;border:1px solid #46556a;background:#223147;color:white;padding:8px;max-width:100%}button{cursor:pointer}button:hover{background:#38506d}button:disabled{opacity:.45;cursor:default}.row{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0}.row>*{flex:1}input[type=number]{width:114px}input[type=checkbox]{width:auto}.hint{font-size:12px;line-height:1.6;color:#acbed4}.green{background:#15544a}.danger{background:#60352f}#stage{display:flex;flex-direction:column;min-width:0}#tools{padding:10px;background:#192638;display:flex;gap:10px;align-items:center;flex-wrap:wrap}#viewport{overflow:auto;flex:1;background:#66717d;padding:20px}svg{background:white;display:block;width:100%;height:auto;touch-action:none}#message{min-height:36px;padding:10px 18px;color:#ffd38a;background:#192638}h3{font-size:14px;margin-top:22px}#observations{max-height:140px;overflow:auto}#observations div{padding:6px 0;border-bottom:1px solid #344052}#summary{font-variant-numeric:tabular-nums;line-height:1.8}a{color:#9bd6ff}\n[hidden]{display:none!important}main{grid-template-rows:minmax(0,1fr)}#stage,#viewport{min-height:0}</style>\n<header><strong>DOEMO <small>STUDIO</small></strong><span>Reconstruction architecturale</span><b class=\"badge\">Prototype · validation requise</b></header>\n<main><aside>\n<label>Projet JSON <input id=\"load\" type=\"file\" accept=\".json\"></label>\n<label>Niveau <select id=\"level\"></select></label><label><input type=\"checkbox\" id=\"floor\"> Identification du niveau vérifiée</label>\n<div id=\"summary\"></div><p class=\"hint\">Les axes sont noirs. Halo orange : à contrôler. Bleu : sélection. Aucune échelle métrique déduite automatiquement.</p>\n<label>Votre nom <input id=\"actor\" placeholder=\"Dessinateur\"></label>\n<h3>Mur sélectionné</h3><div id=\"selected\" class=\"hint\">Cliquez sur un mur.</div>\n<div class=\"row\"><label>Début X <input type=\"number\" step=\".1\" id=\"ax\"></label><label>Début Y <input type=\"number\" step=\".1\" id=\"ay\"></label></div>\n<div class=\"row\"><label>Fin X <input type=\"number\" step=\".1\" id=\"bx\"></label><label>Fin Y <input type=\"number\" step=\".1\" id=\"by\"></label></div>\n<label>Épaisseur détectée (vide = inconnue) <input type=\"number\" min=\".1\" step=\".1\" id=\"thickness\" value=\"3\"></label>\n<div class=\"row\"><button id=\"apply\">Appliquer</button><button id=\"approve\" class=\"green\">Valider le mur</button></div>\n<div class=\"row\"><button id=\"opening\">Créer une ouverture</button><button id=\"delete\" class=\"danger\">Supprimer</button></div>\n<label>Trait graphique (unités du document) <input type=\"number\" min=\".1\" max=\"50\" step=\".1\" id=\"strokeWidth\" value=\"1\"></label><button id=\"style\">Appliquer le trait</button><div class=\"row\"><button id=\"split\">Couper le mur</button><button id=\"connect\">Raccorder la fin B</button><button id=\"calibrate\">Calibrer une cote</button></div>\n<p class=\"hint\">Déplacez un mur en le faisant glisser. Modifiez ses extrémités pour le prolonger. Un raccord exige le choix explicite de deux murs. Toute modification annule leur validation.</p>\n<button id=\"median\">Deux bords → un axe médian</button><p class=\"hint\">À utiliser seulement si deux traces représentent les bords du même mur. L’axe est créé sur leur portion commune ; les parties qui dépassent sont conservées. Le résultat reste à valider.</p>\n<h3>Ouvertures du mur</h3><select id=\"openingList\"></select><div class=\"row\"><button id=\"editOpening\">Corriger</button><button id=\"removeOpening\">Supprimer l’ouverture</button></div><h3>Zones à contrôler</h3><div id=\"observations\" class=\"hint\"></div>\n<h3>Enregistrer</h3><div class=\"row\"><button id=\"save\">Projet JSON</button><button id=\"svgExport\">SVG validé</button></div><div class=\"row\"><button id=\"draft\">SVG de revue</button><button id=\"training\">Corrections validées</button></div><p class=\"hint\">Enregistrez le JSON pour conserver les corrections. L’export SVG validé ne contient que les murs approuvés du niveau affiché. Ouvrez le SVG dans Illustrator pour contrôler les objets.</p>\n</aside><section id=\"stage\"><div id=\"tools\"><button id=\"add\">Ajouter un mur</button><button id=\"undo\">Annuler</button><button id=\"redo\">Refaire</button><label><input id=\"reference\" type=\"checkbox\" checked> Plan original</label><label><input id=\"candidates\" type=\"checkbox\" checked> Propositions</label><label><input id=\"zones\" type=\"checkbox\" checked> Zones à contrôler</label><button id=\"focus\">Cadrer le niveau</button><button id=\"full\">Page entière</button><label>Zoom <input type=\"range\" id=\"zoom\" min=\"100\" max=\"300\" value=\"100\"></label></div><div id=\"viewport\"><svg id=\"canvas\" xmlns=\"http://www.w3.org/2000/svg\"></svg></div><div id=\"message\" role=\"status\">Chargez un projet ou utilisez la page de test incluse.</div></section></main>\n";
    const realDocument = globalThis.document;
    const document = {
      getElementById: id => root.getElementById(id),
      createElement: (...args) => realDocument.createElement(...args),
      createElementNS: (...args) => realDocument.createElementNS(...args),
      addEventListener: (...args) => root.addEventListener(...args),
    };
'use strict';
let doc=null,index=0,selected=null,mode=null,first=null,drag=null,undo=[],redo=[];
const $=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg';
const level=()=>doc.levels[index], chosen=()=>level().walls.find(w=>w.id===selected);
const clone=x=>JSON.parse(JSON.stringify(x));
const distance=(a,b)=>Math.hypot(b[0]-a[0],b[1]-a[1]);
function say(t){$('message').textContent=t}
function actor(){const a=$('actor').value.trim();if(!a)throw Error('Indiquez votre nom pour enregistrer une correction.');return a}
function intervals(w){let cursor=0,out=[];for(const o of [...w.openings].sort((a,b)=>a.start-b.start)){
  if(!Number.isFinite(o.start)||!Number.isFinite(o.end)||o.start<cursor||o.start<0||o.end>1||o.start>=o.end||!['door','window','passage'].includes(o.kind)||!['pending','approved'].includes(o.status))throw Error('Ouvertures invalides');
  if(o.start>cursor)out.push([cursor,o.start]);cursor=o.end;
}if(cursor<1)out.push([cursor,1]);return out}
function axis(w,lo=0,hi=1){return [lo,hi].map(t=>w.a.map((v,i)=>v+(w.b[i]-v)*t))}
function pathData(w,lo,hi){const [a,b]=axis(w,lo,hi);return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`}
function check(d){
 if(d.schema!=='doemo.architecture/1'||!Array.isArray(d.levels)||!d.levels.length||!Number.isInteger(d.revision)||d.revision<0||!Array.isArray(d.history))throw Error('Projet incompatible');
 const ids=new Set();
 for(const l of d.levels){
  if(!Number.isFinite(l.width)||!Number.isFinite(l.height)||l.width<=0||l.height<=0)throw Error('Dimensions invalides');
  if(!Number.isFinite(l.stroke_width??1)||(l.stroke_width??1)<=0||(l.stroke_width??1)>50)throw Error('Trait graphique invalide');
  for(const w of l.walls){
   if(ids.has(w.id))throw Error('Identifiant dupliqué');ids.add(w.id);
   if(w.a.length!==2||w.b.length!==2||![...w.a,...w.b].every(Number.isFinite)||distance(w.a,w.b)<1e-6||(w.thickness!==null&&(!Number.isFinite(w.thickness)||w.thickness<=0)))throw Error('Mur invalide');
   if(!['pending','approved','rejected'].includes(w.status))throw Error('État invalide');
   for(const p of [w.a,w.b])if(p[0]<0||p[0]>l.width||p[1]<0||p[1]>l.height)throw Error('Mur hors page');intervals(w);
  }
 }return d;
}
function journal(l){return clone({id:l.id,source_page:l.source_page,walls:l.walls,scale:l.scale,floor_validated:l.floor_validated,stroke_width:l.stroke_width??1})}
function mutate(operation,fn){try{
 const name=actor(),snapshot=journal(level()),before=clone(snapshot);
 try{fn();check(doc)}catch(e){Object.assign(level(),snapshot);throw e}
 undo.push({levelId:level().id,snapshot});if(undo.length>40)undo.shift();redo=[];
 doc.revision++;doc.history.push({revision:doc.revision,actor:name,level_id:level().id,operation,before,after:journal(level())});
 onChange();render();say('Correction en mémoire. Cliquez sur Enregistrer sur OVH.');
}catch(e){if(doc)render();say(e.message)}}
function historyMove(from,to,op){try{
 if(!from.length)return;const name=actor(),entry=from[from.length-1],l=doc.levels.find(l=>l.id===entry.levelId),before=journal(l);
 Object.assign(l,clone(entry.snapshot));try{check(doc)}catch(e){Object.assign(l,before);throw e}
 from.pop();to.push({levelId:l.id,snapshot:before});doc.revision++;
 doc.history.push({revision:doc.revision,actor:name,level_id:l.id,operation:{op},before,after:journal(l)});
 onChange();index=doc.levels.indexOf(l);$('level').value=index;selected=null;focus();render();say(op==='undo'?'Correction annulée.':'Correction rétablie.');
}catch(e){say(e.message)}}
function element(tag,attrs,parent=$('canvas')){const el=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));parent.appendChild(el);return el}
function focus(){const l=level(),b=l.region||[0,0,l.width,l.height];$('canvas').setAttribute('viewBox',`${b[0]-10} ${b[1]-10} ${b[2]-b[0]+20} ${b[3]-b[1]+20}`)}
function fields(){
 const w=chosen();$('selected').textContent=w?`${w.id.slice(0,16)} · ${w.status==='approved'?'validé':'à valider'} · ${w.openings.length} ouverture(s)`:'Cliquez sur un mur.';
 if(w){for(const [id,v]of Object.entries({ax:w.a[0],ay:w.a[1],bx:w.b[0],by:w.b[1],thickness:w.thickness}))$(id).value=v===null?'':Number(v.toFixed(3))}
 $('strokeWidth').value=level().stroke_width??1;
 $('openingList').replaceChildren();for(const [i,o]of (w?.openings||[]).entries()){
 const option=document.createElement('option');option.value=i;option.textContent=`${i+1} · ${o.kind} · ${o.start.toFixed(3)}–${o.end.toFixed(3)} · ${o.status}`;$('openingList').append(option);
 }
}
function render(){if(!doc)return;const l=level(),svg=$('canvas');svg.replaceChildren();
 if($('reference').checked&&typeof l.reference==='string'&&l.reference.startsWith('data:image/png;base64,'))element('image',{href:l.reference,x:0,y:0,width:l.width,height:l.height,opacity:.65});
 if($('zones').checked)for(const z of l.observations||[]){const b=z.bbox,r=element('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'#b55eea','fill-opacity':.08,stroke:'#9f4ac8','stroke-width':.6,'stroke-dasharray':'3 2','pointer-events':'none'});element('title',{},r).textContent=z.reason}
 for(const w of l.walls){if(w.status==='rejected'||(w.status!=='approved'&&!$('candidates').checked))continue;
  const g=element('g',{'data-id':w.id}),width=l.stroke_width??1;element('title',{},g).textContent=`${w.id} · ${w.status} · épaisseur détectée : ${w.thickness??'inconnue'}`;
  for(const [lo,hi]of intervals(w)){
   const d=pathData(w,lo,hi);
   if(w.id===selected||(w.status==='pending'&&$('zones').checked))element('path',{d,fill:'none',stroke:w.id===selected?'#1678e0':'#d78b18','stroke-width':width+2,'stroke-opacity':.5,'pointer-events':'none'},g);
   element('path',{d,fill:'none',stroke:'#000000','stroke-width':width,'stroke-linecap':'butt'},g);
   element('path',{d,fill:'none',stroke:'transparent','stroke-width':Math.max(5,width),'pointer-events':'stroke'},g);
  }
  if(w.id===selected)for(const p of [w.a,w.b])element('circle',{cx:p[0],cy:p[1],r:2,fill:'#0756ac','pointer-events':'none'},g);
 }
 const approved=l.walls.filter(w=>w.status==='approved').length;
 $('summary').textContent=`${l.walls.length} murs · ${approved} validés · ${l.walls.length-approved} à contrôler. Échelle : ${l.scale?l.scale.mm_per_unit.toFixed(3)+' mm/unité':'non validée'}.`;
 $('floor').checked=!!l.floor_validated;$('undo').disabled=!undo.length;$('redo').disabled=!redo.length;
 $('observations').replaceChildren();for(const z of l.observations||[]){const e=document.createElement('div');e.textContent=z.reason;$('observations').append(e)}fields();
}
function load(d){doc=check(d);index=0;selected=null;undo=[];redo=[];$('level').replaceChildren();for(const [i,l]of doc.levels.entries()){const o=document.createElement('option');o.value=i;o.textContent=l.name;$('level').append(o)}focus();render();say('Projet chargé. Les propositions exigent une validation humaine.')}
function xy(e){const p=$('canvas').createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform($('canvas').getScreenCTM().inverse());return [q.x,q.y]}
$('canvas').addEventListener('pointerdown',e=>{
 if(!doc)return;const p=xy(e),target=e.target.closest('[data-id]');
 if(mode==='add'){if(!first){first=p;say('Cliquez sur la fin du mur.')}else{const a=first,b=p,t=$('thickness').value===''?null:Number($('thickness').value),id=crypto.randomUUID();mutate({op:'add',a,b,thickness:t},()=>level().walls.push({id,kind:'wall',a,b,thickness:t,status:'pending',confidence:0,method:'manual',evidence:[],openings:[]}));mode=first=null}return}
 if((mode==='connect'||mode==='median')&&!target)return say('Cliquez sur la seconde trace, ou appuyez sur Échap pour annuler.');
 if(mode==='connect'&&target){const source=chosen(),other=level().walls.find(w=>w.id===target.dataset.id);mode=null;if(source===other)return say('Choisissez un autre mur.');connect(source,other,distance(p,other.a)<distance(p,other.b)?'a':'b');return}
 if(mode==='median'&&target){const source=chosen(),other=level().walls.find(w=>w.id===target.dataset.id);mode=null;median(source,other);return}
 selected=target?target.dataset.id:null;render();if(target){try{actor();drag={p,a:clone(chosen().a),b:clone(chosen().b),id:selected};$('canvas').setPointerCapture(e.pointerId)}catch(err){say(err.message)}}
});
$('canvas').addEventListener('pointerup',e=>{if(!drag)return;const d=drag;drag=null;const q=xy(e),dx=q[0]-d.p[0],dy=q[1]-d.p[1];if(Math.hypot(dx,dy)<.5)return;const a=[d.a[0]+dx,d.a[1]+dy],b=[d.b[0]+dx,d.b[1]+dy];mutate({op:'update',id:d.id,a,b},()=>{const w=chosen();w.a=a;w.b=b;w.status='pending'})});
$('canvas').addEventListener('pointercancel',()=>{drag=null});
function connect(w,v,end){const a=w.a,b=w.b,c=v.a,d=v.b,dx=b[0]-a[0],dy=b[1]-a[1],ex=d[0]-c[0],ey=d[1]-c[1],cross=dx*ey-dy*ex;
 if(Math.abs(cross)<1e-9)return say('Raccord parallèle ambigu.');const t=((c[0]-a[0])*ey-(c[1]-a[1])*ex)/cross,p=[a[0]+t*dx,a[1]+t*dy];
 if(w.openings.length||v.openings.length)return say('Revalidez les ouvertures avant de modifier la longueur.');
 if(Math.max(distance(p,w.b),distance(p,v[end]))>20)return say('Raccord trop éloigné (20 unités maximum).');
 mutate({op:'connect',id:w.id,other_id:v.id,end:'b',other_end:end,max_distance:20},()=>{w.b=p.slice();v[end]=p.slice();w.status=v.status='pending'});
}
function median(w,v){
 if(!w||!v)return say('Sélectionnez de nouveau les deux traces.');
 if(w===v)return say('Choisissez deux traces distinctes.');
 if(w.openings.length||v.openings.length)return say('Les ouvertures renseignées doivent être contrôlées séparément avant cette opération.');
 if(w.status==='rejected'||v.status==='rejected')return say('Trace rejetée.');
 const length=distance(w.a,w.b),other=distance(v.a,v.b),ux=(w.b[0]-w.a[0])/length,uy=(w.b[1]-w.a[1])/length;
 if(Math.abs(ux*(v.b[1]-v.a[1])-uy*(v.b[0]-v.a[0]))/other>Math.sin(Math.PI/180))return say('Les traces ne sont pas parallèles (tolérance 1 degré).');
 const projected=[v.a,v.b].map(p=>(p[0]-w.a[0])*ux+(p[1]-w.a[1])*uy),lo=Math.max(0,Math.min(...projected)),hi=Math.min(length,Math.max(...projected));
 if(hi-lo<1e-6)return say('Aucune portion commune ; le passage reste ouvert.');
 const ranges=[[lo/length,hi/length],[lo,hi].map(t=>(t-projected[0])/(projected[1]-projected[0]))],faces=[axis(w,...ranges[0]),axis(v,...ranges[1])];
 const offsets=faces[0].map((p,i)=>ux*(faces[1][i][1]-p[1])-uy*(faces[1][i][0]-p[0]));
 if(offsets[0]*offsets[1]<=0||Math.min(...offsets.map(Math.abs))<1e-6||Math.max(...offsets.map(Math.abs))>24||Math.abs(offsets[0]-offsets[1])>.5)return say('Séparation ambiguë ou supérieure à 24 unités du document.');
 const points=faces[0].map((p,i)=>p.map((n,k)=>(n+faces[1][i][k])/2)),id=crypto.randomUUID();
 mutate({op:'merge_parallel_faces',id:w.id,other_id:v.id,max_separation:24},()=>{
  const center={id,kind:'wall',a:points[0],b:points[1],thickness:offsets.reduce((n,t)=>n+Math.abs(t),0)/2,status:'pending',confidence:0,method:'manual_parallel_faces',openings:[],
    evidence:[{source_walls:[w.id,v.id],paired_sides:faces,source_intervals:ranges,human_interpretation:'same_wall_faces'}]},pieces=[center];
  for(const [i,source]of [w,v].entries()){
   const [start,end]=ranges[i].map(t=>Math.max(0,Math.min(1,t))).sort((a,b)=>a-b);
   for(const [rlo,rhi]of [[0,start],[end,1]]){
    if((rhi-rlo)*distance(source.a,source.b)<1e-6)continue;
    const part=clone(source);part.id=crypto.randomUUID();[part.a,part.b]=axis(source,rlo,rhi);part.status='pending';
    part.evidence.push({unmerged_remainder_of:source.id,source_interval:[rlo,rhi]});pieces.push(part);
   }
  }
  level().walls=level().walls.filter(x=>x.id!==w.id&&x.id!==v.id).concat(pieces);selected=id;
 });
}
$('apply').onclick=()=>{const w=chosen();if(!w)return;const near=(v,old)=>Math.abs(v-old)<.001?old:v,a=[near(+$('ax').value,w.a[0]),near(+$('ay').value,w.a[1])],b=[near(+$('bx').value,w.b[0]),near(+$('by').value,w.b[1])],t=$('thickness').value===''?null:+$('thickness').value;
 if(w.openings.length&&distance(a.map((v,i)=>v-w.a[i]),b.map((v,i)=>v-w.b[i]))>1e-9)return say('Déplacez le mur ou corrigez ses ouvertures avant de changer sa longueur.');
 mutate({op:'update',id:w.id,a,b,thickness:t},()=>{w.a=a;w.b=b;w.thickness=t;w.status='pending'});
};
$('style').onclick=()=>{const width=+$('strokeWidth').value;mutate({op:'style',stroke_width:width},()=>{level().stroke_width=width})};
$('approve').onclick=()=>{const w=chosen();if(w)mutate({op:'approve',id:w.id},()=>{if(w.openings.some(o=>o.status!=='approved'))throw Error('Ouvertures non validées');w.status='approved'})};
$('delete').onclick=()=>{if(chosen())mutate({op:'delete',id:selected},()=>{level().walls=level().walls.filter(w=>w.id!==selected);selected=null})};
function openingForm(previous={start:.4,end:.6,kind:'door'}){
 const kind=prompt('Type : door, window ou passage',previous.kind);if(!['door','window','passage'].includes(kind))return null;
 const start=prompt('Début de l’ouverture (fraction de 0 à 1)',String(previous.start));if(start===null)return null;
 const end=prompt('Fin de l’ouverture (fraction de 0 à 1)',String(previous.end));if(end===null)return null;
 return {start:Number(start),end:Number(end),kind,status:'approved'};
}
$('opening').onclick=()=>{const w=chosen();if(!w)return;const o=openingForm();if(o)mutate({op:'opening',id:w.id,...o},()=>{w.openings.push(o);w.status='pending'})};
$('editOpening').onclick=()=>{const w=chosen(),i=+$('openingList').value;if(!w?.openings[i])return;const o=openingForm(w.openings[i]);if(o)mutate({op:'update_opening',id:w.id,index:i,...o},()=>{w.openings[i]=o;w.status='pending'})};
$('removeOpening').onclick=()=>{const w=chosen(),i=+$('openingList').value;if(w?.openings[i])mutate({op:'delete_opening',id:w.id,index:i},()=>{w.openings.splice(i,1);w.status='pending'})};
$('split').onclick=()=>{const w=chosen();if(!w)return;const answer=prompt('Position de coupe sur le mur (fraction entre 0 et 1)','0.5');if(answer===null)return;const t=Number(answer);
 mutate({op:'split',id:w.id,fraction:t},()=>{
 if(!Number.isFinite(t)||t<=0||t>=1)throw Error('Position de coupe invalide');
 const parts=[[0,t],[t,1]].map(([lo,hi],i)=>{const part=clone(w);[part.a,part.b]=axis(w,lo,hi);part.status='pending';if(i)part.id=crypto.randomUUID();
 part.openings=w.openings.filter(o=>Math.max(lo,o.start)<Math.min(hi,o.end)).map(o=>({...o,start:(Math.max(lo,o.start)-lo)/(hi-lo),end:(Math.min(hi,o.end)-lo)/(hi-lo)}));
 part.evidence.push({split_from:w.id,interval:[lo,hi]});return part});level().walls.splice(level().walls.indexOf(w),1,...parts);
 });
};
$('calibrate').onclick=()=>{const w=chosen();if(!w)return say('Sélectionnez un mur dont la longueur correspond à une cote vérifiée.');const s=prompt('Longueur vérifiée entre A et B, en millimètres');if(s===null)return;const n=Number(s),evidence=prompt('Référence de la cote ou du relevé vérifié');if(!evidence||!Number.isFinite(n)||n<=0)return say('Cote et preuve requises.');mutate({op:'calibrate',a:w.a,b:w.b,length_mm:n,evidence},()=>{level().scale={mm_per_unit:n/distance(w.a,w.b),validated_by:actor(),evidence,points:[w.a,w.b]}})};
$('floor').onchange=()=>{const value=$('floor').checked;mutate({op:'identify_floor',validated:value},()=>{level().floor_validated=value})};
$('connect').onclick=()=>{if(!chosen())return say('Sélectionnez d’abord un mur.');mode='connect';say('Cliquez près de l’extrémité du second mur à raccorder à la fin B. Les deux validations seront annulées.')};
$('median').onclick=()=>{if(!chosen())return say('Sélectionnez d’abord une trace de bord.');mode='median';say('Cliquez sur l’autre bord du même mur. L’axe commun remplacera les deux traces sur leur recouvrement. Échap pour annuler.')};
$('add').onclick=()=>{mode='add';first=null;say('Cliquez sur le début du nouveau mur, puis sur sa fin.')};
$('undo').onclick=()=>historyMove(undo,redo,'undo');$('redo').onclick=()=>historyMove(redo,undo,'redo');
$('level').onchange=()=>{index=+$('level').value;selected=null;mode=null;focus();render()};
for(const id of ['reference','candidates','zones'])$(id).onchange=render;
$('focus').onclick=focus;$('full').onclick=()=>{$('canvas').setAttribute('viewBox',`0 0 ${level().width} ${level().height}`)};
$('zoom').oninput=()=>{$('canvas').style.width=$('zoom').value+'%'};
function download(name,text,type='application/json'){const u=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
$('save').onclick=()=>{if(doc)download('doemo-architecture.json',JSON.stringify(doc,null,2))};
function svgExport(preview){if(!doc)return;const l=level(),svg=document.createElementNS(ns,'svg');svg.setAttribute('xmlns',ns);svg.setAttribute('viewBox',`0 0 ${l.width} ${l.height}`);svg.setAttribute('width',l.width+(l.unit==='pt'?'pt':'px'));svg.setAttribute('height',l.height+(l.unit==='pt'?'pt':'px'));
 const ref=element('g',{id:'reference',style:'display:none'},svg);element('image',{href:l.reference,width:l.width,height:l.height},ref);
 for(const name of ['walls','doors','windows','stairs','rooms','texts','fire_equipment']){const g=element('g',{id:name},svg);if(name==='walls')for(const w of l.walls){
 if(w.status==='rejected'||(!preview&&w.status!=='approved'))continue;
 const wg=element('g',{id:'wall-'+w.id,'data-status':w.status},g);for(const [lo,hi]of intervals(w))element('path',{d:pathData(w,lo,hi),fill:'none',stroke:'#000000','stroke-width':l.stroke_width??1,'stroke-linecap':'butt','stroke-linejoin':'miter'},wg);
 }}download((preview?'revue-':'valide-')+l.id+'.svg',new XMLSerializer().serializeToString(svg),'image/svg+xml');
}
$('svgExport').onclick=()=>svgExport(false);$('draft').onclick=()=>svgExport(true);
$('training').onclick=()=>{const records=new Map();for(const h of doc.history){if(h.operation.op!=='approve')continue;const old=h.after.walls.find(w=>w.id===h.operation.id),l=doc.levels.find(l=>l.id===h.level_id),now=l.walls.find(w=>w.id===h.operation.id);if(old&&JSON.stringify(old)===JSON.stringify(now))records.set(l.id+':'+old.id,{schema:'doemo.training.architecture/1',source:doc.source,level_id:l.id,coordinate:l.coordinate,revision:h.revision,validated_by:h.actor,wall:old})}download('corrections-validees.jsonl',[...records.values()].map(r=>JSON.stringify(r)).join('\n'),'application/x-ndjson')};
$('load').onchange=async e=>{try{load(JSON.parse(await e.target.files[0].text()))}catch(err){say(err.message)}};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){mode=first=drag=null;say('Opération annulée.')}});

    $('actor').value = user; $('actor').readOnly = true;
    $('load').parentElement.hidden = true;
    load(initial);
    active = {document:()=>clone(doc),replace:value=>{doc=check(value);render()},
      lock:value=>{root.querySelector('main').inert=value}};
  },
  document: () => active.document(),
  replace: value => active.replace(value),
  lock: value => active && active.lock(value),
};
})();
