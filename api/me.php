<?php
require __DIR__ . '/_s.php';
studio_start();
if (empty($_SESSION['login']) || !in_array($_SESSION['role'] ?? '', STUDIO_ROLES_INTERNES, true) || (time() - (int)($_SESSION['t'] ?? 0)) > 43200) {
    studio_json(401, ['ok' => false]);
}
studio_json(200, ['ok' => true, 'login' => $_SESSION['login'], 'role' => $_SESSION['role']]);
