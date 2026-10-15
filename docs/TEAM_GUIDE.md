# Team guide: Nashmi chatbot

**Repo:** https://github.com/m113raa/nashmi-chatbot
**Model:** `command-r7b-arabic` through Ollama. Ollama must be running.

## Open in VS Code
File → Open Folder → `C:\Downloads\nashmi-main\nashmi-hackathon`.
Python extension recommended. The terminal opens with `` Ctrl+` ``.

## Run (Run and Debug panel ▶, or F5; pick from the list)
| Config | What it does |
|---|---|
| 1. Run bot on practice questions | `python main.py questions.json` → `answers.json` (exactly what the organisers run) |
| 2. Quick test | the 10 hardest chats → `tests/quick/answers.json` |
| 3. Full hard test | all 28 chats → `tests/hard/answers.json` |
| 4. Routing check | shows which service and field each question goes to. Instant, no model |

The same commands from the terminal:
```
python main.py questions.json
cd tests\quick  && python ..\..\main.py questions.json && cd ..\..
cd tests\hard   && python ..\..\main.py questions.json && cd ..\..
python test_route.py
```
Arabic shows reversed in `cmd`. Read the results in VS Code: open the `answers.json` file.

## Where things are in bot.py
| Section | What to edit there |
|---|---|
| 1. `norm()` | Arabic spelling normalisation |
| 2. `parse_service()` / `load()` | Reading and cleaning the 12 files into 9 fields |
| 3. `DOC_WORDS`, `SIT_WORDS`, `FIELD_WORDS`, `OUT_STRONG` | **Dialect vocabulary.** A question routed wrongly is fixed here by adding a word. Write words normally; they are normalised automatically |
| 3. `route()` | Picks the document, situation and fields, and decides decline or clarify |
| 4. `select()` | Turns the route into context pieces. Asks a question when the situation is missing and the answer differs between situations |
| 5. `FEE_TAGS`, `person_profile()`, `filter_fees()` | **Fee rules in code.** Tags each fee line with its condition and keeps only the one that matches the person |
| 5. `fee_list_answer()` | Fee question with no personal details → exact list of cases, no model |
| 5. `SYSTEM`, `generate()`, `strip_totals()` | Prompt, Ollama call, removal of totals |
| 6. `Chat` | Memory per chat (follow-ups) |

## Committing (only from this laptop, straight to main)
```
git add .
git commit -m "short description"
git push
```
Push after every change that's been tested. **Stop changing code 15 minutes before the end.**

## Our test results so far
- Organisers' practice: 6/6, contexts identical to their example
- Hard set: all 31 correct after the last fixes (quick set 10/10 confirmed)
