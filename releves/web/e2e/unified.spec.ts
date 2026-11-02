import { test, expect } from "@playwright/test";
import { spawn, execFileSync, ChildProcess } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createServer } from "node:net";

// Synthetic sources and a small vector asset only. No production account,
// model, remote worker or customer document participates in this recipe.
const python =
  process.env.DOEMO_TEST_PYTHON ||
  "/workspace/.doemo-tools/unified-python/bin/python";
const root = mkdtempSync(tmpdir() + "/doemo-unified-e2e-");
const env = {
  ...process.env,
  PYTHONPATH: resolve("../backend"),
  DOEMO_RELEVES_DATA: root,
  DOEMO_RELEVES_DIST: resolve("../dist"),
  DOEMO_RUNPOD_MANAGED: "0",
  DOEMO_RUNPOD_ENDPOINT: "",
  DOEMO_RUNPOD_TOKEN: "",
  DOEMO_STRUCTURE_PYTHON: python,
  DOEMO_STRUCTURE_MODULE_PATH: resolve(root, "structure-fixture"),
};
let origin: string;
let server: ChildProcess;
let serverErrors = "";

test.beforeAll(async () => {
  // Test-only engine double: exercise the real queue, isolated engine adapter,
  // provenance and apply contract, without claiming recognition quality.
  const module = resolve(
    env.DOEMO_STRUCTURE_MODULE_PATH,
    "doemo_reconstruction",
  );
  mkdirSync(module, { recursive: true });
  writeFileSync(resolve(module, "__init__.py"), "");
  writeFileSync(
    resolve(module, "extract.py"),
    `
import hashlib
from pathlib import Path
from PIL import Image
def reconstruct(source, pages=None):
    with Image.open(source) as image:
        width,height=image.size
    return {'source':{'sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest()},
        'models':{'segmentation':'not_configured'},'levels':[{'source_page':1,'unit':'px',
        'width':width,'height':height,'walls':[{'id':'fixture-wall','a':[width*.3,height*.7],
        'b':[width*.75,height*.7],'thickness':4,'openings':[],'status':'approved',
        'method':'synthetic_contract_fixture','confidence':.75}]}]}
`,
  );
  const listener = createServer();
  await new Promise<void>((done) => listener.listen(0, "127.0.0.1", done));
  const port = (listener.address() as { port: number }).port;
  await new Promise<void>((done) => listener.close(() => done()));
  origin = `http://127.0.0.1:${port}`;
  execFileSync(
    python,
    [
      "-c",
      `
import hashlib
from pathlib import Path
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from doemo_releves.store import Store
from doemo_releves.auth import password_hash
s=Store(${JSON.stringify(root)})
with s.connect() as c:
    for login in ('unified-designer','other-designer'):
        c.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)', (login,password_hash('only-a-synthetic-test-password'),'dessinateur'))
folder=s.root/'libraries'/'test-library';folder.mkdir(parents=True)
writer=PdfWriter();page=writer.add_blank_page(width=30,height=20)
stream=DecodedStreamObject();stream.set_data(b'1 0 0 rg 0 0 30 20 re f')
page[NameObject('/Contents')]=writer._add_object(stream)
with (folder/'symbol.ai').open('wb') as f:writer.write(f)
content=(folder/'symbol.ai').read_bytes()
Image.new('RGB',(60,40),'red').save(folder/'asset-native.png')
s.put_library({'id':'test-library','name':'Bibliothèque de test','archive_verified':True,'warnings':[],
    'assets':[{'id':'asset-native','name':'Extincteur de test','type':'application/vnd.adobe.element.image+dcx',
    'groups':['Incendie'],'verified':True,'approved':True,'pictogram_candidate':True,'preview':True,
    'components':[{'role':'primary','type':'application/illustrator','archive_path':'symbol.ai',
    'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content)}]}]})
`,
    ],
    { env },
  );
  server = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "doemo_releves.auth:standalone",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--no-access-log",
    ],
    {
      env: { ...env, DOEMO_PUBLIC_ORIGIN: origin },
      stdio: "pipe",
    },
  );
  server.stderr?.on("data", (part) => {
    serverErrors = (serverErrors + part).slice(-4000);
  });
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(origin + "/releves/")).ok) return;
    } catch {}
    await new Promise((done) => setTimeout(done, 100));
  }
  throw Error("Serveur synthétique indisponible : " + serverErrors);
});

test.afterAll(async () => {
  server?.kill();
  if (server && server.exitCode === null)
    await new Promise((done) => {
      server.once("exit", done);
      setTimeout(done, 3000);
    });
  rmSync(root, { recursive: true, force: true });
});

test("unified source keeps walls and native equipment aligned through crop, rotation, undo, save and PDF export", async ({
  page,
  playwright,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(origin + "/releves/?workspace=unified");
  await page
    .getByLabel("Identifiant", { exact: true })
    .fill("unified-designer");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill("only-a-synthetic-test-password");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await expect(page.getByText("Déposez votre relevé ici")).toBeVisible();
  await expect(page.locator(".dashboard")).toHaveCount(0);

  const png = execFileSync(
    python,
    [
      "-c",
      "import io,sys;from PIL import Image;b=io.BytesIO();Image.new('RGB',(1200,800),'white').save(b,'PNG');sys.stdout.buffer.write(b.getvalue())",
    ],
    { env },
  );
  await page.getByLabel("Importer des relevés", { exact: true }).setInputFiles({
    name: "source-synthetique.png",
    mimeType: "image/png",
    buffer: png,
  });
  const canvas = page.getByTestId("plan-canvas").locator("svg").first();
  await expect(canvas).toBeVisible();
  await page.getByLabel("Dessiner un mur", { exact: true }).click();
  const bounds = (await canvas.boundingBox())!;
  await page.mouse.move(
    bounds.x + 0.2 * bounds.width,
    bounds.y + 0.3 * bounds.height,
  );
  await page.mouse.down();
  await page.mouse.move(
    bounds.x + 0.65 * bounds.width,
    bounds.y + 0.3 * bounds.height,
    { steps: 8 },
  );
  await page.mouse.up();
  await expect(canvas.locator("g[data-wall-id]").first()).toBeAttached();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  const projectId = await page
    .getByLabel("Projet", { exact: true })
    .inputValue();
  let project = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(project.state.structure_pages).toHaveLength(1);
  const structure = project.state.structure_pages[0];
  expect(structure.walls).toHaveLength(1);
  const originalWall = structuredClone(structure.walls[0]);
  const document = project.documents[0];
  expect(structure.source_document_id).toBe(document.id);
  expect(structure.source_sha256).toBe(document.sha256);
  expect(structure.walls[0].a[0] / structure.width).toBeCloseTo(0.2, 2);
  expect(structure.walls[0].a[1] / structure.height).toBeCloseTo(0.3, 2);

  // Deliberately place the equipment at the wall endpoint, not at its text box.
  // This exact known fixture lets the browser verify one common coordinate frame.
  const anchor = {
    x: originalWall.a[0] / structure.width,
    y: originalWall.a[1] / structure.height,
  };
  project.state.library_id = "test-library";
  project.state.floors = [
    {
      id: "level-rdc",
      name: "RDC test",
      target_page: 1,
      artboard_index: 0,
      source_document_id: document.id,
      source_page: 1,
      source_region: { x: 0.05, y: 0.05, w: 0.9, h: 0.9 },
      rotation_deg: 0,
      confirmed: false,
    },
  ];
  project.state.annotations = [
    {
      id: "equipment-native",
      source_document_id: document.id,
      source_page: 1,
      bbox: { x: 0.3, y: 0.4, w: 0.08, h: 0.05 },
      anchor,
      anchor_kind: "manual",
      text: "EXT",
      equipment_type: "EXT_PORTATIF",
      asset_id: "asset-native",
      floor_id: "level-rdc",
      rotation_deg: 90,
      size_mm: 12,
      status: "review",
    },
  ];
  const install = await page.request.put(
    origin + `/api/projects/${projectId}/state`,
    { headers: { Origin: origin }, data: project.state },
  );
  expect(install.ok(), await install.text()).toBeTruthy();
  await page.reload();
  await expect(canvas.locator("g[data-wall-id]").first()).toBeAttached();
  await page
    .locator(".document-rail")
    .getByRole("button", { name: "RDC test →", exact: true })
    .click();
  await page.getByTitle("Tourner le niveau", { exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  project = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(project.state.floors[0].rotation_deg).toBe(90);
  expect(project.state.structure_pages[0].walls[0].a).toEqual(originalWall.a);
  expect(project.state.annotations[0].anchor).toEqual(anchor);

  // The wall and anchor share the same screen transform after crop and rotation.
  const alignment = await canvas.evaluate(
    (svg, point) => {
      const wall = svg.querySelector("[data-wall-id]") as SVGGraphicsElement;
      const circle = svg.querySelector(
        '[data-anchor="true"] circle',
      ) as SVGCircleElement;
      const wm = wall.getScreenCTM()!;
      const cm = circle.getScreenCTM()!;
      const p = new DOMPoint(point.x, point.y).matrixTransform(wm);
      const q = new DOMPoint(
        circle.cx.baseVal.value,
        circle.cy.baseVal.value,
      ).matrixTransform(cm);
      return Math.hypot(p.x - q.x, p.y - q.y);
    },
    {
      x: anchor.x * document.pages[0].width,
      y: anchor.y * document.pages[0].height,
    },
  );
  expect(alignment).toBeLessThan(1);

  await page
    .getByLabel("Choisir un mur", { exact: true })
    .selectOption(originalWall.id);
  await page
    .getByLabel("Départ X", { exact: true })
    .fill(String(originalWall.a[0] + 20));
  await page
    .getByRole("button", { name: "Appliquer les coordonnées", exact: true })
    .click();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  const moved = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(moved.state.structure_pages[0].walls[0].a[0]).toBeCloseTo(
    originalWall.a[0] + 20,
    4,
  );
  expect(moved.state.annotations[0].anchor).toEqual(anchor);
  await page.getByLabel("Annuler", { exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  await page.reload();
  await expect(canvas.locator("g[data-wall-id]").first()).toBeAttached();
  const restored = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(restored.state.structure_pages[0].walls[0].a).toEqual(originalWall.a);
  expect(restored.state.annotations[0].anchor).toEqual(anchor);

  await page
    .getByLabel("Largeur imprimée de la page (mm)", { exact: true })
    .fill("297");
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exporter le PDF commun", exact: true })
    .click();
  const pdf = await downloadEvent;
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/i);
  const pdfPath = await pdf.path();
  expect(pdfPath).toBeTruthy();
  expect(readFileSync(pdfPath!).subarray(0, 5).toString()).toBe("%PDF-");
  const check = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        `
import json,sys
from pypdf import PdfReader
r=PdfReader(sys.argv[1]);p=r.pages[0]
content=p.get_contents().get_data()
forms=[v.get_object() for v in p.get('/Resources',{}).get('/XObject',{}).values()]
report=json.loads(r.attachments['doemo-plan-unifie.json'][0])
print(json.dumps({'pages':len(r.pages),'width_pt':float(p.mediabox.width),'height_pt':float(p.mediabox.height),
 'images':len(p.images),'vector_rectangle':b're' in content,
 'contains_red_asset':any(b'1 0 0 rg' in f.get_data() for f in forms if f.get('/Subtype')=='/Form'),
 'placements':report['placements'],'unresolved':report['unresolved']}))
`,
        pdfPath!,
      ],
      { env },
    ).toString(),
  );
  expect(check.pages).toBe(1);
  expect(check.width_pt).toBeCloseTo((297 * 72) / 25.4, 3);
  expect(check.height_pt / check.width_pt).toBeCloseTo(800 / 1200, 4);
  expect(check.images).toBe(0);
  expect(check.contains_red_asset).toBeTruthy();
  expect(check.unresolved).toEqual([]);
  expect(check.placements).toHaveLength(1);
  const placement = check.placements[0];
  expect(placement.status).toBe("original_resource");
  const [m0, m1, m2, m3, m4, m5] = placement.resource_to_page_matrix;
  expect(m0 * 15 + m2 * 10 + m4).toBeCloseTo(anchor.x * check.width_pt, 5);
  expect(m1 * 15 + m3 * 10 + m5).toBeCloseTo(
    (1 - anchor.y) * check.height_pt,
    5,
  );
  expect(Math.hypot(m0, m1) * 30).toBeCloseTo((12 * 72) / 25.4, 5);
  await page.screenshot({
    path:
      process.env.DOEMO_UNIFIED_SCREENSHOT || "/workspace/unified-review.png",
    fullPage: true,
  });

  // One UI action must create independent jobs for exactly the same source.
  const submissions: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url() === origin + `/api/projects/${projectId}/jobs`
    )
      submissions.push(request.postDataJSON());
  });
  await page
    .getByRole("button", { name: "Analyser murs et relevé", exact: true })
    .click();
  await expect.poll(() => submissions.length).toBe(2);
  expect(submissions.map((request) => request.engine).sort()).toEqual([
    "local",
    "structure",
  ]);
  expect(
    submissions.every(
      (request) => request.document_id === document.id && request.page === 1,
    ),
  ).toBeTruthy();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(origin + `/api/projects/${projectId}/jobs`)
          ).json()
        ).length,
    )
    .toBe(2);
  const queued = await (
    await page.request.get(origin + `/api/projects/${projectId}/jobs`)
  ).json();
  expect(
    queued.every((job: { status: string }) => job.status === "queued"),
  ).toBeTruthy();

  // Only recognition itself is substituted; actual job claiming, SQLite state,
  // subprocess structure frame checks and protected apply routes are exercised.
  execFileSync(
    python,
    [
      "-c",
      `
from unittest.mock import patch
from doemo_releves.store import Store
from doemo_releves.queue import process_one
from doemo_releves.models import Annotation
def local_fixture(operation, data, *args, **kwargs):
    assert operation=='recognition'
    annotation=Annotation(id='fixture-observation',source_document_id=data['document_id'],source_page=data['page'],
        bbox={'x':.65,'y':.65,'w':.1,'h':.04},anchor={'x':.7,'y':.7},anchor_kind='manual',
        text='DM test de contrat',equipment_type='DM',method='synthetic_contract_fixture',confidence=.8)
    return {'annotations':[annotation.model_dump()],'report':{'warnings':['Résultat synthétique de test du contrat, pas une mesure de reconnaissance.']}}
store=Store(${JSON.stringify(root)})
with patch('doemo_releves.worker.run_job',side_effect=local_fixture):
    assert process_one(store)
    assert process_one(store)
    assert not process_one(store)
`,
    ],
    { env },
  );
  const completed = await (
    await page.request.get(origin + `/api/projects/${projectId}/jobs`)
  ).json();
  expect(
    completed.every((job: { status: string }) => job.status === "completed"),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Analyses IA", exact: true }).click();
  const wallJob = page
    .locator(".job-card")
    .filter({ hasText: "1 murs proposés" });
  const annotationJob = page
    .locator(".job-card")
    .filter({ hasText: "1 observations localisées" });
  await expect(wallJob).toBeVisible({ timeout: 10000 });
  await wallJob
    .getByRole("button", { name: "Ajouter à la revue", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(origin + `/api/projects/${projectId}`)
          ).json()
        ).state.structure_pages[0].walls.length,
    )
    .toBe(2);
  await annotationJob
    .getByRole("button", { name: "Ajouter à la revue", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(origin + `/api/projects/${projectId}`)
          ).json()
        ).state.annotations.length,
    )
    .toBe(2);
  const applied = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(
    applied.state.structure_pages[0].walls.find(
      (wall: { id: string }) => wall.id === originalWall.id,
    ),
  ).toEqual(restored.state.structure_pages[0].walls[0]);
  expect(
    applied.state.annotations.find(
      (item: { id: string }) => item.id === "equipment-native",
    ),
  ).toEqual(restored.state.annotations[0]);
  expect(applied.state.structure_pages[0].analysis_ids).toHaveLength(1);
  expect(
    applied.state.structure_pages[0].walls.find(
      (wall: { method: string }) =>
        wall.method === "synthetic_contract_fixture",
    ).status,
  ).toBe("pending");

  // Replaying either completed job is idempotent and cannot erase manual work.
  const wallReplay = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/apply"),
  );
  await wallJob
    .getByRole("button", { name: "Ajouter à la revue", exact: true })
    .click();
  expect((await wallReplay).status()).toBe(200);
  const annotationReplay = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/apply"),
  );
  await annotationJob
    .getByRole("button", { name: "Ajouter à la revue", exact: true })
    .click();
  expect((await annotationReplay).status()).toBe(200);
  const replayed = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(replayed.state).toEqual(applied.state);
  const common = await (
    await page.request.get(
      origin + `/api/projects/${projectId}/structured-export`,
    )
  ).json();
  expect(common.project.state.structure_pages[0].walls).toHaveLength(2);
  expect(common.project.state.annotations).toHaveLength(2);

  // The standalone gate derives actor from the cookie, never spoofed headers.
  const other = await playwright.request.newContext({ baseURL: origin });
  expect(
    (
      await other.get(`/api/projects/${projectId}`, {
        headers: {
          "X-Doemo-User": "unified-designer",
          "X-Doemo-Role": "admin",
        },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await other.post("/session", {
        headers: { Origin: origin },
        data: {
          login: "other-designer",
          password: "only-a-synthetic-test-password",
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await other.get(
        `/api/projects/${projectId}/unified-export?document_id=${document.id}&page=1`,
      )
    ).status(),
  ).toBe(404);
  await other.dispose();
  expect(errors).toEqual([]);
});
