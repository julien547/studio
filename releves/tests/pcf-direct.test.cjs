const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(__dirname+'/../illustrator/DOEMO-PCF-Direct.jsx','utf8').replace(/^#target.*\n/,'');
const text=process.env.DOEMO_PCF_TRACES_PATH?fs.readFileSync(process.env.DOEMO_PCF_TRACES_PATH,'utf8'):
  '0 0.915 0.791 0 k 0 0 19.842 19.842 re f\n'+Array.from({length:8},(_,i)=>`q 1 0 0 1 ${i+1} 2 cm /CS0 cs 1 scn 0 0 1 1 re f* Q`).join('\n');
function run({badModel=false,failPath=false,failSave=false,already=false}={}) {
  const events=[],alerts=[],created=[];
  const root={typename:'Layer',name:'DOEMO - COMPLEMENTS PROVISOIRES - ANIMALIS',visible:true,parent:{typename:'Document'}};
  function group(parent) {
    const g={parent,pathItems:[],remove(){events.push('remove-new');}};
    g.pathItems.add=()=>{
      if(failPath)throw Error('path failure');
      const p={setEntirePath(points){this.points=Array.from(points,p=>Array.from(p));},zOrder(){}};g.pathItems.push(p);return p;
    };
    Object.defineProperty(g,'visibleBounds',{get(){
      const ps=g.pathItems.flatMap(p=>p.points||[]);return [Math.min(...ps.map(p=>p[0])),Math.max(...ps.map(p=>p[1])),Math.max(...ps.map(p=>p[0])),Math.min(...ps.map(p=>p[1]))];
    }});
    created.push(g);return g;
  }
  const old=[];
  for(const [id,x,y] of [[13,141.5,835],[14,269,266]]) {
    const parent={typename:'Layer',visible:true,parent:root};parent.groupItems={add:()=>group(parent)};
    old.push({parent,name:'',note:`DOEMO Animalis / position ${id} / PROVISOIRE`+(already?' / DOEMO-PCF-DIRECT-V1':''),visibleBounds:[x-9.92125,1190.55-y+9.92125,x+9.92125,1190.55-y-9.92125],remove(){events.push('remove-old-'+id);}});
  }
  const doc={groupItems:[...old,{name:'other',note:'DOEMO Animalis / position 8 /',remove(){throw Error('Other equipment must stay');}}],saveAs(){events.push('save');if(failSave)throw Error('disk full');}};
  function File(path){return {exists:true,length:text.length,parent:{fsName:'/assets'},open(){return true;},read(){return text+(badModel?' BAD':'');},close(){}};}
  File.saveDialog=()=>({name:'corrected.ai',fsName:'/output/corrected.ai',exists:false});
  const forbidden=()=>{throw Error('External import or clipboard forbidden');};
  const app={documents:[doc],activeDocument:doc,coordinateSystem:'old',open:forbidden,copy:forbidden,paste:forbidden,redraw(){}};
  vm.runInNewContext(script,{app,File,$:{fileName:'/assets/script.jsx'},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:1},CMYKColor:function(){},StrokeJoin:{MITERENDJOIN:1},ZOrderMethod:{BRINGTOFRONT:1},IllustratorSaveOptions:function(){},alert:m=>alerts.push(m)});
  return {events,alerts,created,old,app};
}
test('creates nine source paths in each target group, identified by note even when names are empty',()=>{
  const r=run();assert.equal(r.created.length,2);
  for(let i=0;i<2;i++) {
    const g=r.created[i];assert.equal(g.pathItems.length,9);
    assert.match(g.note,/DOEMO-PCF-DIRECT-V1/);
    g.visibleBounds.forEach((n,j)=>assert.ok(Math.abs(n-r.old[i].visibleBounds[j])<1e-6));
    assert.equal(g.pathItems[0].fillColor.magenta,91.5);
  }
  assert.deepEqual(r.events,['remove-old-13','remove-old-14','save']);assert.equal(r.app.coordinateSystem,'old');
  if(process.env.DOEMO_PCF_DRAW_OUTPUT)fs.writeFileSync(process.env.DOEMO_PCF_DRAW_OUTPUT,JSON.stringify(r.created[0].pathItems));
});
test('invalid model and native path failure preserve the original two symbols',()=>{
  for(const options of [{badModel:true},{failPath:true}]) {
    const r=run(options);assert.deepEqual(r.events,['remove-new']);assert.match(r.alerts[0],/existants sont conserves/);
  }
});
test('save failure keeps the corrected artwork open with explicit instructions',()=>{
  const r=run({failSave:true});assert.deepEqual(r.events,['remove-old-13','remove-old-14','save']);assert.match(r.alerts[0],/corrections restent ouvertes/);
});
test('already corrected groups are left unchanged',()=>{
  const r=run({already:true});assert.deepEqual(r.events,[]);assert.equal(r.created.length,0);assert.match(r.alerts[0],/deja/);
});
