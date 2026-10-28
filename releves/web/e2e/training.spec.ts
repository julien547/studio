import { test, expect, type Page } from "@playwright/test";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
const python =
  process.env.DOEMO_TEST_PYTHON ||
  "/workspace/.venvs/studio-releves/bin/python";
const root = mkdtempSync(tmpdir() + "/doemo-training-e2e-"),
  origin = "http://127.0.0.1:18083";
let server: ChildProcess;
let acceptedTrainingFixture = false;
function start() {
  return spawn(
    python,
    [
      "-m",
      "uvicorn",
      "doemo_releves.auth:standalone",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      "18083",
      "--no-access-log",
    ],
    {
      env: {
        ...process.env,
        DOEMO_RELEVES_DATA: root,
        DOEMO_PUBLIC_ORIGIN: origin,
        DOEMO_RELEVES_DIST: resolve("../dist"),
        DOEMO_RUNPOD_MANAGED: acceptedTrainingFixture ? "1" : "0",
        DOEMO_RUNPOD_ENDPOINT: "",
        DOEMO_RUNPOD_TOKEN: acceptedTrainingFixture
          ? "fixture-token-only-0000000000000000"
          : "",
        RUNPOD_API_KEY: acceptedTrainingFixture
          ? "fixture-provider-key-only"
          : "",
        DOEMO_RUNPOD_POD_ID: "fixture-pod-never-contacted",
        DOEMO_TRAINING_PROFILE: acceptedTrainingFixture
          ? root + "/fixture-profile.json"
          : "",
      },
      stdio: "pipe",
    },
  );
}
async function ready() {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(origin + "/entrainement")).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw Error("Local test server unavailable");
}
async function stop() {
  const exited = new Promise((r) => server.once("exit", r));
  server.kill();
  await exited;
}
test.beforeAll(async () => {
  execFileSync(python, [
    "-c",
    `from doemo_releves.store import Store
from doemo_releves.auth import password_hash
s=Store(${JSON.stringify(root)})
with s.connect() as c:
 for role in ('admin','dessinateur'):c.execute('INSERT INTO users(login,password_hash,role) VALUES(?,?,?)',(role,password_hash('test-only-long-password'),role))`,
  ]);
  server = start();
  await ready();
});
test.afterAll(async () => {
  await stop();
  rmSync(root, { recursive: true, force: true });
});
async function login(page: Page, role = "admin") {
  await page.goto(origin + "/entrainement");
  await page.getByLabel("Identifiant", { exact: true }).fill(role);
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill("test-only-long-password");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
}
async function upload(page: Page, name: string) {
  await page.getByLabel("Nouveau projet", { exact: true }).fill(name);
  await page
    .getByRole("button", { name: "Créer le projet", exact: true })
    .click();
  const png = execFileSync(python, [
    "-c",
    "import io,sys;from PIL import Image;b=io.BytesIO();Image.new('RGB',(1200,850),'white').save(b,'PNG');sys.stdout.buffer.write(b.getvalue())",
  ]);
  await page
    .getByLabel("Importer un plan", { exact: true })
    .setInputFiles({ name: "plan.png", mimeType: "image/png", buffer: png });
  await expect(page.getByTestId("plan-canvas")).toBeVisible();
}
async function drag(
  page: Page,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
) {
  const svg = page.getByTestId("plan-canvas").locator("svg");
  await svg.scrollIntoViewIfNeeded();
  const b = (await svg.boundingBox())!;
  await page.mouse.move(b.x + b.width * x1, b.y + b.height * y1);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width * x2, b.y + b.height * y2, { steps: 8 });
  await page.mouse.up();
}
const section = (page: Page, name: string) =>
  page
    .getByRole("navigation", { name: "Rubriques d’apprentissage" })
    .getByRole("button", { name, exact: true });

test("OCR corrections, explicit consent, immutable dataset export, process restart and conflicts", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page
    .getByRole("button", { name: "PaddleOCR Lire les écritures" })
    .click();
  await upload(page, "OCR apprentissage");
  await page
    .getByRole("button", { name: "Dessiner une annotation", exact: true })
    .click();
  await drag(page, 0.1, 0.1, 0.3, 0.2);
  await page
    .getByLabel("Transcription exacte", { exact: true })
    .fill("H₂O · CO₂ · PCF");
  await page.getByLabel("Annotation vérifiée", { exact: true }).check();
  await expect(
    page.getByRole("button", { name: "Valider l’exemple", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel(
      "J’autorise la réutilisation de ce projet pour l’apprentissage.",
      { exact: true },
    )
    .click();
  await page
    .getByRole("button", { name: "Valider l’exemple", exact: true })
    .click();
  await expect(
    page.getByText("Exemple validé.", { exact: true }),
  ).toBeVisible();
  let examples = await (
    await page.request.get(
      origin + "/api/projects/training/examples?engine=paddleocr",
    )
  ).json();
  const saved = examples[0];
  expect(saved.data.labels[0].text).toBe("H₂O · CO₂ · PCF");
  expect(saved.status).toBe("validated");
  await section(page, "Datasets").click();
  await page
    .getByRole("checkbox", {
      name: "Inclure l’exemple " + saved.id,
      exact: true,
    })
    .check();
  await page.getByLabel("Nom du dataset", { exact: true }).fill("OCR v1");
  await page
    .getByRole("button", { name: "Créer une version du dataset", exact: true })
    .click();
  await expect(
    page.getByText("Version du dataset créée.", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exporter le dataset", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(
    /^DOEMO-dataset-.*\.zip$/,
  );
  await section(page, "Entraînements").click();
  await expect(
    page.getByRole("button", { name: "Lancer l’entraînement", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("heading", {
      name: "Entraînement non disponible",
      exact: true,
    }),
  ).toBeVisible();
  await stop();
  server = start();
  await ready();
  await page.reload();
  await page
    .getByRole("button", { name: "PaddleOCR Lire les écritures" })
    .click();
  await section(page, "Datasets").click();
  await page
    .getByRole("button", { name: "Vérifier / corriger", exact: true })
    .click();
  await expect(
    page.getByLabel("Transcription exacte", { exact: true }),
  ).toHaveCount(0);
  await page.locator(".training-labels button").first().click();
  await expect(
    page.getByLabel("Transcription exacte", { exact: true }),
  ).toHaveValue("H₂O · CO₂ · PCF");
  const external = structuredClone(saved.data);
  external.notes = "Autre session";
  expect(
    (
      await page.request.put(
        origin + "/api/projects/training/examples/" + saved.id,
        { headers: { Origin: origin }, data: external },
      )
    ).ok(),
  ).toBeTruthy();
  await page
    .getByLabel("Transcription exacte", { exact: true })
    .fill("Correction locale");
  await page
    .getByRole("button", { name: "Enregistrer les corrections", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("recharger");
  await expect(
    page.getByLabel("Transcription exacte", { exact: true }),
  ).toHaveValue("Correction locale");
  page.once("dialog", (d) => d.dismiss());
  await section(page, "Datasets").click();
  await expect(
    page.getByLabel("Transcription exacte", { exact: true }),
  ).toHaveValue("Correction locale");
  expect(errors).toEqual([]);
});

test("architecture centerline, opening clipping and equipment anchors use separate saved geometry", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("button", { name: "IA architecturale Reconstruire les murs" })
    .click();
  await upload(page, "Murs apprentissage");
  await page
    .getByRole("button", { name: "Tracer un axe de mur", exact: true })
    .click();
  await drag(page, 0.1, 0.3, 0.8, 0.3);
  await page.getByLabel("Annotation vérifiée", { exact: true }).check();
  await page
    .getByLabel("Catégorie à ajouter", { exact: true })
    .selectOption("OPENING");
  await page
    .getByRole("button", { name: "Dessiner une annotation", exact: true })
    .click();
  await drag(page, 0.4, 0.25, 0.5, 0.35);
  await page.getByLabel("Annotation vérifiée", { exact: true }).check();
  await page
    .getByLabel(
      "J’autorise la réutilisation de ce projet pour l’apprentissage.",
      { exact: true },
    )
    .click();
  await page
    .getByRole("button", { name: "Valider l’exemple", exact: true })
    .click();
  await expect(
    page.getByText("Exemple validé.", { exact: true }),
  ).toBeVisible();
  const saved = (
    await (
      await page.request.get(
        origin + "/api/projects/training/examples?engine=architecture",
      )
    ).json()
  )[0];
  expect(saved.data.labels[0].segments).toHaveLength(2);
  const lines = page.getByTestId("plan-canvas").locator('line[stroke="black"]');
  await expect(lines).toHaveCount(2);
  await page.screenshot({
    path: "/tmp/doemo-training-architecture.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "RTMDet Détecter les équipements" })
    .click();
  await page
    .getByLabel("Projet d’apprentissage", { exact: true })
    .selectOption(saved.project_id);
  await page
    .getByLabel("Catégorie à ajouter", { exact: true })
    .selectOption("FIRE");
  await page
    .getByRole("button", { name: "Dessiner une annotation", exact: true })
    .click();
  await drag(page, 0.1, 0.1, 0.2, 0.2);
  await page
    .getByRole("button", { name: "Pointer l’implantation", exact: true })
    .click();
  const svg = page.getByTestId("plan-canvas").locator("svg");
  const b = (await svg.boundingBox())!;
  await page.mouse.click(b.x + b.width * 0.6, b.y + b.height * 0.3);
  await page.getByLabel("Annotation vérifiée", { exact: true }).check();
  await page
    .getByRole("button", { name: "Valider l’exemple", exact: true })
    .click();
  await expect(
    page.getByText("Exemple validé.", { exact: true }),
  ).toBeVisible();
  const equipment = (
    await (
      await page.request.get(
        origin + "/api/projects/training/examples?engine=rtmdet",
      )
    ).json()
  )[0].data.labels[0];
  expect(equipment.anchor.x).toBeCloseTo(0.6, 1);
  expect(equipment.bbox.x).toBeCloseTo(0.1, 1);
});

test("Qwen reference version is real, and designer cannot access training", async ({
  page,
}) => {
  await login(page);
  await upload(page, "Conventions Qwen");
  await page.getByLabel("Convention DOEMO", { exact: true }).fill("PCF");
  await page
    .getByLabel("Interprétation corrigée", { exact: true })
    .fill("Porte coupe-feu");
  await page
    .getByLabel(
      "J’autorise la réutilisation de ce projet pour l’apprentissage.",
      { exact: true },
    )
    .click();
  await page
    .getByRole("button", { name: "Valider l’exemple", exact: true })
    .click();
  await expect(
    page.getByText("Exemple validé.", { exact: true }),
  ).toBeVisible();
  await section(page, "Datasets").click();
  await page.getByRole("checkbox", { name: /Inclure l’exemple/ }).check();
  await page.getByLabel("Nom du dataset", { exact: true }).fill("Conventions");
  await page
    .getByRole("button", { name: "Créer une version du dataset", exact: true })
    .click();
  await expect(
    page.getByText("Version du dataset créée.", { exact: true }),
  ).toBeVisible();
  await section(page, "Modèles IA").click();
  await page
    .getByLabel("Nom de la version", { exact: true })
    .fill("Conventions 1");
  await page
    .getByLabel("Version du dataset", { exact: true })
    .selectOption({ label: "Conventions · v1" });
  await page
    .getByRole("button", { name: "Enregistrer le référentiel", exact: true })
    .click();
  await expect(
    page.getByText("Version enregistrée dans le registre.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mettre en production", exact: true }),
  ).toBeDisabled();
  const versions = (
    await (
      await page.request.get(
        origin + "/api/projects/training/models?engine=qwen",
      )
    ).json()
  ).versions;
  expect(versions[0].manifest.rules.PCF).toBe("Porte coupe-feu");
  expect(versions[0].manifest.weights_trained).toBe(false);
  await page.request.post(origin + "/session/logout", {
    headers: { Origin: origin },
  });
  await login(page, "dessinateur");
  await expect(
    page.getByRole("heading", { name: "Accès réservé aux administrateurs" }),
  ).toBeVisible();
  expect(
    (
      await page.request.get(origin + "/api/projects/training/capabilities")
    ).status(),
  ).toBe(403);
});

test("saved detector result overlays neutral boxes and requires explicit categorisation", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("button", { name: "RTMDet Détecter les équipements" })
    .click();
  await upload(page, "Analyse conservée");
  const projectId = await page
    .getByLabel("Projet d’apprentissage", { exact: true })
    .inputValue();
  const project = await (
    await page.request.get(origin + "/api/projects/" + projectId)
  ).json();
  const submitted = await page.request.post(
    origin + "/api/projects/" + projectId + "/jobs",
    {
      headers: { Origin: origin },
      data: { engine: "rtmdet", document_id: project.documents[0].id, page: 1 },
    },
  );
  expect(submitted.ok()).toBeTruthy();
  const job = await submitted.json();
  // Replay a detector output in the isolated database. No GPU service is invoked.
  execFileSync(python, [
    "-c",
    `import json
from doemo_releves.store import Store
from doemo_releves.ai_contracts import normalise
s=Store(${JSON.stringify(root)})
r=normalise('rtmdet',{'labels':[9],'scores':[.9],'bboxes':[[120,85,240,170]]},${JSON.stringify(project.documents[0].id)},1,1200,850)
with s.connect() as c:c.execute("UPDATE jobs SET status='completed',stage='Terminé',result=? WHERE id=?",(json.dumps(r),${JSON.stringify(job.id)}))`,
  ]);
  await expect(
    page.getByLabel("Analyses enregistrées").locator("option"),
  ).toHaveCount(2, { timeout: 10000 });
  await page.getByLabel("Analyses enregistrées").selectOption(job.id);
  await expect(
    page.getByTestId("plan-canvas").locator('rect[stroke="#2477ad"]'),
  ).toHaveCount(1);
  await expect(page.getByText("Classe source 9 · 90 %")).toBeVisible();
  await page
    .getByRole("button", {
      name: "Copier les propositions à vérifier",
      exact: true,
    })
    .click();
  await page.locator(".training-labels button").first().click();
  await expect(
    page.getByLabel("Annotation vérifiée", { exact: true }),
  ).not.toBeChecked();
  await page
    .getByRole("button", { name: "Enregistrer les corrections", exact: true })
    .click();
  await expect(
    page.getByText("Corrections enregistrées.", { exact: true }),
  ).toBeVisible();
  const examples = await (
    await page.request.get(
      origin +
        "/api/projects/training/examples?engine=rtmdet&project_id=" +
        projectId,
    )
  ).json();
  expect(examples[0].data.labels[0].anchor).toBeNull();
  expect(examples[0].status).toBe("draft");
  expect(
    (
      await (
        await page.request.get(origin + "/api/projects/" + projectId)
      ).json()
    ).state.annotations,
  ).toEqual([]);
});

test("confirmed training admission persists and can be cancelled without a GPU worker", async ({
  page,
}) => {
  // An explicitly fake acceptance profile exercises real local API admission.
  // No lifecycle/training worker is started and no external request is made.
  await stop();
  const data = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        `
import json,sys
from pathlib import Path
sys.path.insert(0,${JSON.stringify(resolve("../backend/tests"))})
from test_training import source,example,label,validate,dataset
from fastapi.testclient import TestClient
from doemo_releves.api import create_app
root=Path(${JSON.stringify(root)})
profile={'engine':'rtmdet','driver_sha256':'a'*64,'runtime_sha256':'b'*64,'config_sha256':'c'*64,'weights_sha256':'d'*64,'acceptance':{'training_completed':True,'resume_verified':True,'inference_preemption_verified':True,'cancel_verified':True,'report_sha256':'e'*64}}
(root/'fixture-profile.json').write_text(json.dumps(profile))
c=TestClient(create_app(root),headers={'X-Doemo-User':'admin','X-Doemo-Role':'admin'})
examples=[]
for color in ('red','green','blue'):
 p=source(c,color);_,e=example(c,'rtmdet',p,[label('FIRE',anchor={'x':.5,'y':.5})]);examples.append(validate(c,p,e))
print(json.dumps(dataset(c,'rtmdet',examples)))
`,
      ],
      { encoding: "utf8" },
    ),
  );
  acceptedTrainingFixture = true;
  server = start();
  await ready();
  await login(page);
  await page
    .getByRole("button", { name: "RTMDet Détecter les équipements" })
    .click();
  await page
    .getByRole("button", { name: "Entraînements", exact: true })
    .click();
  await page.getByLabel("Version du dataset").selectOption(data.id);
  await page.getByLabel("Époques", { exact: true }).fill("2");
  await expect(
    page.getByRole("button", { name: "Lancer l’entraînement", exact: true }),
  ).toBeEnabled();
  page.on("dialog", (dialog) => dialog.accept());
  const admission = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().endsWith("/training/runs"),
  );
  await page
    .getByRole("button", { name: "Lancer l’entraînement", exact: true })
    .click();
  const sent = (await admission).postDataJSON();
  expect(sent.confirmed).toBe(true);
  expect(sent.request_key).toMatch(/^[a-z0-9-]{36}$/);
  await expect(
    page.getByText("Entraînement demandé.", { exact: true }),
  ).toBeVisible();
  const url = origin + "/api/projects/training/runs?engine=rtmdet";
  const runs = await (await page.request.get(url)).json();
  expect(runs).toHaveLength(1);
  expect(runs[0].status).toBe("queued");
  expect(runs[0].parameters.epochs).toBe(2);
  expect(runs[0].dispatched).toBe(0);
  await stop();
  server = start();
  await ready();
  await page.reload();
  await page
    .getByRole("button", { name: "RTMDet Détecter les équipements" })
    .click();
  await page
    .getByRole("button", { name: "Entraînements", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "En attente · " + runs[0].id.slice(0, 8),
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Interrompre proprement", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Annulé · " + runs[0].id.slice(0, 8) }),
  ).toBeVisible();
  expect((await (await page.request.get(url)).json())[0].status).toBe(
    "cancelled",
  );
});
