import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, g
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = Flask(__name__)

# Use /data/phrases.db on Railway (persistent volume), local db otherwise
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "phrases.db"))

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS phrases (
                id TEXT PRIMARY KEY,
                english TEXT,
                cantonese TEXT,
                jyutping TEXT,
                phonetic TEXT,
                created TEXT
            )
        """)
        db.commit()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/translate", methods=["POST"])
def translate():
    data = request.get_json()
    english = data.get("english", "").strip()
    if not english:
        return jsonify({"error": "No text provided"}), 400

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"""You are a Hong Kong Cantonese language expert. Translate the English phrase below into HONG KONG CANTONESE — NOT Mandarin, NOT Putonghua, NOT simplified Chinese.

Rules:
- Use Traditional Chinese characters (繁體字) as written in Hong Kong
- Use authentic Cantonese vocabulary and grammar, NOT Mandarin words written in Traditional characters
- For example: "to eat" is 食 (sik6) in Cantonese, NOT 吃; "don't have" is 冇 (mou5), NOT 沒有; "very" is 好 (hou2), NOT 很
- Use colloquial spoken Hong Kong Cantonese, not formal written Chinese
- Provide Jyutping romanization (the standard Cantonese phonetic system with tone numbers 1-6)
- Provide a phonetic hint written as English syllables, exactly how an English speaker living in Hong Kong would say it out loud
- Use these sound mappings consistently:
  INITIALS: z/j → "j" (早=jow, 知=jee), c → "ch" (車=cheh, 錯=chaw), s → "s", g → "g", k → "k", ng → "ng", gw → "gw", kw → "kw", h → "h", f → "f", l → "l", m → "m", n → "n", w → "w", b → "b", p → "p", d → "d", t → "t"
  VOWELS/FINALS: aa → "ah", aai → "eye", aau → "ow", aam → "aam", aan → "aan", aang → "aang", aak → "ahk", aap → "aap", aat → "aat", ai → "eye", au → "oh", am → "um", an → "un", ang → "ung", ak → "uk", ap → "up", at → "ut", ei → "ay", eu/eo → "er", i → "ee", iu → "yew", im → "im", in → "in", ing → "ing", ik → "ik", ip → "ip", it → "it", o → "oh", oi → "oy", ou → "oh", on → "on", ong → "ong", ok → "ok", op → "op", ot → "ot", u → "oo", ui → "wee", un → "oon", ung → "oong", uk → "ook", ut → "oot", yu → "yü" (use "ew" for English speakers), yun → "ewn", yut → "ewt"
  STANDALONE SYLLABLES: 唔(m4)="m", 吳(ng4)="ng"
  TONES: ignore tone numbers in the phonetic — just write the syllables naturally
- Examples: 早晨="Jow sun", 你好="Nay ho", 唔該="M-goy", 多謝="Doh jeh", 好味="Ho may", 係="Hay", 唔係="M-hay", 邊度="Bin doh", 去="Hoy", 食="Sik", 飲="Yum", 幾多錢="Gay daw chin"
- Hyphenate syllables within a word, space between words. Capitalise the first syllable only

English: {english}

Respond ONLY in this exact JSON format, no extra text:
{{
  "cantonese": "Traditional Chinese characters (Hong Kong Cantonese)",
  "jyutping": "jyutping with tone numbers",
  "phonetic": "easy English syllables e.g. nay ho ma"
}}""",
            }
        ],
    )

    try:
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Translation failed", "raw": message.content[0].text}), 500


@app.route("/api/phrases", methods=["GET"])
def get_phrases():
    db = get_db()
    rows = db.execute("SELECT * FROM phrases ORDER BY created DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/phrases", methods=["POST"])
def add_phrase():
    data = request.get_json()
    phrase = {
        "id": datetime.now().isoformat(),
        "english": data.get("english", ""),
        "cantonese": data.get("cantonese", ""),
        "jyutping": data.get("jyutping", ""),
        "phonetic": data.get("phonetic", ""),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    db = get_db()
    db.execute(
        "INSERT INTO phrases (id, english, cantonese, jyutping, phonetic, created) VALUES (?,?,?,?,?,?)",
        (phrase["id"], phrase["english"], phrase["cantonese"], phrase["jyutping"], phrase["phonetic"], phrase["created"])
    )
    db.commit()
    return jsonify(phrase)


@app.route("/api/phrases/<phrase_id>", methods=["DELETE"])
def delete_phrase(phrase_id):
    db = get_db()
    db.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    print("Cantonese Learning App running at http://localhost:5100")
    app.run(debug=True, port=5100)


# For gunicorn (Railway)
init_db()
