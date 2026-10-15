# -*- coding: utf-8 -*-
"""
main.py - entry point the organisers run:   python main.py questions.json   ->  answers.json

Reads every chat, answers its messages in order (one fresh memory per chat), adds "answer" and
"contexts" to every message, keeps everything else untouched. Saves after every chat, and one failing
message never stops the run.
"""
import json, os, sys, time

import bot


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "questions.json"
    out_path = os.path.join(os.path.dirname(os.path.abspath(in_path)), "answers.json")
    with open(in_path, encoding="utf-8-sig") as f:
        data = json.load(f)

    services = bot.load()
    print(f"loaded {len(services)} services from data/")
    try:
        print("model:", bot.model_name())
    except Exception as e:
        print("!! Ollama not reachable:", e, "-> answers will be the exact document text")

    chats = data.get("chats", [])
    total = sum(len(c.get("messages", [])) for c in chats)
    done, t0 = 0, time.time()
    for chat in chats:
        conv = bot.Chat(services)  # every chat is a new user: forget everything
        for msg in chat.get("messages", []):
            done += 1
            q = str(msg.get("question", ""))
            t1 = time.time()
            try:
                answer, contexts, _ = conv.ask(q)
            except Exception as e:  # never lose a message: a partial file scores better than none
                print(f"   !! error on {msg.get('message_id')}: {e}")
                answer, contexts = "عذراً، حدث خطأ أثناء معالجة السؤال.", []
            msg["answer"], msg["contexts"] = answer, contexts
            print(f"[{done}/{total}] {msg.get('message_id')}  {time.time() - t1:.1f}s  {q[:60]}")
        save(data, out_path)  # after every chat, so a crash still leaves a valid file
    save(data, out_path)
    print(f"\nwrote {out_path}  ({done} answers, {time.time() - t0:.0f}s total)")


def save(data, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
