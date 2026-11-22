#!/usr/bin/env bash
# Install finance-desk as personal Claude Code skills (alternative to the plugin).
# Copies this folder to ~/.claude/finance-desk and links each skill into
# ~/.claude/skills. Re-run to update. Nothing is downloaded; no packages installed.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.claude/finance-desk"
mkdir -p "${HOME}/.claude/skills"
rm -rf "${DEST}.new"
mkdir -p "${DEST}.new"
cp -R "${SRC}/fin.py" "${SRC}/finskills" "${SRC}/skills" "${SRC}/examples" "${DEST}.new/"
rm -rf "${DEST}"
mv "${DEST}.new" "${DEST}"
for d in "${DEST}"/skills/*/; do
  name="$(basename "$d")"
  link="${HOME}/.claude/skills/${name}"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "skip ${name}: ${link} exists and is not a symlink" >&2
    continue
  fi
  ln -sfn "${d%/}" "$link"
  echo "linked ${name}"
done
python3 "${DEST}/fin.py" --version
echo "Done. Optional: export SEC_USER_AGENT=\"Your Name you@example.com\" (needed for fundamentals/valuation)."
