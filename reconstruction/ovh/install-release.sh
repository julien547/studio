#!/usr/bin/env bash
set -euo pipefail
# Run as root on OVH from the reviewed Git checkout. Does not alter Apache or RunPod.
if [[ ${EUID} -ne 0 || $# -ne 2 ]]; then
  echo 'Usage: sudo bash reconstruction/ovh/install-release.sh /absolute/checkout /absolute/StudioDocumentRoot' >&2
  exit 2
fi
source_root=$(realpath "$1")
web_root=$(realpath "$2")
[[ -f "$source_root/reconstruction/pyproject.toml" && -f "$web_root/api/_s.php" ]] || {
  echo 'Sources ou racine Studio non confirmées ; aucun fichier publié.' >&2; exit 2;
}
[[ -f "$source_root/redessin/editor.js" ]] || { echo 'Construire editor.js avant installation.' >&2; exit 2; }
if systemctl is-active --quiet doemo-redessin.service; then
  echo 'Service actif : terminer les tâches et le stopper avant de préparer une mise à jour.' >&2
  exit 2
fi
if ! getent group www-data >/dev/null; then echo 'Adapter le groupe du serveur web après inventaire.' >&2; exit 2; fi
if ! id doemo-redessin >/dev/null 2>&1; then
  useradd --system --gid www-data --home-dir /var/lib/doemo-redessin --no-create-home --shell /usr/sbin/nologin doemo-redessin
fi
release_id=$(git -C "$source_root" rev-parse HEAD)
release_dir="/opt/doemo-redessin/releases/$release_id"
[[ ! -e "$release_dir" ]] || { echo 'Cette version est déjà préparée ; inspecter son état avant de relancer.' >&2; exit 2; }
install -d -m 0755 /opt/doemo-redessin/releases
install -d -m 0700 /var/backups/doemo-redessin
install -d -m 0750 -o root -g www-data /etc/doemo-redessin
install -d -m 0700 -o doemo-redessin -g www-data /var/lib/doemo-redessin
mkdir "$release_dir"
cp -a "$source_root/reconstruction/." "$release_dir/"
python3 -m venv "$release_dir/venv"
"$release_dir/venv/bin/pip" install "$release_dir[service]"
"$release_dir/venv/bin/python" -c 'import doemo_reconstruction.workbench'
"$release_dir/venv/bin/pip" freeze > "$release_dir/installed-requirements.txt"
# Source snapshot and runtime stay root-owned, readable by the service account.
chmod -R u=rwX,go=rX "$release_dir"
backup="/var/backups/doemo-redessin/$(date -u +%Y%m%dT%H%M%SZ)-$release_id"
mkdir -m 0700 "$backup"
[[ ! -e "$web_root/redessin" ]] || cp -a "$web_root/redessin" "$backup/"
[[ ! -e "$web_root/api/redessin.php" ]] || cp -a "$web_root/api/redessin.php" "$backup/redessin.php"
readlink /opt/doemo-redessin/current > "$backup/previous-current.txt" || true
readlink /opt/doemo-redessin/venv > "$backup/previous-venv.txt" || true
[[ ! -f /etc/systemd/system/doemo-redessin.service ]] || cp -a /etc/systemd/system/doemo-redessin.service "$backup/"
[[ ! -f /etc/doemo-redessin/service.env ]] || cp -a /etc/doemo-redessin/service.env "$backup/"
if [[ ! -e /etc/doemo-redessin/service.env ]]; then
  install -m 0640 -o root -g www-data "$source_root/reconstruction/ovh/service.env.example" /etc/doemo-redessin/service.env
fi
install -d -m 0755 "$web_root/redessin"
for file in index.php editor.js workbench.js workbench.css; do
  install -m 0644 "$source_root/redessin/$file" "$web_root/redessin/$file"
done
install -m 0644 "$source_root/api/redessin.php" "$web_root/api/redessin.php"
ln -sfn "$release_dir" /opt/doemo-redessin/current
ln -sfn "$release_dir/venv" /opt/doemo-redessin/venv
install -m 0644 "$source_root/reconstruction/ovh/doemo-redessin.service" /etc/systemd/system/doemo-redessin.service
systemctl daemon-reload
# Activation is a separate documented step after Apache/PHP configuration validation.
echo "Version préparée : $release_id"
echo "Sauvegarde : $backup"
echo 'Valider Apache/PHP puis démarrer doemo-redessin.service selon DEPLOIEMENT_OVH.md.'
