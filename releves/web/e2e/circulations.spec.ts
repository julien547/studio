import {test,expect} from '@playwright/test';
import {spawn,execFileSync,type ChildProcess} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
const python=process.env.DOEMO_TEST_PYTHON||'/workspace/.venvs/studio-releves/bin/python',root=mkdtempSync(tmpdir()+'/doemo-circulations-'),origin='http://127.0.0.1:18084';
let server:ChildProcess;
test.beforeAll(async()=>{
 execFileSync(python,['-c',`from doemo_releves.store import Store
from doemo_releves.auth import password_hash
s=Store(${JSON.stringify(root)})
with s.connect() as c:c.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)',('designer',password_hash('local-test-password-only'),'dessinateur'))`]);
 server=spawn(python,['-m','uvicorn','doemo_releves.auth:standalone','--factory','--host','127.0.0.1','--port','18084','--no-access-log'],{env:{...process.env,DOEMO_RELEVES_DATA:root,DOEMO_PUBLIC_ORIGIN:origin,DOEMO_RELEVES_DIST:resolve('../dist'),DOEMO_RUNPOD_MANAGED:'0'},stdio:'pipe'});
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/circulations')).ok)return;}catch{}await new Promise(r=>setTimeout(r,100));}throw Error('Serveur local indisponible');
});
test.afterAll(async()=>{if(server){const end=new Promise(r=>server.once('exit',r));server.kill();await end;}rmSync(root,{recursive:true,force:true});});
test('vector review preserves exclusions, history and approved colour before Illustrator export',async({page})=>{
 await page.goto(origin+'/circulations');await page.getByLabel('Identifiant',{exact:true}).fill('designer');await page.getByLabel('Mot de passe',{exact:true}).fill('local-test-password-only');await page.getByRole('button',{name:'Se connecter',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Vert des circulations'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Vert des circulations'})).toBeVisible();
 const created=await page.evaluate(async()=>{const r=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Fixture circulations'})});return r.json();});
 await page.reload();await page.getByLabel('Projet',{exact:true}).selectOption(created.id);
 const nodes=(ps:number[][])=>ps.map(p=>[...p,...p,...p]);
 const source={schema_version:'doemo.circulations-source/1',provider:'illustrator',document_id:'browser-fixture',source_name:'fixture.ai',source_sha256:'1'.repeat(64),architecture_sha256:'2'.repeat(64),units:'pt',coordinate_system:'illustrator_document_y_up',color_space:'RGB',artboards:[[0,100,100,0]],levels:[{id:'rdc',name:'RDC',artboard:0,footprint:{shell:[[0,0],[100,0],[100,100],[0,100]],holes:[]}}],paths:[{id:'divider',role:'wall',nodes:nodes([[40,0],[40,100]]),stroke_width:2}],texts:[{text:'Couloir',point:[15,50],level:'rdc'},{text:'Bureau',point:[65,50],level:'rdc'}]};
 await page.getByLabel('Géométrie Illustrator',{exact:true}).setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(source))});
 await expect(page.getByText(/2 régions/)).toBeVisible();
 await page.locator('svg[aria-label="Plan et régions"] path').filter({has:page.locator('title',{hasText:'Circulation :'} )}).click();
 await page.getByRole('button',{name:'Ceci est une circulation',exact:true}).click();
 await expect(page.getByText(/révision 1/)).toBeVisible();
 await page.getByRole('button',{name:'Annuler',exact:true}).click();await expect(page.getByText(/révision 2/)).toBeVisible();
 await page.getByRole('button',{name:'Rétablir',exact:true}).click();await expect(page.getByText(/révision 3/)).toBeVisible();
 await page.getByLabel('Composantes couleur').fill('160,190,130');await page.getByRole('button',{name:'Valider la nuance',exact:true}).click();
 await expect(page.getByText('Nuance de sortie validée',{exact:true})).toBeVisible();
 const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Préparer la copie Illustrator'}).click();expect((await downloaded).suggestedFilename()).toBe('circulations-validees.json');
 await page.reload();await page.getByLabel('Projet',{exact:true}).selectOption(created.id);await page.getByLabel('Document enregistré').selectOption('browser-fixture');await expect(page.getByText('Nuance de sortie validée',{exact:true})).toBeVisible();
});

test('raw AI geometry can be qualified in the page without named Illustrator layers',async({page})=>{
 await page.goto(origin+'/circulations');await page.getByLabel('Identifiant',{exact:true}).fill('designer');await page.getByLabel('Mot de passe',{exact:true}).fill('local-test-password-only');await page.getByRole('button',{name:'Se connecter',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Vert des circulations'})).toBeVisible();
 const created=await page.evaluate(async()=>{const r=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Raw circulation fixture'})});return r.json();});
 await page.reload();await page.getByLabel('Projet',{exact:true}).selectOption(created.id);
 const nodes=(ps:number[][])=>ps.map(p=>[...p,...p,...p]);
 const source={schema_version:'doemo.circulations-source/1',provider:'illustrator',document_id:'raw-fixture',source_name:'raw.ai',source_sha256:'3'.repeat(64),architecture_sha256:'4'.repeat(64),units:'pt',coordinate_system:'illustrator_document_y_up',color_space:'RGB',artboards:[[0,100,100,0]],levels:[],paths:[{id:'outline',role:'unknown',nodes:nodes([[5,5],[95,5],[95,95],[5,95]]),closed:true,stroke:['GrayColor',100],stroke_width:.2},{id:'divider',role:'unknown',nodes:nodes([[40,5],[40,95]]),stroke:['GrayColor',100],stroke_width:2}],texts:[{text:'Couloir',point:[15,50],level:''},{text:'Bureau',point:[65,50],level:''}]};
 await page.getByLabel('Géométrie Illustrator',{exact:true}).setInputFiles({name:'raw.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(source))});
 await expect(page.getByText(/0 régions/)).toBeVisible();
 await expect(page.locator('svg[aria-label="Plan et régions"]')).toHaveAttribute('viewBox','0 -100 100 100');
 await page.getByRole('button',{name:'Proposer les tracés à vérifier',exact:true}).click();
 await page.getByLabel('Proposition à examiner').selectOption('outline:0');
 await expect(page.locator('[data-path-id="outline"]')).toHaveAttribute('stroke','#6843da');
 await page.getByRole('button',{name:'Utiliser le contour sélectionné comme emprise',exact:true}).click();
 await expect(page.getByText(/1 régions/)).toBeVisible();
 await page.getByText('Préparer les murs et les niveaux',{exact:true}).click();
 await page.getByRole('button',{name:'Sélectionner des tracés',exact:true}).click();
 await page.locator('svg[aria-label="Plan et régions"]').scrollIntoViewIfNeeded();
 const click=await page.locator('[data-path-id="divider"]').evaluate((element)=>{const p=element as SVGPathElement;const point=p.getPointAtLength(p.getTotalLength()/2).matrixTransform(p.getScreenCTM()!);return {x:point.x,y:point.y};});
 await page.mouse.click(click.x,click.y);await expect(page.locator('[data-path-id="divider"]')).toHaveAttribute('stroke','#6843da');
 await page.getByLabel('Rôle confirmé').selectOption('wall');
 await page.getByRole('button',{name:'Confirmer le rôle des tracés',exact:true}).click();
 await expect(page.getByText(/2 régions/)).toBeVisible();
 await page.getByRole('button',{name:'Annuler',exact:true}).click();await expect(page.getByText(/1 régions/)).toBeVisible();
 await page.getByRole('button',{name:'Rétablir',exact:true}).click();await expect(page.getByText(/2 régions/)).toBeVisible();
 const stored=await page.evaluate(async(url)=>{return (await fetch(url)).json();},'/api/projects/'+created.id+'/circulations/raw-fixture');
 expect(stored.source.source_sha256).toBe(source.source_sha256);expect(stored.source.architecture_sha256).toBe(source.architecture_sha256);
 expect(stored.source.paths[1].nodes).toEqual(source.paths[1].nodes);expect(stored.regions.map((r:{category:string})=>r.category).sort()).toEqual(['circulation','room']);
});
