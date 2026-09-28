# Personal Finance Advisor Bot

Flask app where you enter your monthly income, expenses and a savings goal. It sends them to Google Gemini and shows a suggested budget, which categories are overspent, and a few ways to save. Made for the SkillWallet Personal Finance Advisor Bot project.

Built with Python, Flask, Gemini API, HTML/CSS/JavaScript.

## Setup

```
python -m venv myenv
myenv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your Gemini API key (from https://aistudio.google.com).

## Run

```
python app.py
```

Open http://127.0.0.1:5000

To get a public link with ngrok, add your authtoken to `.env` and run `python run_public.py`. The free link changes every restart.

## How it works

- The form sends income, expenses and goal to `/analyse` using fetch
- `build_prompt()` makes the prompt using `CATEGORY_TIPS` and `GOAL_DESCRIPTIONS`
- Gemini replies in JSON and `extract_json()` pulls it out
- `renderResults()` in `main.js` shows the budget, status and suggestions
- There is also a `/generate` route because the project spec asks for it

Nothing is saved, every analysis is a new request.
