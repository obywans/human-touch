# HumanTouch: update instructions (read this file only when check_update.py printed a notice, or when the user asks to update)

Always do the work first. Add the update notice after the reply. Write the notice in the language of the user's request.

WARNING: Never change a file or run an update command before the user agrees. Every update needs consent.

## Notice lines

`UPDATE_AVAILABLE installed=A latest=B url=U` means a skill-folder install (a git clone or a copy).
1. After the reply, ask one yes/no question. Example in Spanish: "Hay una actualización disponible: vB (tienes vA). ¿Quieres que la aplique ahora?"
2. If the user answers yes, in any language, run from the skill directory: `python3 scripts/apply_update.py --quiet`.
3. Report the real result in the user's language. If it fails, give the exact reason.
4. If the user answers no or does not answer, do nothing. Do not ask again in this session.
5. Never run `apply_update.py` before the user agrees. Never run it in the same reply that shows the question.

`PLUGIN_INSTALL installed=A latest=B url=U` means a Claude Code plugin install. Claude Code owns these files.
1. After the reply, ask the user for consent to update the plugin. Name the two versions.
2. If the user agrees, run `claude plugin marketplace update human-touch`.
3. Then run `claude plugin update human-touch@human-touch`.
4. Tell the user to restart Claude Code or to run `/reload-plugins`. The new version loads only after that.
5. If a command fails, or the tool is not allowed, show the user the exact two commands to run by hand. Do not retry.
6. Never run `apply_update.py` for a plugin install. It refuses to write in `plugins/cache` and in `plugins/marketplaces`.
7. The plugin command is `/human-touch:human`. The skill-folder command is `/human`.

`PACKAGE_INSTALL installed=A latest=B url=U` means a package install that cannot write its own files (the `human-skill.zip` for claude.ai).
1. After the reply, tell the user the new version number and the release link.
2. Tell the user to download `human-skill.zip` from the release page and to upload it again in claude.ai (Customize, Skills).
3. Do not say that the skill updated itself. It did not.
4. If the check prints nothing, say nothing.

`WIKIPEDIA_CHANGED url=U` means the source page about AI-writing patterns changed. Add one line with the URL. This line needs no answer and changes nothing.

## Claude Desktop extension (`human-touch.mcpb`)

The extension cannot update itself. The tool `human_update_check` shows the installed version, the latest version and the release link. Use it only when the user asks. Tell the user to reinstall the extension by hand.
