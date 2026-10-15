# Walkthrough script (about 1 minute)

**The problem.** There are 12 service pages: 3 documents × 4 situations. The 4 pages of each document are almost identical, so normal similarity search easily grabs the wrong twin. And many fees depend on the person.

**1. Data.** We parse every file into its 9 official fields and drop the website menus, tabs and repeated lines. Where an amount is written in words we add the digit next to it (دينارين → 2 دينار), without changing any fact. Every piece of context is `service - field: text`.

**2. Finding the right information.** Instead of embeddings, a rule-based router that understands Jordanian dialect picks:
- the document: باسبور، هوية، دفتر العيلة
- the situation: ضاع، خرب، اهترى، خلص، أول مرة
- the field: قديش، شو بلزمني، وين، كم بياخد

ملاحظات is always included with fee, condition and timing questions, because extra charges and deadlines hide there. Each chat has its own memory, so follow-ups work. A message about several services gets each part answered.

**Hybrid retrieval.** We also use embeddings (`bge-m3`), deliberately in second position. The rules choose the service, because the twin files are too similar for vectors to separate. Inside that service, embeddings rank the fields when the wording doesn't match our keywords. The vectors live in ChromaDB (cosine distance, filtered by service). If ChromaDB isn't available, the same vectors are read from a JSON cache, so the program can never fail because of it.

**3. Fees.** The 7B model kept picking the wrong fee case, so we moved that decision into code. Each fee line is tagged with its condition (age 16, 180 days, abroad, military, nth loss, expired). The code reads the person's situation and sends only the matching line. **The documents give the rules, the code applies them, and the model only writes the sentence.**

**4. Not making things up.**
- Only the selected pieces reach the model.
- The prompt is strict, the temperature is 0, and `num_ctx` is set explicitly.
- Out-of-scope questions are declined in code, and unclear ones get a clarifying question in code.
- A fee question with no personal details is answered with the exact lines from the document.
- Totals are stripped.
- If Ollama fails, the answer falls back to the document text, so a file is always written.

**Results.** 6/6 on the practice file, and all of our own 31-message hard set covering every question type in the brief.
