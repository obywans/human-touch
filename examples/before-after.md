# Before and after

These are real outputs of `/human`, recorded on the inputs in `tests/inputs/`. The raw outputs are in `tests/recorded/`. `tests/make_examples.py` builds this page from them, and `python3 tests/make_examples.py --check` fails if the two differ. Model output varies between runs, so treat these as examples, not fixed results.

## 1. Generic English text

**Before**

> In today's fast-paced world, effective communication is crucial for team success. It's important to note that clear, regular updates foster trust. Firstly, share progress early. Secondly, be specific about blockers. Finally, always follow up, because consistency matters. In conclusion, effective communication is the cornerstone of high-performing teams.

**After**

> Good communication is essential to team success. Clear, regular updates build trust. Share progress early and be specific about blockers. Always follow up, because consistency matters. Communication is the foundation of high-performing teams.
>
> *Notes: The source has no specifics (team size, tools, examples), so the claims stay general.*

What changed: The opener, "It's important to note", "Firstly / Secondly / Finally", "In conclusion", "crucial", "foster" and "cornerstone" are gone. The reason the source gives ("because consistency matters") is kept, and nothing was added.

## 2. Professional Spanish email

**Before**

> Estimado Carlos: En el mundo empresarial actual, la comunicación clara es fundamental. Cabe destacar que el proyecto se entregó el 14 de marzo con un presupuesto de 12.500 €, lo que refleja un compromiso notable con la calidad. Además, el equipo —un grupo multidisciplinar de cinco personas— logró resultados excepcionales. En definitiva, quedo a su disposición para cualquier consulta.
>
> Un cordial saludo,
> Ana García

**After**

> Estimado Carlos:
>
> La comunicación clara es fundamental en el ámbito empresarial. El proyecto se entregó el 14 de marzo con un presupuesto de 12.500 €, lo que refleja un compromiso notable con la calidad. El equipo, un grupo multidisciplinar de cinco personas, logró resultados excepcionales.
>
> Quedo a su disposición para cualquier consulta.
>
> Un cordial saludo,
>
> Ana García
>
> *Notes: "resultados excepcionales" no tiene datos concretos en el original. Si existen cifras o hechos verificables (plazos cumplidos, entregables, valoración del cliente), añadirlos reforzaría el texto sin cambiar su tono.*

What changed: "En el mundo empresarial actual", "Cabe destacar que", "Además" and "En definitiva" are gone, and the dashes around the team description became commas. The date, the budget and the team size are unchanged, and so is the usted address.

## 3. Casual English message

**Before**

> hey! so i finally finished the report, it was honestly kind of a nightmare but i think it turned out pretty good. gonna send it to Maria tomorrow, she'll probably have feedback lol. let me know if you want to grab coffee after, my treat.

**After**

> hey! so i finally finished the report, it was honestly kind of a nightmare but i think it turned out pretty good. gonna send it to Maria tomorrow, she'll probably have feedback lol. let me know if you want to grab coffee after, my treat.
>
> *Notes: The text already reads as natural casual chat with no template patterns, so I left it unchanged.*

What changed: Nothing. The message was already natural casual chat, and the chat register keeps the author's casing and punctuation.

## 4. Text that is already natural

**Before**

> Quick update: the migration script works on staging. I still need to test the rollback path, so I won't push to prod before Thursday. If you see anything weird in the logs, ping me.

**After**

> Quick update: the migration script works on staging. I still need to test the rollback path, so I won't push to prod before Thursday. If you see anything weird in the logs, ping me.
>
> *Notes: The text already reads as natural prose, so I left it unchanged. "Thursday" has no date attached, so confirm which Thursday if the timing matters.*

What changed: Nothing. "No change needed" is a valid result for a text that already reads naturally.

## 5. Long-form English essay

**Before**

> Remote work has transformed how many companies operate. In 2023, a survey of 1,200 employees across three countries found that 62% preferred hybrid arrangements over full-time office work. Moreover, the study noted that average commute time fell by 45 minutes per day for those who worked from home at least three days a week. This is a significant development that reflects broader shifts in how work is organized.
>
> However, the same survey revealed challenges. Managers reported that onboarding new hires was harder, and 38% of respondents said they felt less connected to their colleagues. Furthermore, it is important to recognize that these results vary by industry, seniority, and household situation. Some critics argue that the benefits are overstated, while others contend that the problems are largely a matter of poor management.
>
> Ultimately, the findings underscore the need for thoughtful policy design. Companies that establish clear expectations, invest in deliberate onboarding, and create regular in-person occasions tend to report better outcomes. In conclusion, remote work is not a single model but a set of choices, and those choices matter.

**After**

> Remote work has transformed how many companies operate. In 2023, a survey of 1,200 employees across three countries found that 62% preferred hybrid arrangements over full-time office work. It also noted that average commute time fell by 45 minutes per day for those who worked from home at least three days a week. These findings reflect broader shifts in how work is organized.
>
> However, the same survey revealed challenges. Managers reported that onboarding new hires was harder, and 38% of respondents said they felt less connected to their colleagues. These results vary by industry, seniority, and household situation. Some critics argue that the benefits are overstated, while others contend that the problems are largely a matter of poor management.
>
> The findings show the need for thoughtful policy design. Companies that establish clear expectations, invest in deliberate onboarding, and create regular in-person occasions tend to report better outcomes. Remote work is not a single model but a set of choices, and those choices matter.
>
> *Notes: The text does not name the survey or the critics, cite a source for the claim about better outcomes, or say what those outcomes are, so I kept these points as general as the original. Add citations if you have them.*

What changed: "Moreover", "This is a significant development that", "Furthermore, it is important to recognize that", "Ultimately" and "In conclusion" are gone, and "underscore" became "show". Every figure is unchanged, the rest keeps the author's wording, and every claim survives, including the broader shifts in how work is organized and the need for policy design.
