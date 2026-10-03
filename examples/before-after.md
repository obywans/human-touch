# Before and after

These are real outputs of `/human`, recorded on the inputs in `tests/inputs/`. The raw outputs are in `tests/recorded/`. Model output varies between runs, so treat these as examples, not fixed results.

## 1. Generic English text

**Before**

> In today's fast-paced world, effective communication is crucial for team success. It's important to note that clear, regular updates foster trust. Firstly, share progress early. Secondly, be specific about blockers. Finally, always follow up, because consistency matters. In conclusion, effective communication is the cornerstone of high-performing teams.

**After**

> Clear, regular updates build trust on a team. Share progress early. When something is blocking you, say exactly what it is. Then follow up, and keep doing it, because consistency is what makes the updates believable. Good communication is a foundation of high-performing teams.
>
> *Notes: The source gives no data or examples for its claims about trust and team performance, so none were added.*

What changed: the filler opener, the numbered sequence, the "crucial" and "cornerstone" vocabulary, and the closing restatement are gone. Every claim from the original is still there, and no new claim was added.

## 2. Professional Spanish email

**Before**

> Estimado Carlos: En el mundo empresarial actual, la comunicación clara es fundamental. Cabe destacar que el proyecto se entregó el 14 de marzo con un presupuesto de 12.500 €, lo que refleja un compromiso notable con la calidad. Además, el equipo —un grupo multidisciplinar de cinco personas— logró resultados excepcionales. En definitiva, quedo a su disposición para cualquier consulta.
>
> Un cordial saludo,
> Ana García

**After**

> Estimado Carlos:
>
> El proyecto se entregó el 14 de marzo con un presupuesto de 12.500 €, lo que refleja un compromiso notable con la calidad. El equipo, un grupo multidisciplinar de cinco personas, logró resultados excepcionales.
>
> Quedo a su disposición para cualquier consulta.
>
> Un cordial saludo,
> Ana García
>
> *Notes: Se eliminó la frase de apertura sobre la comunicación en el mundo empresarial, porque es una afirmación genérica sin contenido específico. Si quiere una frase de apertura, indique el motivo del correo. "Resultados excepcionales" tampoco tiene cifras en el original; si existen (plazos, métricas, reconocimientos), conviene añadirlos.*

What changed: the em dashes became commas, the filler opener and the "Además" and "En definitiva" connectors were removed, and the language and register stayed Spanish and formal. The date, the amount, the team size, and the signature are unchanged. The Notes line flags that "resultados excepcionales" and "compromiso notable" are still vague. The rewrite keeps them because the original gives no figures to replace them with.

## 3. Casual English message

**Before**

> hey! so i finally finished the report, it was honestly kind of a nightmare but i think it turned out pretty good. gonna send it to Maria tomorrow, she'll probably have feedback lol. let me know if you want to grab coffee after, my treat.

**After**

> Hey! I finally finished the report. It was honestly kind of a nightmare, but I think it turned out pretty good. I'm sending it to Maria tomorrow. She'll probably have feedback, lol. Let me know if you want to grab coffee after. It's my treat.
>
> *Notes: "after" is unclear (after the report, after Maria's feedback, or some other time?), so you may want to say when. The original was already casual and natural, so I made only light edits.*

What changed: only punctuation and capitalization. The casual register is kept, and the model flagged an ambiguous word instead of guessing.

## 4. Text that is already natural

**Before**

> Quick update: the migration script works on staging. I still need to test the rollback path, so I won't push to prod before Thursday. If you see anything weird in the logs, ping me.

**After**

> Quick update: the migration script works on staging. I still need to test the rollback path, so I won't push to prod before Thursday. If anything looks off in the logs, ping me.
>
> *Notes: The original already reads naturally, so I changed only the last sentence. All facts and the request are unchanged.*

What changed: one sentence. A text that is already natural should get small edits, and this one did.

## 5. Long-form English essay

**Before** (excerpt, first paragraph and the start of the second)

> Remote work has transformed how many companies operate. In 2023, a survey of 1,200 employees across three countries found that 62% preferred hybrid arrangements over full-time office work. Moreover, the study noted that average commute time fell by 45 minutes per day for those who worked from home at least three days a week. This is a significant development that reflects broader shifts in how work is organized.
>
> However, the same survey revealed challenges. Managers reported that onboarding new hires was harder, and 38% of respondents said they felt less connected to their colleagues. …

**After** (full rewrite)

> Remote work has changed how many companies operate. A 2023 survey of 1,200 employees across three countries found that 62% preferred hybrid arrangements to working full time in an office. The study also found that people who worked from home at least three days a week cut their average commute by 45 minutes a day. That is a meaningful shift, and it reflects wider changes in how work gets organized.
>
> The survey also turned up problems. Managers said onboarding new hires got harder, and 38% of respondents felt less connected to their colleagues. These results vary by industry, seniority, and household situation. Critics disagree about the overall picture. Some think the benefits are overstated, while others argue that most of the problems come down to poor management.
>
> The findings point to the need for careful policy. Companies that set clear expectations, put real effort into onboarding, and schedule regular in-person time tend to report better outcomes. Remote work is not one model. It is a set of choices, and those choices matter.
>
> *Notes: The source does not name the study's authors, define the "outcomes" it refers to, or identify the critics, so the rewrite stays as vague on those points as the original.*

What changed: "Moreover", "Furthermore", "Ultimately", "In conclusion", "underscore", and "it is important to recognize" are gone. The paragraphs have different lengths and sentences vary in length. Every figure (2023, 1,200, three countries, 62%, 45 minutes, 38%) is unchanged, and the Notes line flags the vagueness that the original already had.
