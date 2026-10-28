<?php
// Internal router, included only after the authenticated orientation gate.
if (!defined('OR_PRIVATE')) { http_response_code(404); exit; }

function or_levels_json_input() {
    $raw = file_get_contents('php://input', false, null, 0, 4194305);
    if (strlen($raw) > 4194304) studio_json(413, ['ok' => false, 'error' => 'Sélections trop volumineuses.']);
    $value = json_decode($raw, true);
    if (!is_array($value)) studio_json(400, ['ok' => false, 'error' => 'Document JSON invalide.']);
    return $value;
}
function or_levels_reply($code, $out, $err) {
    $result = json_decode($out, true);
    if ($code !== 0 || !is_array($result)) studio_json(422, ['ok' => false, 'error' => or_msg($err, 'Sélection refusée.')]);
    return $result;
}
if ($action === 'source') {
    $id = (string)($_GET['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $path = OR_PRIVATE . "/$id/source.pdf";
    if (!is_file($path) || is_link($path)) studio_json(404, ['ok' => false, 'error' => 'BAT introuvable.']);
    header('Content-Type: application/pdf'); header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff'); header('Content-Length: ' . filesize($path));
    readfile($path); exit;
}
if ($action === 'projects') {
    $projects = [];
    if (is_dir(OR_PRIVATE)) foreach (scandir(OR_PRIVATE) as $id) {
        if (!or_job_ok($id) || !is_file(OR_PRIVATE . "/$id/levels.json")) continue;
        $m = json_decode(@file_get_contents(OR_PRIVATE . "/$id/meta.json"), true);
        if (!is_array($m) || (!$isAdmin && ($m['login'] ?? '') !== $login)) continue;
        $projects[] = ['job' => $id, 'name' => $m['name'], 'updated' => filemtime(OR_PRIVATE . "/$id/levels.json")];
    }
    usort($projects, fn($a, $b) => $b['updated'] <=> $a['updated']);
    studio_json(200, ['ok' => true, 'projects' => $projects]);
}
if ($action === 'project') {
    $id = (string)($_GET['job'] ?? ''); $meta = or_job_meta($id, $login, $isAdmin);
    [$code, $out, $err] = or_run(['inspect', OR_PRIVATE . "/$id/source.pdf"], 60);
    $info = or_levels_reply($code, $out, $err);
    studio_json(200, ['ok' => true, 'job' => $id, 'name' => $meta['name'], 'pageCount' => $info['page_count']]);
}
if ($action === 'levels' && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $id = (string)($_GET['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $path = OR_PRIVATE . "/$id/levels.json";
    if (is_file($path)) {
        [$code, $out, $err] = or_run(['levels-validate', OR_PRIVATE . "/$id/source.pdf", $path]);
    } else {
        [$code, $out, $err] = or_run(['levels-init', OR_PRIVATE . "/$id/source.pdf"]);
    }
    $result = or_levels_reply($code, $out, $err);
    studio_json(200, ['ok' => true] + $result);
}
if ($action === 'levels') {
    or_post_guard();
    $input = or_levels_json_input();
    $id = (string)($input['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $document = $input['document'] ?? null;
    if (!is_array($document)) studio_json(400, ['ok' => false, 'error' => 'Sélections absentes.']);
    $directory = OR_PRIVATE . "/$id";
    $temporary = tempnam($directory, '.levels-');
    if ($temporary === false) studio_json(500, ['ok' => false, 'error' => 'Sauvegarde indisponible.']);
    try {
        file_put_contents($temporary, json_encode($document, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));
        [$code, $out, $err] = or_run(['levels-validate', "$directory/source.pdf", $temporary]);
    } finally { @unlink($temporary); }
    $result = or_levels_reply($code, $out, $err);
    $lock = fopen("$directory/.levels.lock", 'c');
    if (!$lock || !flock($lock, LOCK_EX)) studio_json(500, ['ok' => false, 'error' => 'Verrouillage indisponible.']);
    $old = is_file("$directory/levels.json") ? json_decode(file_get_contents("$directory/levels.json"), true) : ['revision' => 0];
    if (($document['revision'] ?? 0) !== ($old['revision'] ?? 0)) {
        flock($lock, LOCK_UN); fclose($lock);
        studio_json(409, ['ok' => false, 'error' => 'Le projet a été modifié dans une autre session. Rechargez-le avant de sauvegarder.']);
    }
    $result['document']['revision'] = ($old['revision'] ?? 0) + 1;
    $temporary = tempnam($directory, '.levels-');
    $written = $temporary !== false && file_put_contents($temporary, json_encode($result['document'], JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)) !== false;
    if ($written) { chmod($temporary, 0660); $written = rename($temporary, "$directory/levels.json"); }
    if (!$written && $temporary !== false) @unlink($temporary);
    flock($lock, LOCK_UN); fclose($lock);
    if (!$written) studio_json(500, ['ok' => false, 'error' => 'Sauvegarde impossible.']);
    studio_json(200, ['ok' => true] + $result);
}
if ($action === 'clip-preview') {
    or_post_guard();
    $input = or_levels_json_input();
    $id = (string)($input['job'] ?? ''); or_job_meta($id, $login, $isAdmin);
    $mode = $input['mode'] ?? '';
    $level = $input['level'] ?? '';
    if (!in_array($mode, ['PE', 'PI'], true) || !is_string($level) || !preg_match('/^[A-Za-z0-9_-]{1,80}$/', $level)) {
        studio_json(400, ['ok' => false, 'error' => 'Niveau ou type invalide.']);
    }
    $saved = OR_PRIVATE . "/$id/levels.json";
    if (!is_file($saved)) studio_json(400, ['ok' => false, 'error' => 'Enregistrez les niveaux avant cet aperçu.']);
    $directory = OR_RESULTS . "/$id";
    if (!or_mkdir($directory)) studio_json(500, ['ok' => false, 'error' => 'Stockage indisponible.']);
    $name = 'selection-' . bin2hex(random_bytes(8)) . '.pdf';
    [$code, $out, $err] = or_run(['levels-preview', OR_PRIVATE . "/$id/source.pdf", $saved, "$directory/$name", '--mode', $mode, '--level', $level]);
    $result = or_levels_reply($code, $out, $err);
    @chmod("$directory/$name", 0660);
    studio_json(200, ['ok' => true, 'job' => $id, 'file' => $name, 'report' => $result]);
}
