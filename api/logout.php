<?php
require __DIR__ . '/_s.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST') studio_json(405, ['ok' => false]);
studio_same_origin();
studio_start();
if (!empty($_SESSION['token'])) studio_api('session_revoke', ['X-Auth-Token: ' . $_SESSION['token']]);
$_SESSION = [];
session_destroy();
setcookie('studio_sid', '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
studio_json(200, ['ok' => true]);
