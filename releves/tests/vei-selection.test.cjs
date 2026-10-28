const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync(__dirname + '/../illustrator/DOEMO-VEI-selection.jsx', 'utf8').replace(/^#target.*\n/, '');

function run({selected=true, exists=false, failPaste=false}={}) {
  const events=[], alerts=[];
  const source={selection:selected?[{}]:[], documentColorSpace:'RGB',activate(){events.push('source-activate');},close(){throw Error('Original must stay open');}};
  const file={name:'VEI.ai',fsName:'/tmp/VEI.ai',exists};
  const result={selection:[{}],artboards:[{artboardRect:[0,100,100,0]}],pageItems:[{}],activate(){},fitArtboardToSelectedArt(){return true;},saveAs(){events.push('save');},close(){events.push('close-result');}};
  const documents=[source];documents.add=()=>{events.push('new');return result;};
  const context={app:{documents,activeDocument:source,copy(){events.push('copy');},paste(){events.push('paste');if(failPaste)throw Error("1346458189 ('MRAP')");},redraw(){},open(){events.push('reopen');return result;}},File:{saveDialog(){return file;}},IllustratorSaveOptions:function(){},SaveOptions:{DONOTSAVECHANGES:0},alert:m=>alerts.push(m)};
  vm.runInNewContext(script,context);
  return {events,alerts};
}

test('copies the selected artwork and never closes the user source document',()=>{
  const r=run();assert.deepEqual(r.events,['source-activate','copy','new','paste','save','close-result','reopen']);
  assert.match(r.alerts[0],/enregistre et rouvert/);
});
test('reports the failing Illustrator stage without saving an incomplete extraction',()=>{
  const r=run({failPaste:true});assert.match(r.alerts[0],/Collage des objets natifs/);
  assert.match(r.alerts[0],/MRAP/);assert.ok(!r.events.includes('save'));
});
test('empty selection and existing output cannot overwrite or create a document',()=>{
  for(const options of [{selected:false},{exists:true}]){const r=run(options);assert.deepEqual(r.events,[]);assert.equal(r.alerts.length,1);}
});
