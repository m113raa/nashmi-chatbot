# Nashmi Pro: Government Services Chatbot

Answers citizens' questions about Jordan's **passport, family book and smart ID** services
(first issue, renewal, lost, damaged), only from the 12 official documents in `data/`.

## How to run

```
ollama pull command-r7b-arabic
python main.py questions.json        # writes answers.json next to questions.json
```

- Pure Python standard library: **no pip install, no virtual environment.**
- Ollama is called over HTTP at `http://localhost:11434`.
- The model defaults to `command-r7b-arabic`. To use another one, set `LLM_MODEL`.
- If Ollama is unreachable, every answer falls back to the exact document text, so `answers.json` is always written.

## Files

| File | What it does |
|---|---|
| `main.py` | Entry point. Reads the questions and writes `answers.json`. Gives every chat its own memory, catches errors per message, and saves after every chat |
| `bot.py` | Parsing, routing, situation facts, prompt and the Ollama call |
| `data/` | The 12 service files |
| `test_route.py` | Shows which service and fields each question is routed to, with no model needed |
| `tests/hard/questions.json` | Our own 28-chat test set, covering every question type in the brief |
| `tests/quick/questions.json` | A 7-chat subset for fast checks |

## How it works

**1. Handling the data.** Each file is parsed into its 9 official fields (beneficiaries, places, conditions, documents, procedure, time, partners, notes, fees). The cleaning:
- removes website menu lines and repeated lines
- normalises tabs and whitespace
- adds digits next to amounts written as words (دينارين → 2 دينار), without changing any fact

Each piece of context looks like `تجديد دفتر العائلة - الرسوم: ...`.

**2. Finding the right information.** The 4 files of each document are near-identical, so similarity search (BM25 or embeddings) easily picks the wrong twin. Instead, a **dialect-aware rule-based router** reads the question and picks:
- the **document**: جواز / باسبور، دفتر العيلة، هوية / بطاقة
- the **situation**: أول مرة / تجديد / فاقد / تالف, including dialect such as ضاع، خرب، اهترى، خلص
- the **field(s)**: رسوم / قديش، أوراق / شو بلزم، وين، كم بياخد

It also handles:
- **Several services in one message:** each clause is paired with its own situation.
- **Comparisons**
- **Follow-ups:** a memory per chat, so "وكم بتكلف؟" or "وإذا ضاع؟" refer to the earlier question.
- **Hidden rules:** ملاحظات is always attached to fee, condition and timing questions, because extra charges and deadlines hide there.

**3. The code applies the fee rules.** Many fees depend on the person, and in our tests the 7B model picked a different fee case whenever the prompt changed slightly. So every fee line is tagged with its condition (military, under/over 16, less/more than 180 days left, abroad, full pages, 1st/2nd loss, expired/not expired). The code reads the person's situation from the whole chat and sends **only the matching fee line** to the model and into `contexts`. If the person gave no details, every line goes, so the answer lists the cases. The code also gives the model plain facts:
- age vs. 16 and 18
- time left on the document vs. 180 days
- time since the marriage vs. 90 days
- abroad
- military
- 1st / 2nd / 3rd loss
- urgent service

The documents give the rules, the code applies them, and the model only writes the sentence. Any total line the model adds is removed, because the documents never give totals.

**4. Not making things up.**
- Only the selected pieces are sent to the model.
- The prompt is strict: answer only from the text, copy the numbers exactly, correct wrong assumptions, never assume facts about the asker.
- Temperature is 0.
- `num_ctx` is set explicitly so nothing is cut off silently.
- **Declining** out-of-scope questions (flight tickets, certificates, a diplomatic passport, a driving licence) is done in code, with empty contexts.
- **Asking for clarification** when the document or the situation is missing (بدي أجدد، شو المطلوب؟ / كم رسوم الجواز؟) is also done in code. When the answer is the same for all 4 situations (time, place, a shared note), it answers directly instead of asking.

## Testing

```
python test_route.py                                  # routing only, instant, no model
cd tests\quick && python ..\..\main.py questions.json   # 7 chats, ~1 min
cd tests\hard  && python ..\..\main.py questions.json   # 31 messages, ~6 min
```
