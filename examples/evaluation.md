# Evaluation set

Nine cases across English, Spanish, French and Romanian, and across chat, social, technical, business and personal writing. For each one: the input, the actual `/human` output recorded in `tests/recorded/`, what the rewrite was expected to change, and what it had to leave alone. This is the evidence for whether `/human` adapts to context instead of making every text sound like the same person — read the outputs side by side to judge that for yourself.

This is a quality check, not a detector test. There is no score here for passing any AI-detection tool.

## 1. Generic AI-style paragraph (English)

**Input**
> In today's fast-paced world, effective communication is crucial for team success. It's important to note that clear, regular updates foster trust. Firstly, share progress early. Secondly, be specific about blockers. Finally, always follow up, because consistency matters. In conclusion, effective communication is the cornerstone of high-performing teams.

**Output**
> Good communication is essential to team success. Clear, regular updates build trust. Share progress early and be specific about blockers. Always follow up, because consistency matters. Communication is the foundation of high-performing teams.
>
> *Notes: The source has no specifics (team size, tools, examples), so the claims stay general.*

**Should change:** the filler opener, the "Firstly/Secondly/Finally" scaffold, "crucial" and "cornerstone", and the conclusion that only restated the intro.
**Must not change:** that communication matters for team success, that updates build trust, the advice to share progress early and name blockers, and the claim that this is the foundation of high-performing teams.

## 2. Same pattern, French

**Input**
> Dans le monde d'aujourd'hui, une communication efficace est essentielle au succès de toute équipe. Il est important de noter que des mises à jour claires et régulières renforcent la confiance. Premièrement, partagez l'avancement tôt. Deuxièmement, soyez précis sur les blocages. Enfin, faites toujours un suivi, car la constance compte. En conclusion, la communication efficace est la pierre angulaire des équipes performantes.

**Output**
> Une communication efficace est essentielle au succès de toute équipe. Des mises à jour claires et régulières renforcent la confiance. Partagez l'avancement tôt. Soyez précis sur les blocages. Faites toujours un suivi, car la constance compte. C'est le fondement des équipes performantes.
>
> *Notes : le texte ne contient ni exemple ni donnée chiffrée. Je n'en ai pas ajouté, donc les affirmations restent aussi générales que la source.*

**Should change:** the same filler and numbered scaffold, in French, and "pierre angulaire".
**Must not change:** the language (French stays French), every claim, and the formal "vous"-level register the source already has.

## 3. Same pattern, Romanian

**Input**
> În lumea de astăzi, comunicarea eficientă este esențială pentru succesul echipei. Este important de menționat că actualizările clare și regulate consolidează încrederea. În primul rând, împărtășiți progresul din timp. În al doilea rând, fiți specifici în privința blocajelor. În concluzie, comunicarea eficientă este piatra de temelie a echipelor performante.

**Output**
> Comunicarea eficientă este esențială pentru succesul echipei. Actualizările clare și regulate întăresc încrederea. Împărtășiți progresul din timp și fiți specifici în privința blocajelor. Comunicarea eficientă este temelia echipelor performante.
>
> *Notes: Textul nu precizează cât de des trebuie făcute actualizările și nici ce înseamnă un blocaj concret, așa că nu am adăugat nimic din acestea.*

**Should change:** the filler opener and the "În primul rând / În al doilea rând / În concluzie" scaffold.
**Must not change:** the diacritics (ă â î ș ț), the language, and every claim, including the closing one about the foundation of high-performing teams.

## 4. Technical documentation (English)

**Input**
> To install the CLI, run npm install -g toolkit@2.4.1. The command requires Node.js 18 or later. Set the API_KEY environment variable before running toolkit sync. The sync takes about 40 seconds for a project with 1,200 files. If the sync fails with error 503, wait five minutes and retry, because the service is rate-limited per account. Logs are written to ~/.toolkit/logs/.

**Output**
> Install the CLI with `npm install -g toolkit@2.4.1`. You need Node.js 18 or later. Before you run `toolkit sync`, set the `API_KEY` environment variable. A sync takes about 40 seconds for a project with 1,200 files. If the sync fails with error 503, wait five minutes and retry, because the service is rate-limited per account. Logs are written to `~/.toolkit/logs/`.
>
> *Notes: The source was already plain technical prose, so this is a light edit that keeps every value and claim. The text does not say whether a retry after the five-minute wait can also fail with 503, or what to do then.*

**Should change:** very little. Mostly commands and paths get code formatting, which the register calls for.
**Must not change:** the version number, the Node requirement, the variable and command names, the 40-second and 1,200-file figures, the 503 code, the five-minute wait, and the log path. A technical text must stay precise, not become chatty.

## 5. Social post (English)

**Input**
> Excited to share that our team just shipped the new dashboard! 🚀 It's been a long road, but we learned so much about what our customers really need. Huge thanks to the design and backend teams. Here's to building things people actually use. #productivity #startups

**Output**
> Our team just shipped the new dashboard! 🚀 It was a long road, and we learned a lot about what our customers really need. Huge thanks to the design and backend teams. Here's to building things people actually use. #productivity #startups

**Should change:** "Excited to share that" as a canned opener.
**Must not change:** the emoji, the hashtags, the thanks to both teams, and the energy of a social post. A personal message can turn conversational; a social post can stay expressive. Flattening this into formal prose would be the wrong direction.

## 6. WhatsApp message (Spanish)

**Input**
> oye, ya llegué al hotel. la habitación es muy chica pero limpia jaja. mañana a las 9 nos vemos en la recepción? si llegas antes me avisas, que hay mucho tráfico en la avenida.

**Output**
> oye, ya llegué al hotel. la habitación es muy chica pero limpia jaja. mañana a las 9 nos vemos en la recepción? si llegas antes me avisas, que hay mucho tráfico en la avenida.
>
> *Notes: el texto ya suena natural, así que no lo cambié. "A las 9" no indica si es de mañana o de noche; si es de noche, conviene decirlo.*

**Should change:** nothing. This text is already natural chat writing.
**Must not change:** the lowercase, "jaja", the missing accents and punctuation habits, and every detail (hotel, room, 9 o'clock, traffic). Correcting a WhatsApp message's casing or spelling would be the over-editing this skill is supposed to avoid.

## 7. Business proposal (English)

**Input**
> We propose a three-phase engagement to modernize your order system. Phase one, a two-week audit, costs $12,000. Phase two, the migration of 40,000 records, is estimated at $48,000 and takes eight weeks. Phase three is ongoing support at $4,500 per month. Our team has delivered over 30 similar projects, and we believe this approach minimizes risk while delivering measurable value.

**Output**
> We propose a three-phase engagement to modernize your order system. Phase one is a two-week audit for $12,000. Phase two is the migration of 40,000 records, estimated at $48,000 over eight weeks. Phase three is ongoing support at $4,500 per month. We've delivered over 30 similar projects, and this approach minimizes risk while delivering measurable value.

**Should change:** very little; the source was already direct. "Our team has delivered" tightens to "We've delivered", and "we believe this approach" drops the hedge "we believe".
**Must not change:** every figure and duration ($12,000, $48,000, $4,500, 40,000 records, two weeks, eight weeks, 30+ projects) and the professional register. A business proposal should stay professional, not turn conversational.

## 8. Personal message (Romanian)

**Input**
> Mamă, îmi pare rău că n-am sunat ieri. Am fost tot timpul la birou și am uitat de telefon. Îți promit că duminica asta vin acasă, chiar dacă plouă. Îți iau și plăcintele tale preferate de la piață. Te iubesc.

**Output**
> Mamă, îmi pare rău că n-am sunat ieri. Am fost tot timpul la birou și am uitat de telefon. Îți promit că duminica asta vin acasă, chiar dacă plouă. Îți iau și plăcintele tale preferate de la piață. Te iubesc.
>
> *Notes: Deja citește natural — mesaj personal, direct, fără tipare artificiale. Nu am făcut modificări.*

**Should change:** nothing. Already natural, warm, personal writing.
**Must not change:** the diacritics, "Mamă", the apology, the Sunday visit, the pies, "Te iubesc". A personal message is where warmth belongs; it did not need to become more or less warm.

## 9. Technical explanation (Spanish)

**Input**
> El servicio guarda las sesiones en Redis durante 30 minutos. Si el token expira, el cliente recibe un código 401 y debe volver a autenticarse. Recomendamos aumentar el TTL solo en entornos con pocos usuarios, porque un TTL alto consume más memoria. La configuración está en config/sesiones.yml.

**Output**
> El servicio guarda las sesiones en Redis durante 30 minutos. Si expira el token, el cliente recibe un 401 y tiene que autenticarse otra vez. El TTL alto conviene solo subirlo en entornos con pocos usuarios, porque consume más memoria. La configuración está en config/sesiones.yml.
>
> *Notes: Texto ya era natural y técnico; cambios mínimos (reordené la frase del TTL para variar el ritmo, sin alterar ningún dato).*

**Should change:** little; mainly sentence order in the TTL sentence, for rhythm.
**Must not change:** Redis, the 30-minute figure, the 401 code, the TTL trade-off, and the config path. Precision stays; the text does not become more casual.

## Reading this set together

Across these nine cases the register moves from a WhatsApp message left almost untouched, to a technical paragraph that stays exact, to a business proposal that stays professional, to a social post that keeps its emoji and hashtags. If `/human` were flattening everything into one "friendly human" voice, these nine outputs would start to read alike. `tests/style_report.py` measures that directly; see its output and the note on what it does and does not prove.
