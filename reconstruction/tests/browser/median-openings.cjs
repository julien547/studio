// Synthetic browser acceptance test: no client document or GPU model is used.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const wall=(id,a,b,openings=[])=>({id,kind:'wall',a,b,thickness:4,status:'approved',confidence:0,method:'manual',evidence:[],openings});
const opening=(start,end,kind='door')=>({start,end,kind,status:'approved'});
const doc=walls=>({schema:'doemo.architecture/1',revision:0,history:[],source:{sha256:'a'.repeat(64)},levels:[{id:'L',source_page:1,name:'Test synthétique',width:200,height:100,unit:'pt',coordinate:{},scale:null,floor_validated:false,reference:'',walls}]});
(async()=>{
 // Serve only the generated editor and a synthetic harness, never project data.
 const editor=fs.readFileSync(path.resolve(__dirname,'../../../redessin/editor.js'));
 const server=http.createServer((request,response)=>{
  if(request.url==='/'){response.setHeader('Content-Type','text/html; charset=utf-8');response.end('<!doctype html><meta charset="utf-8"><div id="host"></div><script src="/editor.js"></script>')}
  else if(request.url==='/editor.js'){response.setHeader('Content-Type','application/javascript');response.end(editor)}
  else {response.statusCode=404;response.end()}
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)});
 let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.DOEMO_TEST_CHROMIUM||undefined,headless:true});
  const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const mount=walls=>page.evaluate(d=>window.doemoEditor.mount(document.querySelector('#host'),d,'Dessinateur',()=>{}),doc(walls));
  const get=()=>page.evaluate(()=>window.doemoEditor.document());
  const pairMerge=async()=>{await page.locator('#axisPairs').selectOption('0');await page.locator('#mergeAxisPair').click()};
  await mount([wall('first',[10,20],[110,20],[opening(.2,.4)]),wall('second',[110,24],[10,24],[opening(.6,.8)])]);
  await pairMerge();let d=await get();
  assert.equal(d.levels[0].walls.length,1);assert.equal(d.levels[0].walls[0].openings.length,1);
  assert.equal(d.levels[0].walls[0].openings[0].status,'pending');
  assert.match(await page.locator('#openingReview').textContent(),/1 ouverture\(s\) à contrôler/);
  await page.locator('#approve').click();assert.equal((await get()).revision,1);
  assert.match(await page.locator('#message').textContent(),/Ouvertures non validées/);
  await page.locator('#undo').click();assert.equal((await get()).levels[0].walls.length,2);
  await page.locator('#redo').click();assert.equal((await get()).levels[0].walls[0].openings[0].status,'pending');
  // Reopen exactly the serialized project, including source-opening evidence.
  const serialized=JSON.parse(JSON.stringify(await get()));
  await page.evaluate(d=>window.doemoEditor.mount(document.querySelector('#host'),d,'Dessinateur',()=>{}),serialized);
  await page.locator('g[data-id] path').last().click({force:true});
  await page.locator('#approveOpening').click();d=await get();
  assert.equal(d.levels[0].walls[0].status,'pending');assert.equal(d.levels[0].walls[0].openings[0].status,'approved');
  await page.locator('#approve').click();
  const download=page.waitForEvent('download');await page.locator('#svgExport').click();
  const svg=fs.readFileSync(await (await download).path(),'utf8');
  assert.equal((svg.match(/<path /g)||[]).length,2);assert.match(svg,/stroke="#000000"/);assert.ok(!svg.includes('<polygon'));
  const paths=[...svg.matchAll(/ d="M ([^"]+)"/g)].map(m=>m[1].split(/[ L]+/).map(Number));
  assert.equal(paths.length,2);assert.ok(Math.abs(paths[0][2]-30)<1e-8);assert.ok(Math.abs(paths[1][0]-50)<1e-8);
  assert.ok(paths.every(p=>p[1]===22&&p[3]===22));
  // Conflicting types remain visible until the user resolves the classification.
  await mount([wall('first',[10,20],[110,20],[opening(.2,.4)]),wall('second',[10,24],[110,24],[opening(.3,.5,'window')])]);
  await pairMerge();assert.match(await page.locator('#openingReview').textContent(),/types différents/);
  assert.equal((await get()).levels[0].walls[0].openings[0].kind,'passage');
  const answer=dialog=>dialog.accept(dialog.message().startsWith('Type')?'door':dialog.message().startsWith('Début')?'0.2':'0.5');
  page.on('dialog',answer);await page.locator('#editOpening').click();page.off('dialog',answer);
  assert.equal((await get()).levels[0].walls[0].openings[0].kind,'door');
  assert.equal((await get()).levels[0].walls[0].openings[0].status,'approved');
  assert.equal((await get()).levels[0].walls[0].status,'pending');
  // A gap crossing the common extent survives on both the median and the tail.
  await mount([wall('first',[0,20],[100,20],[opening(.2,.4),opening(.8,.9,'window')]),wall('second',[30,24],[70,24])]);
  await pairMerge();d=await get();assert.equal(d.levels[0].walls.length,3);
  assert.equal(d.levels[0].walls.reduce((n,w)=>n+w.openings.length,0),3);
  assert.ok(d.levels[0].walls.every(w=>w.openings.every(o=>o.status==='pending')));
  await page.locator('#undo').click();assert.equal((await get()).levels[0].walls[0].openings.length,2);
  await page.locator('#redo').click();assert.equal((await get()).levels[0].walls.length,3);
  // The command is atomic when every part of the overlap is an opening.
  await mount([wall('first',[10,20],[110,20],[opening(0,.5)]),wall('second',[10,24],[110,24],[opening(.5,1)])]);
  await page.locator('g[data-id="first"] path').last().click({force:true});await page.locator('#median').click();
  await page.locator('g[data-id="second"] path').last().click({force:true});
  assert.equal((await get()).revision,0);assert.equal((await get()).levels[0].walls.length,2);
  assert.match(await page.locator('#message').textContent(),/aucune portion pleine/);
  // Diagonal geometry keeps one axis and the same fractional gap.
  await mount([wall('first',[10,10],[60,60],[opening(.25,.5,'window')]),wall('second',[12,8],[62,58])]);
  await pairMerge();d=await get();
  assert.ok(Math.abs(d.levels[0].walls[0].a[0]-11)<1e-8&&Math.abs(d.levels[0].walls[0].a[1]-9)<1e-8);
  assert.ok(Math.abs(d.levels[0].walls[0].openings[0].start-.25)<1e-8);
  assert.deepEqual(errors,[]);
  const report={passed:true,one_median_with_gap:true,opening_validation_required:true,black_svg:true,
    reversed_face:true,type_conflict_visible:true,partial_tails_preserved:true,full_exclusion_refused:true,
    diagonal:true,undo_redo:true,json_reload:true,source_provenance:true,real_gpu_inference:false,errors};
  console.log(JSON.stringify(report));
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve))}
})().catch(e=>{console.error(e);process.exit(1)});
