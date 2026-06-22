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
                "content": f"""Translate the following English phrase into Cantonese (Traditional Chinese as spoken in Hong Kong).

Provide:
1. The Cantonese Chinese characters (Traditional)
2. The Jyutping romanization (phonetic pronunciation guide)
3. A literal pronunciation hint in plain English syllables (to help someone pronounce it phonetically without knowing Jyutping)

English: {english}

Respond in this exact JSON format:
{{
  "cantonese": "Traditional Chinese characters here",
  "jyutping": "jyutping romanization here",
  "phonetic": "easy English phonetic hint here"
}}

Only output the JSON, nothing else.""",
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
