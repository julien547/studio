<?php
// Relais same-origin vers l'API DOEMO : le jeton de session reste côté serveur (jamais envoyé au navigateur).
require __DIR__ . '/_s.php';
studio_start();
if (empty($_SESSION['token']) || !in_array($_SESSION['role'] ?? '', STUDIO_ROLES_INTERNES, true) || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) {
    studio_json(401, ['ok' => false, 'error' => 'Session expirée.']);
}
$method = $_SERVER['REQUEST_METHOD'];
if (!in_array($method, ['GET', 'POST'], true)) studio_json(405, ['ok' => false, 'error' => 'Méthode non autorisée.']);
if ($method === 'POST') {
    studio_same_origin();
    if (($_SERVER['HTTP_ORIGIN'] ?? '') === '' && ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '') !== 'same-origin') studio_json(403, ['ok' => false, 'error' => 'Origine refusée.']);
}
// Seules les actions de l'atelier sont relayées.
$action = (string)($_GET['action'] ?? '');
if (!preg_match('/^studio_[a-z_]{1,40}$/', $action)) studio_json(403, ['ok' => false, 'error' => 'Action non autorisée.']);
$qs = $_SERVER['QUERY_STRING'] ?? '';
$ch = curl_init('https://gestion.doemo.fr/api_doemo.php?' . $qs);
$headers = ['X-Auth-Token: ' . $_SESSION['token'], 'X-Real-IP: ' . substr($_SERVER['REMOTE_ADDR'] ?? '', 0, 45)];
if (!empty($_SERVER['CONTENT_TYPE'])) $headers[] = 'Content-Type: ' . $_SERVER['CONTENT_TYPE'];
$opts = [CURLOPT_RETURNTRANSFER => true, CURLOPT_HEADER => true, CURLOPT_TIMEOUT => 300, CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_SSL_VERIFYPEER => true, CURLOPT_HTTPHEADER => $headers];
if ($method === 'POST') { $opts[CURLOPT_POST] = true; $opts[CURLOPT_POSTFIELDS] = file_get_contents('php://input'); }
curl_setopt_array($ch, $opts);
$raw = curl_exec($ch);
if ($raw === false) { curl_close($ch); studio_json(502, ['ok' => false, 'error' => 'Service momentanément indisponible.']); }
$code = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
$hs = (int)curl_getinfo($ch, CURLINFO_HEADER_SIZE);
curl_close($ch);
$head = substr($raw, 0, $hs); $body = substr($raw, $hs);
http_response_code($code ?: 502);
header('Cache-Control: no-store');
foreach (['Content-Type', 'Content-Disposition'] as $h) {
    if (preg_match('/^' . $h . ':\s*(.+)$/mi', $head, $m)) header($h . ': ' . trim($m[1]));
}
echo $body;
