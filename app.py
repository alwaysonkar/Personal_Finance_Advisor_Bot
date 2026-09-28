import json
import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

CATEGORY_TIPS = {
    "rent": "should be at most 30% of income",
    "food": "should stay under 15% of income",
    "transport": "should stay within 10% of income",
    "entertainment": "should be around 5-8% of income",
    "savings": "should be at least 20% of income",
}

GOAL_DESCRIPTIONS = {
    "emergency fund": "Build an emergency fund worth 3-6 months of expenses. Focus on cutting non-essentials and saving steadily.",
    "vacation": "Save up for a trip. Focus on short-term saving and trimming discretionary spending like dining and entertainment.",
    "gadget purchase": "Save for a big gadget purchase (phone, laptop etc). Suggest a monthly target and what to cut to reach it.",
    "investment": "Free up money to start investing. Focus on raising the savings rate and keeping fixed costs low.",
}

MAX_AMOUNT = 10_000_000


def get_client():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
    return genai.Client(api_key=key)


def ask_gemini(prompt, json_mode=False):
    client = get_client()
    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=4096,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    return response.text or ""


def build_prompt(income, expenses, goal):
    lines = []
    for name, amount in expenses.items():
        percent = round(amount / income * 100, 1)
        tip = CATEGORY_TIPS.get(name.lower())
        line = f"- {name}: Rs {amount:,.0f} ({percent}% of income)"
        if tip:
            line += f" | guideline: {tip}"
        lines.append(line)

    goal_text = GOAL_DESCRIPTIONS.get(goal, "General financial health and better saving habits.")

    return f"""You are a personal finance advisor for someone in India. All amounts are in Indian rupees.

Monthly income: Rs {income:,.0f}

Monthly spending:
{chr(10).join(lines)}

Financial goal: {goal}
{goal_text}

Do three things:
1. budget: a recommended monthly budget. One entry per category above (add "savings" if it is missing). The amounts should add up to at most the monthly income.
2. analysis: for each category, the percent of income currently spent, and a status: "over" if it is above the guideline or clearly too high, otherwise "ok". Add a one-line note.
3. suggestions: 3 to 5 specific actions. Each one must include a rupee amount and what it is for. Tie them to the goal.

Reply with ONLY valid JSON in exactly this shape, nothing else:
{{
  "budget": [{{"category": "rent", "amount": 15000}}],
  "analysis": [{{"category": "rent", "percent": 30.0, "status": "ok", "note": "short note"}}],
  "suggestions": ["Cut dining by Rs 1500 and move it to your emergency fund."]
}}"""


def extract_json(text):
    text = (text or "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # sometimes it comes back inside ```json fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # last try, grab everything between the first { and last }
    braces = re.search(r"\{.*\}", text, re.DOTALL)
    if braces:
        try:
            return json.loads(braces.group(0))
        except json.JSONDecodeError:
            pass

    return None


def clean_expenses(raw):
    if not isinstance(raw, dict):
        return None, "Expenses are missing."

    expenses = {}
    for name, value in raw.items():
        name = re.sub(r"[^A-Za-z ]", "", str(name)).strip()[:30]
        if not name:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None, f"Amount for {name} is not a number."
        if value < 0 or value > MAX_AMOUNT:
            return None, f"Amount for {name} is out of range."
        if value > 0:
            expenses[name] = value

    if not expenses:
        return None, "Enter at least one expense."
    return expenses, None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyse", methods=["POST"])
def analyse():
    data = request.get_json(silent=True) or {}

    try:
        income = float(data.get("income", 0))
    except (TypeError, ValueError):
        income = 0
    if income <= 0 or income > MAX_AMOUNT:
        return jsonify(success=False, error="Enter a monthly income between 1 and 1,00,00,000."), 400

    expenses, error = clean_expenses(data.get("expenses"))
    if error:
        return jsonify(success=False, error=error), 400

    goal = str(data.get("goal", "")).strip().lower()[:40]

    try:
        raw = ask_gemini(build_prompt(income, expenses, goal), json_mode=True)
    except RuntimeError as e:
        return jsonify(success=False, error=str(e)), 500
    except Exception as e:
        app.logger.error("Gemini call failed: %s", e)
        return jsonify(success=False, error="Could not reach Gemini. Check your API key and internet, then try again."), 502

    result = extract_json(raw)
    if not isinstance(result, dict) or not all(k in result for k in ("budget", "analysis", "suggestions")):
        return jsonify(success=False, error="The AI reply was not in the expected format. Please try again."), 502

    # calculating this here, don't trust the AI with the maths
    total_spent = sum(expenses.values())
    saved = expenses.get("savings", expenses.get("Savings", 0))
    summary = {
        "income": income,
        "total_spent": total_spent,
        "left_over": income - total_spent,
        "savings_rate": round(saved / income * 100, 1),
    }

    return jsonify(
        success=True,
        budget=result["budget"],
        analysis=result["analysis"],
        suggestions=result["suggestions"],
        summary=summary,
    )


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    product_info = str(data.get("product_info", "")).strip()
    platform = str(data.get("platform", "Instagram")).strip()[:30]
    tone = str(data.get("tone", "friendly")).strip()[:30]

    if not product_info or len(product_info) > 2000:
        return jsonify(success=False, error="product_info must be between 1 and 2000 characters."), 400

    prompt = (
        f"Write a short {tone} post for {platform} promoting this finance product or service:\n"
        f"{product_info}\n\nKeep it under 100 words."
    )

    try:
        text = ask_gemini(prompt)
    except RuntimeError as e:
        return jsonify(success=False, error=str(e)), 500
    except Exception as e:
        app.logger.error("Gemini call failed: %s", e)
        return jsonify(success=False, error="Could not reach Gemini."), 502

    return jsonify(success=True, content=text.strip())


if __name__ == "__main__":
    app.run(debug=True)
