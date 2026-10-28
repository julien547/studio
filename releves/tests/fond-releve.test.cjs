const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const png = Buffer.from([137,80,78,71,13,10,26,10,0,255,128]);
const script = fs.readFileSync(__dirname+'/../illustrator/DOEMO-Fond-Releve.jsx','utf8')
  .replace(/^#target.*\n/,'').replace('__DOEMO_REGISTERED_PNG_BASE64__',png.toString('base64'));
function run({wrongSize=false,duplicate=false,embedFailure=false,existingOutput=false}={}) {
  const events=[],alerts=[];let written;
  const folder={exists:false,fsName:'/tmp/background',create(){return true;},remove(){events.push('remove-folder');}};
  const temporary={exists:false,fsName:'/tmp/background/releve.png',parent:folder,open(){return true;},
    write(bytes){written=Buffer.from(bytes,'latin1');this.length=written.length;return true;},close(){},remove(){events.push('remove-temp');}};
  const output={exists:existingOutput,fsName:'/out/copy.ai',name:'copy.ai'};
  function File(){return temporary;} File.saveDialog=()=>output;
  function Folder(){return folder;} Folder.temp={fsName:'/tmp'};
  const raster={};
  const item={embed(){events.push('embed');if(embedFailure)throw Error('MRAP');layer.placedItems.length=0;layer.rasterItems.push(raster);}};
  const placed=[];placed.add=()=>{placed.push(item);return item;};
  const layer={placedItems:placed,rasterItems:[],zOrder(method){assert.equal(method,'back');events.push('back');},remove(){events.push('remove-layer');}};
  const layers=duplicate?[{name:'DOEMO - RELEVE DE CONTROLE - NON VALIDE'}]:[];
  layers.add=()=>{events.push('add');layers.push(layer);return layer;};
  const doc={layers,artboards:[{artboardRect:[100,1500,wrongSize?500:941.890991,309.449951]}],saveAs(file){assert.equal(file,output);events.push('save-copy');}};
  const app={version:'28.0',coordinateSystem:'old',documents:[doc],activeDocument:doc,redraw(){}};
  vm.runInNewContext(script,{app,File,Folder,CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:'document'},ZOrderMethod:{SENDTOBACK:'back'},IllustratorSaveOptions:function(){},alert:m=>alerts.push(m)});
  return {events,alerts,layer,raster,written,app};
}
test('embeds bytes below existing artwork, aligns full page, locks background and saves a new AI',()=>{
  const r=run();assert.deepEqual(r.written,png);
  assert.deepEqual(r.events,['add','back','embed','save-copy','remove-temp','remove-folder']);
  assert.equal(r.layer.opacity,45);assert.equal(r.layer.locked,true);
  assert.equal(r.raster.width,841.890991);assert.equal(r.raster.height,1190.550049);
  assert.deepEqual(Array.from(r.raster.position),[100,1500]);assert.equal(r.app.coordinateSystem,'old');
  assert.match(r.alerts[0],/Copie AI enregistree/);
});
test('wrong artboard, duplicate background and existing output stop before modifying the plan',()=>{
  for(const options of [{wrongSize:true},{duplicate:true},{existingOutput:true}]){
    const r=run(options);assert.deepEqual(r.events,[]);assert.equal(r.written,undefined);assert.equal(r.alerts.length,1);
  }
});
test('failed native embedding removes only the new layer and never saves',()=>{
  const r=run({embedFailure:true});assert.ok(!r.events.includes('save-copy'));
  assert.ok(r.events.includes('remove-layer'));assert.ok(r.events.includes('remove-temp'));
  assert.match(r.alerts[0],/Incorporation/);assert.match(r.alerts[0],/MRAP/);
  assert.equal(r.app.coordinateSystem,'old');
});
