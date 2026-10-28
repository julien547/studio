const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(process.env.DOEMO_JSX_TEST_PATH||__dirname+'/../illustrator/DOEMO-Animalis-Pictogrammes.jsx','utf8');
const geometry={Transformation:{CENTER:'center'}};
vm.createContext(geometry);
vm.runInContext(source.slice(source.indexOf('    function circles('),source.indexOf('    try {\n        if(parseInt')),geometry);
function group(vei=false) {
  const g={typename:'GroupItem',visibleBounds:vei?[2,92.0607,40.0408,2]:[0,19.8425,19.8425,0],pageItems:[]};
  if(vei)for(const box of [[34.2128,92.0607,40.0408,86.2327],[2.0001,35.6100,35.6101,2]])
    g.pageItems.push({parent:g,typename:'PathItem',closed:true,clipping:false,pathPoints:[{},{},{},{},{},{},{},{}],geometricBounds:box});
  if(vei) {
    const marker={parent:g,typename:'PathItem',name:'DOEMO_VEI_ANCHOR',geometricBounds:[37.0268,89.2467,37.2268,89.0467]};
    marker.remove=()=>g.pageItems.splice(g.pageItems.indexOf(marker),1);
    g.pageItems.push(marker);
  }
  function transform(s,dx,dy) {
    const b=g.visibleBounds,cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;
    function change(v){return v.map((n,i)=>i%2===0?cx+(n-cx)*s+dx:cy+(n-cy)*s+dy);}
    g.visibleBounds=change(g.visibleBounds);for(const p of g.pageItems)p.geometricBounds=change(p.geometricBounds);
  }
  g.resize=(sx,sy)=>{assert.equal(sx,sy);transform(sx/100,0,0);};
  g.translate=(x,y)=>transform(1,x,y);
  return g;
}
function center(b){return [(b[0]+b[2])/2,(b[1]+b[3])/2];}
function near(a,b){assert.ok(Math.abs(a-b)<1e-6,`${a} vs ${b}`);}
test('VEI uses its small point, not its text bubble; bubble is seven millimetres',()=>{
  const g=group(true);geometry.place(g,[11,'rdc','vei',410.829083,388.763808],[100,1500,941.891,309.45]);
  const point=center(g.pageItems[0].geometricBounds);
  near(point[0],510.829083);near(point[1],1111.236192);near(g.pageItems[1].geometricBounds[2]-g.pageItems[1].geometricBounds[0],7*72/25.4);
  assert.equal(g.pageItems.length,2,'temporary anchor removed, original artwork kept');
  assert.ok(Math.abs(center(g.visibleBounds)[1]-point[1])>10);
});
test('generic extinguisher is centred on the target with seven millimetres size',()=>{
  const g=group();geometry.place(g,[2,'r-1','ext',225.04895,961.717038],[100,1500,941.891,309.45]);
  const p=center(g.visibleBounds);near(p[0],325.04895);near(p[1],538.282962);
  near(g.visibleBounds[2]-g.visibleBounds[0],7*72/25.4);
});
test('VEI without its explicit reference stops instead of guessing an anchor',()=>{
  assert.throws(()=>geometry.circles(group()),/repere temporaire/);
});
test('native paste failure removes only the new layer, closes the opened resource and never saves',()=>{
  const events=[],alerts=[];
  const root={name:'',zOrder(){},remove(){events.push('remove-layer');}};
  const layers=[{name:'DOEMO - RELEVE DE CONTROLE - NON VALIDE'}];
  if(source.includes('COMPLEMENTS PROVISOIRES'))layers.push({name:'DOEMO - PICTOGRAMMES PROVISOIRES - ANIMALIS'});
  layers.add=()=>root;
  const doc={layers,artboards:[{artboardRect:[0,1190.55,841.891,0]}],activate(){},saveAs(){events.push('save');}};
  const assetLayer={typename:'Layer',visible:true,parent:{typename:'Document'}};
  const asset={pageItems:[{typename:'PathItem',parent:assetLayer,geometricBounds:[0,20,20,0]}],artboards:[{}],selection:[],activate(){},close(){events.push('close-asset');}};
  function File(path){return {fsName:path,parent:{fsName:'/assets'},exists:true,name:'source.ai'};}
  File.saveDialog=()=>({name:'new.ai',fsName:'/out/new.ai',exists:false});
  const app={version:'30.8',coordinateSystem:'old',documents:[doc],activeDocument:doc,open(){events.push('open-asset');return asset;},copy(){},paste(){throw Error('MRAP');}};
  vm.runInNewContext(source.replace(/^#target.*\n/,''),{app,File,$:{fileName:'/assets/test.jsx'},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:1},ZOrderMethod:{BRINGTOFRONT:1},SaveOptions:{DONOTSAVECHANGES:1},alert:m=>alerts.push(m)});
  assert.deepEqual(events,['open-asset','remove-layer','close-asset']);
  assert.match(alerts[0],/MRAP/);assert.equal(app.coordinateSystem,'old');
});

if(source.includes('COMPLEMENTS PROVISOIRES')) {
  test('complements contain both PCF doors and the two separately confirmed extinguishers at 8',()=>{
    const rows=JSON.parse(source.match(/var positions\s*=\s*(\[.*?\]);/s)[1]);
    assert.equal(rows.length,7);
    assert.equal(rows.filter(r=>r[2]==='ext').length,4);
    assert.equal(rows.filter(r=>r[2]==='vei').length,1);
    assert.deepEqual(rows.filter(r=>r[2]==='pcf').map(r=>r[1]).sort(),['r-1','rdc']);
    const twins=rows.filter(r=>String(r[0]).startsWith('8-'));
    assert.equal(twins.length,2);
    assert.ok(Math.abs(twins[0][4]-twins[1][4])>7*72/25.4,'7mm symbols must not overlap');
    for(const r of rows)assert.ok(r[3]>0&&r[3]<841.891&&r[4]>0&&r[4]<1190.55);
  });
  test('PCF has its own label and uses the supplied symbol centred at seven millimetres',()=>{
    const g=group();geometry.place(g,[14,'rdc','pcf',269,266],[100,1500,941.891,309.45]);
    near(center(g.visibleBounds)[0],369);near(center(g.visibleBounds)[1],1234);
    near(g.visibleBounds[2]-g.visibleBounds[0],7*72/25.4);
    assert.match(g.name,/Porte coupe-feu/);
  });
}

test('anchor transfer uses the source artboard and the actual clipboard translation',()=>{
  let marker,closed=false;
  const pasted={typename:'GroupItem',pageItems:[],geometricBounds:[102,298.281899,140.0408,208.221199],pathItems:{rectangle(top,left,w,h){marker={geometricBounds:[left,top,left+w,top-h]};return marker;}}};
  const target={selection:null,activate(){}};
  const assetLayer={typename:'Layer',visible:true,parent:{typename:'Document'}};
  const asset={artboards:[{artboardRect:[0,100,41.759,6.221199]}],pageItems:[{typename:'PathItem',parent:assetLayer,geometricBounds:[2,98.281899,40.0408,8.221199]}],selection:[],activate(){},close(){closed=true;}};
  const context={doc:target,source:null,owned:false,sourceSelection:null,root:{groupItems:{add(){return pasted;}}},app:{documents:[],open(){return asset;},copy(){},paste(){target.selection=[{move(){}}];}},ElementPlacement:{PLACEATBEGINNING:1},SaveOptions:{DONOTSAVECHANGES:0}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('    function visible('),source.indexOf('    function circles(')),context);
  context.importNative({name:'VEI.ai',fsName:'/assets/VEI.ai'});
  near(center(marker.geometricBounds)[0],137.12679863);
  near(center(marker.geometricBounds)[1],295.36789704);
  assert.equal(marker.opacity,0);assert.equal(marker.name,'DOEMO_VEI_ANCHOR');assert.ok(closed);
});
