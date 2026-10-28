const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(__dirname+'/../illustrator/DOEMO-Corriger-Deux-PCF.jsx','utf8').replace(/^#target.*\n/,'');
function run({failDuplicate=false,failSave=false,already=false}={}) {
  const events=[],alerts=[],created=[];
  const documentParent={typename:'Document'};
  const root={typename:'Layer',name:'DOEMO - COMPLEMENTS PROVISOIRES - ANIMALIS',visible:true,parent:documentParent};
  function newGroup(parent) {
    const group={typename:'GroupItem',parent,pageItems:[],visibleBounds:[0,20,20,0],remove(){events.push('remove-new');}};
    group.resize=s=>{const b=group.visibleBounds,cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;group.visibleBounds=b.map((n,i)=>(i%2?cy:cx)+(n-(i%2?cy:cx))*s/100);};
    group.translate=(x,y)=>{group.visibleBounds=group.visibleBounds.map((n,i)=>n+(i%2?y:x));};
    created.push(group);return group;
  }
  const old=[];
  for(const [id,x,y] of [[13,141.5,835],[14,269,266]]) {
    const parent={typename:'Layer',name:'floor',visible:true,parent:root};parent.groupItems={add:()=>newGroup(parent)};
    old.push({typename:'GroupItem',parent,name:id+' - Porte coupe-feu - A CONTROLER',note:already?'DOEMO-PCF-CORRIGE':'DOEMO Animalis / position '+id,visibleBounds:[x-9.92125,1190.55-y+9.92125,x+9.92125,1190.55-y-9.92125],remove(){events.push('remove-old-'+id);}});
  }
  const unrelated={name:'8-haut - Extincteur portatif',remove(){throw Error('Other pictograms must stay');}};
  const doc={groupItems:[...old,unrelated],activate(){},saveAs(){events.push('save');if(failSave)throw Error('disk full');}};
  const assetLayer={typename:'Layer',visible:true,parent:documentParent};
  const source={artboards:[{}],rasterItems:[],placedItems:[],pageItems:[],close(){events.push('close-source');}};
  for(let n=0;n<2;n++)source.pageItems.push({typename:'PathItem',parent:assetLayer,duplicate(target){if(failDuplicate&&n===0)throw Error('duplicate failed');target.pageItems.push({typename:'PathItem',shape:'verified PCF',parent:target});}});
  function File(path){return {fsName:path,parent:{fsName:'/assets'},exists:true};}
  File.saveDialog=()=>({name:'corrected.ai',fsName:'/output/corrected.ai',exists:false});
  const app={documents:[doc],activeDocument:doc,coordinateSystem:'old',preferences:{PDFFileOptions:{pageToOpen:7}},open(file){assert.match(file.fsName,/PCF-verifie\.pdf$/);return source;},copy(){throw Error('Clipboard forbidden');},paste(){throw Error('Clipboard forbidden');},redraw(){}};
  vm.runInNewContext(script,{app,File,$:{fileName:'/assets/script.jsx'},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:1},ElementPlacement:{PLACEATBEGINNING:1},Transformation:{CENTER:1},SaveOptions:{DONOTSAVECHANGES:0},IllustratorSaveOptions:function(){},alert:m=>alerts.push(m)});
  return {events,alerts,created,old,app};
}
test('replaces only PCF 13 and 14 with vectors from the verified PDF at their existing centres and sizes',()=>{
  const r=run();assert.equal(r.created.length,2);
  for(let i=0;i<2;i++) {
    assert.equal(r.created[i].pageItems.length,2);
    assert.ok(r.created[i].pageItems.every(p=>p.shape==='verified PCF'));
    r.created[i].visibleBounds.forEach((n,j)=>assert.ok(Math.abs(n-r.old[i].visibleBounds[j])<1e-6));
    assert.match(r.created[i].note,/DOEMO-PCF-CORRIGE/);
  }
  assert.deepEqual(r.events,['close-source','remove-old-13','remove-old-14','save']);
  assert.equal(r.app.preferences.PDFFileOptions.pageToOpen,7);assert.equal(r.app.coordinateSystem,'old');
});
test('native duplication failure keeps both original symbols and removes only the incomplete replacement',()=>{
  const r=run({failDuplicate:true});assert.deepEqual(r.events,['remove-new','close-source']);assert.match(r.alerts[0],/existants sont conserves/);
});
test('save failure leaves corrected artwork open and reports that it still needs saving',()=>{
  const r=run({failSave:true});assert.ok(!r.events.includes('remove-new'));assert.match(r.alerts[0],/corrections restent ouvertes/);
});
test('rerunning on the corrected copy stops without duplicating symbols',()=>{
  const r=run({already:true});assert.equal(r.created.length,0);assert.deepEqual(r.events,[]);assert.match(r.alerts[0],/deja/);
});
