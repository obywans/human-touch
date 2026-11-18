#!/bin/sh
# HumanTouch installer for macOS and Linux. Installs the skill so its command is /human.
#   sh install.sh [--claude] [--agents] [--gemini-command]    (default: --claude --agents)
# One clone lives in ~/.human-touch; each host gets a symlink. Nothing existing is overwritten.
#   --claude          ~/.claude/skills/human        Claude Code        command: /human
#   --agents          ~/.agents/skills/human        Codex, Gemini CLI  Codex: $human, Gemini: automatic
#   --gemini-command  ~/.gemini/commands/human.toml Gemini CLI         command: /human
# Environment: HUMAN_TOUCH_HOME (clone dir), HUMAN_TOUCH_REPO (source, default the official repo).
set -eu
HOME_DIR="${HOME:?HOME is not set}"
CLONE="${HUMAN_TOUCH_HOME:-$HOME_DIR/.human-touch}"
REPO="${HUMAN_TOUCH_REPO:-https://github.com/obywans/human-touch}"
claude=0; agents=0; gemini=0
for a in "$@"; do
  case "$a" in
    --claude) claude=1;; --agents) agents=1;; --gemini-command) gemini=1;;
    -h|--help) sed -n '2,9p' "$0"; exit 0;;
    *) echo "unknown option: $a" >&2; exit 2;;
  esac
done
[ $((claude + agents + gemini)) -eq 0 ] && { claude=1; agents=1; }
command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
if [ -d "$CLONE/.git" ]; then
  git -C "$CLONE" pull --ff-only -q || { echo "could not update $CLONE" >&2; exit 1; }
else
  [ -e "$CLONE" ] && { echo "$CLONE exists and is not a HumanTouch clone; set HUMAN_TOUCH_HOME" >&2; exit 1; }
  git clone -q "$REPO" "$CLONE"
fi
SKILL="$CLONE/skills/human"
link() { # link TARGET_DIR
  mkdir -p "$(dirname "$1")"
  if [ -L "$1" ] && [ "$(readlink "$1")" = "$SKILL" ]; then echo "already installed: $1"
  elif [ -e "$1" ] || [ -L "$1" ]; then echo "SKIPPED: $1 already exists (not touched). Move it away and run again." >&2
  else ln -s "$SKILL" "$1" && echo "installed: $1 -> $SKILL"; fi
}
[ $claude -eq 1 ] && link "$HOME_DIR/.claude/skills/human"
[ $agents -eq 1 ] && link "$HOME_DIR/.agents/skills/human"
if [ $gemini -eq 1 ]; then
  f="$HOME_DIR/.gemini/commands/human.toml"; mkdir -p "$(dirname "$f")"
  if [ -e "$f" ]; then echo "SKIPPED: $f already exists (not touched)." >&2
  else
    cat > "$f" <<'TOML'
description = "HumanTouch: improve prose, clean invisible Unicode, inspect metadata, audit watermarks"
prompt = """Use the human skill (HumanTouch) on this request: {{args}}"""
TOML
    echo "installed: $f"
  fi
fi
echo "HumanTouch $(cat "$SKILL/VERSION"). Update later with: git -C \"$CLONE\" pull"
