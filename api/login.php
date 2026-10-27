<?php
require __DIR__ . '/_s.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST') studio_json(405, ['ok' => false, 'error' => 'Méthode non autorisée.']);
studio_same_origin();
$in = json_decode(file_get_contents('php://input'), true);
$login = is_array($in) ? trim((string)($in['login'] ?? '')) : '';
$pass = is_array($in) ? (string)($in['password'] ?? '') : '';
if ($login === '' || $pass === '' || strlen($login) > 100 || strlen($pass) > 200) studio_json(400, ['ok' => false, 'error' => 'Renseignez votre identifiant et votre mot de passe.']);
$ip = substr($_SERVER['REMOTE_ADDR'] ?? '', 0, 45);
// Même contrôle que l'application DOEMO (mot de passe vérifié par Dolibarr, anti-force-brute inclus).
$r = studio_api('session_login', ['X-Real-IP: ' . $ip], ['login' => $login, 'password' => $pass, 'entity' => 2]);
if (!is_array($r) || empty($r['ok']) || empty($r['token'])) {
    $msg = is_array($r) ? (string)($r['error'] ?? '') : '';
    if (stripos($msg, 'trop') !== false || stripos($msg, 'tentative') !== false) studio_json(429, ['ok' => false, 'error' => 'Trop de tentatives. Réessayez dans quelques minutes.']);
    usleep(400000);
    studio_json(401, ['ok' => false, 'error' => 'Identifiant ou mot de passe incorrect.']);
}
$token = (string)$r['token'];
if (!in_array($r['role'] ?? '', STUDIO_ROLES_INTERNES, true)) {
    studio_api('session_revoke', ['X-Auth-Token: ' . $token]);
    studio_json(403, ['ok' => false, 'error' => "Cet espace est réservé aux utilisateurs internes DOEMO."]);
}
studio_start();
session_regenerate_id(true);
$_SESSION = ['login' => $login, 'role' => $r['role'], 'token' => $token, 't' => time()];
studio_json(200, ['ok' => true]);
