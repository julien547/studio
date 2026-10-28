<?php
// Same-origin session bridge. The browser never receives RunPod credentials or internal paths.
require __DIR__ . '/_s.php';
studio_start();
if (empty($_SESSION['login']) || time() - (int)($_SESSION['t'] ?? 0) > 43200) {
    studio_json(401, ['error' => 'Session expirée.']);
}
if (!in_array($_SESSION['role'] ?? '', ['admin', 'administration', 'dessinateur'], true)) {
    studio_json(403, ['error' => 'Accès réservé aux dessinateurs et administrateurs.']);
}
$login = (string)$_SESSION['login'];
session_write_close();
if (preg_match('/[\r\n]/', $login)) studio_json(403, ['error' => 'Session invalide.']);
$method = $_SERVER['REQUEST_METHOD'];
$route = (string)($_GET['route'] ?? '/health');
$id = '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}';
$allowed = $method === 'GET'
    ? preg_match('#^/(health|projects|projects/' . $id . '|tasks/' . $id . '|projects/' . $id . '/export/(svg|preview|training|illustrator))$#D', $route)
    : ($method === 'POST' && preg_match('#^/(projects|projects/' . $id . '/(save|analyze))$#D', $route));
if (!$allowed) studio_json(404, ['error' => 'Route inconnue.']);
$body = null;
if ($method === 'POST') {
    studio_same_origin();
    if (($_SERVER['HTTP_ORIGIN'] ?? '') !== STUDIO_ORIGIN && ($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '') !== 'same-origin') {
        studio_json(403, ['error' => 'Origine refusée.']);
    }
    if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 33554432) studio_json(413, ['error' => 'Demande trop volumineuse.']);
    if ($route === '/projects') {
        $file = $_FILES['plan'] ?? null;
        if (!$file || $file['error'] !== UPLOAD_ERR_OK || $file['size'] > 20971520 || !is_uploaded_file($file['tmp_name'])) {
            studio_json(422, ['error' => 'PDF, PNG ou JPEG de 20 Mio maximum requis.']);
        }
        $page = filter_var($_POST['page'] ?? 1, FILTER_VALIDATE_INT);
        if ($page === false || $page < 1 || $page > 10000) studio_json(422, ['error' => 'Page invalide.']);
        $body = json_encode(['name' => basename($file['name']), 'page' => $page,
                             'content' => base64_encode(file_get_contents($file['tmp_name']))]);
    } else {
        $body = file_get_contents('php://input', false, null, 0, 33554433);
        if (strlen($body) > 33554432) studio_json(413, ['error' => 'Demande trop volumineuse.']);
        if ($body === '') $body = '{}';
    }
}
$ch = curl_init('http://localhost' . $route);
curl_setopt_array($ch, [CURLOPT_UNIX_SOCKET_PATH => getenv('DOEMO_REDESSIN_SOCKET') ?: '/run/doemo-redessin/api.sock',
    CURLOPT_RETURNTRANSFER => true, CURLOPT_CONNECTTIMEOUT => 3, CURLOPT_TIMEOUT => 30,
    CURLOPT_FOLLOWLOCATION => false, CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'X-Doemo-User: ' . $login]]);
if ($body !== null) curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
$response = curl_exec($ch); $status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE); curl_close($ch);
if ($response === false || $status < 100) studio_json(503, ['error' => 'Service de redessin indisponible.']);
$decoded = json_decode($response, true);
if ($decoded === null) studio_json(502, ['error' => 'Réponse de service invalide.']);
studio_json($status, $decoded);
