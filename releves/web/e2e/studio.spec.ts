import { test, expect } from "@playwright/test";
import { spawn, execFileSync, ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
const python =
  process.env.DOEMO_TEST_PYTHON ||
  "/workspace/.venvs/studio-releves/bin/python";
const root = mkdtempSync(tmpdir() + "/doemo-studio-e2e-");
const port = 18082,
  origin = `http://127.0.0.1:${port}`;
let server: ChildProcess;
test.beforeAll(async () => {
  execFileSync(python, [
    "-c",
    `from doemo_releves.store import Store
from doemo_releves.auth import password_hash
s=Store(${JSON.stringify(root)})
with s.connect() as c:c.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)',('test-designer',password_hash('test-only-long-password'),'admin'))`,
  ]);
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
      env: {
        ...process.env,
        DOEMO_RELEVES_DATA: root,
        DOEMO_PUBLIC_ORIGIN: origin,
        DOEMO_RELEVES_DIST: resolve("../dist"),
        DOEMO_RUNPOD_MANAGED: "0",
        DOEMO_RUNPOD_POD_ID: "41m7oy6qjaj2ji",
      },
      stdio: "pipe",
    },
  );
  for (let n = 0; n < 100; n++) {
    try {
      if ((await fetch(origin + "/releves/")).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw Error("Serveur de test indisponible");
});
test.afterAll(async () => {
  server?.kill();
  if (server)
    await new Promise((r) => {
      server.once("exit", r);
      setTimeout(r, 3000);
    });
  rmSync(root, { recursive: true, force: true });
});

test("authenticated project, source floors, annotation vs equipment, autosave, undo, persistence, JSON export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(origin + "/releves/");
  await page.getByLabel("Identifiant", { exact: true }).fill("test-designer");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill("test-only-long-password");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Chaque détail compte." }),
  ).toBeVisible();
  const gpuPanel = page.getByRole("region", { name: "Gestion du serveur GPU" });
  await expect(
    gpuPanel.getByRole("button", { name: "Démarrer le GPU" }),
  ).toBeDisabled();
  await expect(
    gpuPanel.getByRole("button", { name: "Arrêter le GPU" }),
  ).toBeDisabled();
  await gpuPanel.getByRole("button", { name: "Détails GPU" }).click();
  await expect(gpuPanel.getByText("Pod : 41m7oy6qjaj2ji")).toBeVisible();
  await expect(gpuPanel.getByText("● Qwen3.5-9B · en attente")).toBeVisible();
  await gpuPanel.getByRole("button", { name: "Masquer", exact: true }).click();
  await page
    .getByRole("button", { name: "＋ Nouveau projet", exact: true })
    .click();
  await page
    .getByLabel("Bâtiment / nom du projet")
    .fill("Animalis · essai navigateur");
  await page.getByLabel("Référence", { exact: true }).fill("E2E-ANIMALIS");
  await page
    .getByRole("button", { name: "Créer le projet", exact: true })
    .click();
  await expect(page.getByText("Déposez votre relevé ici")).toBeVisible();
  const survey = process.env.DOEMO_TEST_SURVEY;
  if (survey)
    await page
      .getByLabel("Importer des relevés", { exact: true })
      .setInputFiles(survey);
  else {
    const png = execFileSync(python, [
      "-c",
      "import io,sys;from PIL import Image;b=io.BytesIO();Image.new('RGB',(1200,850),'white').save(b,'PNG');sys.stdout.buffer.write(b.getvalue())",
    ]);
    await page
      .getByLabel("Importer des relevés", { exact: true })
      .setInputFiles({ name: "plan.png", mimeType: "image/png", buffer: png });
  }
  const canvas = page.getByTestId("plan-canvas").locator("svg").first();
  await expect(canvas).toBeVisible();
  async function drag(x1: number, y1: number, x2: number, y2: number) {
    const b = (await canvas.boundingBox())!;
    await page.mouse.move(b.x + b.width * x1, b.y + b.height * y1);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width * x2, b.y + b.height * y2, {
      steps: 8,
    });
    await page.mouse.up();
  }
  await page.getByLabel("Nom du niveau").fill("R-1");
  await page.getByRole("button", { name: "＋ Découper un niveau" }).click();
  await drag(0.03, 0.03, 0.4, 0.53);
  await expect(page.locator(".canvas-heading h1")).toHaveText("R-1");
  await page.getByLabel("Encadrer une annotation").click();
  await drag(0.08, 0.37, 0.15, 0.43);
  await page.getByLabel("Texte de l’annotation", { exact: true }).fill("PCF");
  await page.getByLabel("Catégorie", { exact: true }).selectOption("PCF");
  await page
    .getByRole("button", { name: "⊕ Pointer sur le plan", exact: true })
    .click();
  let b = (await canvas.boundingBox())!;
  await page.mouse.click(b.x + b.width * 0.17, b.y + b.height * 0.34);
  await expect(page.locator(".position-card p")).not.toHaveText("Non définie");
  await page.getByLabel("Agrandir", { exact: true }).click();
  await page.getByLabel("Agrandir", { exact: true }).click();
  await page.getByRole("button", { name: "150 %", exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  const projectId = await page
    .getByLabel("Projet", { exact: true })
    .inputValue();
  let first = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(first.state.annotations).toHaveLength(1);
  expect(first.state.annotations[0].anchor).not.toBeNull();
  expect(first.state.annotations[0].bbox.x).not.toBe(
    first.state.annotations[0].anchor.x,
  );
  // Real autosave after a pointer drag, then rotating the view must keep that position.
  const handle = canvas.locator('[data-anchor="true"] circle').first();
  const hb = (await handle.boundingBox())!;
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
  await page.mouse.down();
  await page.mouse.move(hb.x + hb.width / 2 + 16, hb.y + hb.height / 2 + 12, {
    steps: 6,
  });
  await page.mouse.up();
  await expect(page.locator(".save-ok")).toBeVisible({ timeout: 10000 });
  const moved = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(moved.state.annotations[0].anchor).not.toEqual(
    first.state.annotations[0].anchor,
  );
  expect(moved.state.annotations[0].bbox).toEqual(
    first.state.annotations[0].bbox,
  );
  first = moved;
  // Editing while autosave is in flight must queue the later edit, not lose it.
  let release!: () => void;
  let started!: () => void;
  let pause = true;
  const sawRequest = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route(
    origin + `/api/projects/${projectId}/state`,
    async (route) => {
      if (pause && route.request().method() === "PUT") {
        pause = false;
        started();
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      await route.continue();
    },
  );
  await page
    .getByRole("textbox", { name: "Commentaire", exact: true })
    .fill("Première correction");
  await sawRequest;
  await page
    .getByRole("textbox", { name: "Commentaire", exact: true })
    .fill("Correction pendant la sauvegarde");
  release();
  await expect(page.locator(".save-ok")).toBeVisible({ timeout: 10000 });
  const concurrent = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(concurrent.state.annotations[0].comment).toBe(
    "Correction pendant la sauvegarde",
  );
  await page.unroute(origin + `/api/projects/${projectId}/state`);
  await page.getByTitle("Tourner le niveau", { exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible({ timeout: 10000 });
  const rotated = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(rotated.state.floors[0].rotation_deg).toBe(90);
  expect(rotated.state.annotations[0].anchor).toEqual(
    first.state.annotations[0].anchor,
  );

  await page.getByRole("button", { name: "Dupliquer", exact: true }).click();
  await expect(page.locator(".annotation-rows>button")).toHaveCount(2);
  await page.getByLabel("Annuler", { exact: true }).click();
  await expect(page.locator(".annotation-rows>button")).toHaveCount(1);
  await page.getByLabel("Rétablir", { exact: true }).click();
  await expect(page.locator(".annotation-rows>button")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Supprimer la sélection", exact: true })
    .click();
  await expect(page.locator(".annotation-rows>button")).toHaveCount(1);
  await page.getByRole("button", { name: "Page entière", exact: true }).click();
  await page.getByLabel("Nom du niveau").fill("RDC");
  await page.getByRole("button", { name: "＋ Découper un niveau" }).click();
  await drag(0.41, 0.03, 0.98, 0.57);
  await expect(page.locator(".canvas-heading h1")).toHaveText("RDC");
  await page.getByLabel("Encadrer une annotation").click();
  await drag(0.27, 0.08, 0.33, 0.14);
  await page
    .getByLabel("Texte de l’annotation", { exact: true })
    .fill("PCF RDC");
  await page.getByLabel("Catégorie", { exact: true }).selectOption("PCF");
  await page
    .getByRole("button", { name: "⊕ Pointer sur le plan", exact: true })
    .click();
  b = (await canvas.boundingBox())!;
  await page.mouse.click(b.x + b.width * 0.25, b.y + b.height * 0.15);
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.locator(".save-ok")).toBeVisible();
  await page.reload();
  await page.getByLabel("Projet", { exact: true }).selectOption(projectId);
  await expect(page.locator(".annotation-rows>button")).toHaveCount(2);
  const saved = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(saved.state.floors).toHaveLength(2);
  expect(saved.state.annotations[0].anchor).toEqual(
    first.state.annotations[0].anchor,
  );
  expect(saved.state.annotations[0].bbox).toEqual(
    first.state.annotations[0].bbox,
  );
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exporter les données", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("DOEMO-donnees.json");
  await page.getByRole("button", { name: "Historique", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Corrections enregistrées" }),
  ).toBeVisible();
  await page.screenshot({
    path: process.env.DOEMO_TEST_SCREENSHOT || "/tmp/doemo-studio-mvp.png",
    fullPage: true,
  });
  // A different session wins its revision; this client must stop rather than overwrite it.
  const external = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  external.state.annotations[0].comment = "Correction d’une autre session";
  const externalSave = await page.request.put(
    origin + `/api/projects/${projectId}/state`,
    {
      headers: { Origin: origin },
      data: external.state,
    },
  );
  expect(externalSave.ok()).toBeTruthy();
  await page.locator(".annotation-rows>button").first().click();
  await page
    .getByRole("textbox", { name: "Commentaire", exact: true })
    .fill("Correction locale à conserver");
  await expect(page.getByRole("alert")).toContainText("autre session");
  const preserved = await (
    await page.request.get(origin + `/api/projects/${projectId}`)
  ).json();
  expect(preserved.state.annotations[0].comment).toBe(
    "Correction d’une autre session",
  );
  await expect(
    page.getByRole("button", { name: "Sauver la copie locale" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("SAI symbols are positioned at equipment anchors, draggable, persistent and exported with Illustrator", async ({
  page,
}) => {
  const ident = execFileSync(
    python,
    [
      "-c",
      `
import sys,json
from pathlib import Path
sys.path.insert(0,${JSON.stringify(resolve("../backend/tests"))})
from test_placement_flow import setup,mark
from doemo_releves.models import ProjectState,Point
c,ident,library=setup(Path(${JSON.stringify(root)}),data_root=Path(${JSON.stringify(root)}),owner='test-designer')
s=ProjectState.model_validate(c.get('/projects/'+ident).json()['state'])
s.annotations=[mark('p1','PCF'),mark('e1','CO₂'),mark('v1','PE'),mark('u1','inconnu',False)]
s.annotations[0].anchor=Point(x=.3,y=.4);s.annotations[1].anchor=Point(x=.5,y=.4);s.annotations[2].anchor=Point(x=.7,y=.4)
with c.app.state.store.connect() as con:
 con.execute('INSERT INTO jobs(id,project_id,actor,status,stage,payload,result) VALUES(?,?,?,?,?,?,?)',('posefixture',ident,'test-designer','completed','Résultat fixture',json.dumps({'engine':'multimodal','document_id':'survey','page':1}),json.dumps({'annotations':[a.model_dump() for a in s.annotations],'observations':[],'warnings':['Résultat CPU de test ; aucune IA réelle exécutée.']})))
print(ident)
`,
    ],
    { encoding: "utf8" },
  ).trim();
  await page.goto(origin + "/releves/");
  await page.getByLabel("Identifiant", { exact: true }).fill("test-designer");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill("test-only-long-password");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page.getByLabel("Projet", { exact: true }).selectOption(ident);
  await page.getByRole("button", { name: "Analyses IA", exact: true }).click();
  await page
    .getByRole("button", { name: "Ajouter à la revue", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Préparer les pictogrammes", exact: true })
    .click();
  const symbols = page.getByTestId("placed-pictogram");
  await expect(symbols).toHaveCount(3);
  await expect(symbols.first()).toHaveAttribute(
    "transform",
    "translate(300,400) rotate(0)",
  );
  await expect(symbols.first().locator("image")).toHaveAttribute(
    "href",
    /\/assets\/pcf\/preview/,
  );
  await expect(page.getByText(/3 pictogramme\(s\) affichable/)).toBeVisible();
  await page
    .getByRole("button", { name: "Exporter pour Illustrator", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("confirmer séparément");
  // Move the actual symbol. The annotation box remains at the observed text.
  const b = (await symbols.first().boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2 + 25, b.y + b.height / 2 + 20, {
    steps: 5,
  });
  await page.mouse.up();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  let project = await (
    await page.request.get(origin + "/api/projects/" + ident)
  ).json();
  expect(project.state.annotations[0].anchor.x).toBeGreaterThan(0.3);
  expect(project.state.annotations[0].bbox.x).toBe(0.1);
  expect(project.state.annotations[0].review.position).toBe(false);
  await page.reload();
  await page.getByLabel("Projet", { exact: true }).selectOption(ident);
  await expect(page.getByTestId("placed-pictogram")).toHaveCount(3);
  // Confirm each actual placement through the same API used by the review form.
  project = await (
    await page.request.get(origin + "/api/projects/" + ident)
  ).json();
  for (const a of project.state.annotations) {
    if (a.id === "u1") a.status = "rejected";
    else {
      a.status = "confirmed";
      for (const k of Object.keys(a.review)) a.review[k] = true;
    }
  }
  for (const m of project.state.mappings) m.confirmed = true;
  const saved = await page.request.put(
    origin + "/api/projects/" + ident + "/state",
    { headers: { Origin: origin }, data: project.state },
  );
  expect(saved.ok()).toBeTruthy();
  await page.reload();
  await page.getByLabel("Projet", { exact: true }).selectOption(ident);
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exporter pour Illustrator", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("DOEMO-placements.zip");
  await page.screenshot({
    path: "/tmp/doemo-pictograms-browser.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Illustrator & SAI ↗", exact: true })
    .click();
  await expect(
    page.getByText("BAT de référence", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "← Retour à l’atelier", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "← Retour à l’atelier", exact: true })
    .click();
  await expect(page.getByLabel("Projet", { exact: true })).toHaveValue(ident);
  await expect(page.getByTestId("placed-pictogram")).toHaveCount(3);
});
