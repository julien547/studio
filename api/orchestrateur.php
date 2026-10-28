<?php
// Tableau de bord de l'orchestrateur IA : relais en LECTURE SEULE vers le service interne (127.0.0.1).
// Accès : session studio, rôles admin / administration. Le jeton de lecture ne permet que la vue d'ensemble.
require __DIR__ . '/_s.php';
studio_start();
$role = (string)($_SESSION['role'] ?? '');
$login = (string)($_SESSION['login'] ?? '');
if ($login === '' || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) studio_json(401, ['ok' => false, 'error' => 'Session expirée.']);
if (!in_array($role, ['admin', 'administration'], true)) studio_json(403, ['ok' => false, 'error' => 'Accès réservé à l’administration.']);
session_write_close();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') studio_json(405, ['ok' => false, 'error' => 'Méthode refusée.']);

$tokenFile = '/etc/doemo-studio/orchestrateur-lecture.env';
$env = is_readable($tokenFile) ? (string)file_get_contents($tokenFile) : '';
if (!preg_match('/^DOEMO_ORCH_READ_TOKEN=([A-Za-z0-9_\-]{32,})$/m', $env, $m)) studio_json(503, ['ok' => false, 'error' => 'Orchestrateur non configuré.']);

$window = (int)($_GET['window'] ?? 3600);
$window = max(60, min(86400 * 7, $window));
$ch = curl_init('http://127.0.0.1:8765/v1/admin/overview?window=' . $window);
curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 2, CURLOPT_TIMEOUT => 8,
    CURLOPT_PROXY => '', CURLOPT_FOLLOWLOCATION => false, CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $m[1], 'Accept: application/json']]);
$out = curl_exec($ch);
$code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);
$data = $out === false ? null : json_decode($out, true);
if ($code !== 200 || !is_array($data)) studio_json(503, ['ok' => false, 'error' => 'Orchestrateur indisponible.']);
studio_json(200, ['ok' => true, 'overview' => $data]);
