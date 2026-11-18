# HumanTouch: actualización (solo si el usuario la pide o ya se avisó de UPDATE_AVAILABLE)
No aplica a instalaciones como plugin de Claude Code.

## 0. Update check (before anything else, but never blocking)

This step only applies to this installed skill form, run from its own directory (the one that contains this SKILL.md) — it has no effect in the portable adapters (ChatGPT, Gemini, local Qwen), which cannot run scripts and have no update mechanism.

From this same directory, run:

```
python3 scripts/check_update.py --quiet
```

Give it a few seconds at most. This never fails loudly and never changes anything on disk; if it prints nothing, or errors, or the file is missing, say nothing about updates and go straight to step 1 — a broken or offline check must never stop or delay the rewrite.

If it prints a line starting with `UPDATE_AVAILABLE`, remember it, but do not mention it yet.

If it prints a line starting with `PLUGIN_INSTALL`, this skill was installed as a Claude Code plugin and the plugin manager updates it. Do not ask about updating and never run `apply_update.py`; say nothing about updates unless the user asks, and then give them the command printed in `update_with`.

If it prints a line starting with `WIKIPEDIA_CHANGED`, remember it too. This only means the source Wikipedia page these patterns were informed by has changed since it was last checked — it is not a code update, and nothing about $ARGUMENTS or the rewrite changes because of it.


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
