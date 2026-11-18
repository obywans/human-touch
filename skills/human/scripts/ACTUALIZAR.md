# HumanTouch: actualización (se lee cuando check_update.py imprime un aviso, o si el usuario la pide)

## Update notices (after the reply)

## 8. Update apply (only on explicit consent, after the reply, never before or during)

This applies only when step 0 printed `UPDATE_AVAILABLE` in this same conversation and the reply asked the yes/no question above.

If the user's next message answers yes, in any language or phrasing ("sí", "yes", "da", "oui", "ok", "update it") — run, from the same directory:

```
python3 scripts/apply_update.py --quiet
```

Report the real outcome to the user, in their language: success, or the exact reason it failed (nothing on disk changes on failure, and they can still run the command themselves later). If they answer no, or answer something else entirely, do not run it, and do not ask again this session unless they bring it up.

Never run this before or during the reply that first shows the question — it must never change what the user just received, only what a future `/human` call reads. Never run it speculatively without an explicit yes.

## Avisos al final de la respuesta (si el paso 0 los imprimió)

If step 0 printed `UPDATE_AVAILABLE`, add one more line after everything else, in the language of the user's request (not necessarily the rewrite's language), asking whether to update now — for example, in Spanish: "Hay una actualización disponible: vX.Y.Z (tienes vA.B.C). ¿Quieres que la aplique ahora?" Phrase it as a real yes/no question in that language; do not just state the version and a command to run.

If step 0 printed `WIKIPEDIA_CHANGED`, add one more line after everything else (after the update question too, if both printed), also in the language of the user's request: a notice that the source Wikipedia page for AI-writing patterns changed, with its URL. This does not change anything automatically and needs no answer.

If step 0 printed `PLUGIN_INSTALL`, this copy was installed as a Claude Code plugin, which is no longer supported (its command would be `/human-touch:human`). Never run `apply_update.py`. After the reply, add one line in the user's language that tells the user to migrate once, with the `migrate` text it printed.
