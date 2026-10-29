/* Exercise exporter traversal and raw-source contract, not Adobe save/reopen. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const filename=require('node:path').resolve(__dirname,'../illustrator/DOEMO-Exporter-Circulations.jsx');
const node=(x,y)=>[x,y,x,y,x,y];
const path={type:'PathItem',name:'',nodes:[node(10,10),node(90,90)],closed:false,filled:true,fill:['GrayColor',100],stroked:false,width:0,children:[]};
let result,alerts=[];
const inventory={artboards:[[0,100,100,0]],color_space:'RGB',layers:[{name:'Plan brut',visible:true,items:[path,{...path,guides:true},{type:'TextFrame',name:'',bounds:[10,80,40,60],text:'Couloir',children:[]},{type:'CompoundPathItem',name:'',children:[{...path,closed:true}]},{type:'GroupItem',name:'',clipped:true,children:[path]}],layers:[]}]};
const app={version:'28.0',documents:[{}],coordinateSystem:'original',activeDocument:{saved:true,fullName:{name:'raw.ai',fsName:'/local/raw.ai'}}};
function File(path){return {parent:'/scripts',name:path};}
File.saveDialog=()=>({name:'source.json'});
vm.runInNewContext(fs.readFileSync(filename,'utf8').replace(/^#target.*\n/,''),{
 app,File,$:{fileName:filename,evalFile(){}},CoordinateSystem:{DOCUMENTCOORDINATESYSTEM:'document'},
 DOEMO:{sha256:()=> '1'.repeat(64)},DOEMO_CIRC_NATIVE:{preflight(){},inventory:()=>inventory,read:()=>'',hash:()=> '2'.repeat(64),write:(_,v)=>{result=v;}},alert:s=>alerts.push(s)
});
assert.ok(result,'Raw source without footprints must be exported');
assert.equal(result.levels.length,0);
assert.equal(result.paths.length,3,'Native guides are excluded; compound and clipped paths are quarantined');
assert.equal(result.paths[0].filled,true);
assert.equal(result.paths[0].role,'unknown');
assert.equal(result.paths[1].clipped,true);
assert.equal(result.paths[2].clipped,true);
assert.equal(result.texts[0].level,'');
assert.equal(result.texts[0].text,'Couloir');
assert.equal(result.source_sha256,'1'.repeat(64));
assert.equal(app.coordinateSystem,'original');
assert.ok(alerts[0].includes('Géométrie exportée'));
console.log('Extraction brute vérifiée avec inventaire simulé ; exécution Adobe toujours requise.');
