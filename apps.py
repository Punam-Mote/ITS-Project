from owlready2 import *
from flask import Flask, render_template, request, jsonify, session
import os
import random

# -------------------- Load Ontology --------------------
OWL_FILE_PATH = os.path.join(os.path.dirname(__file__), "ITS_System_Ontology.owl")
ontology = get_ontology(OWL_FILE_PATH).load()
print(f"Loaded ontology from: {OWL_FILE_PATH}")

# -------------------- Flask App --------------------
app = Flask(__name__)
app.secret_key = "secret123"  # needed for session memory


# -------------------- Helpers --------------------
def get_data_property(indiv, prop_name):
    """Safely retrieve numeric data property"""
    if indiv and hasattr(indiv, prop_name):
        val = getattr(indiv, prop_name, [0])
        try:
            return float(val[0])
        except Exception:
            return None
    return None


def compound_interest_detailed(P, rate_percent, t, n):
    """Compute CI with detailed, step-by-step explanation."""
    r_percent = rate_percent
    r = r_percent / 100.0
    n_times_t = n * t
    r_over_n = r / n
    base = 1 + r_over_n
    power_value = base ** n_times_t
    A = P * power_value

    steps = {
        "step1": f"Given: Principal P = £{P}, Rate r = {r_percent}% per year, Time t = {t} year(s), Compounding n = {n} time(s) per year.",
        "step2": f"Convert rate to decimal: r = {r_percent}% ÷ 100 = {r:.6f}.",
        "step3": f"Compute r/n: r/n = {r:.6f} ÷ {n} = {r_over_n:.6f}.",
        "step4": f"Compute 1 + r/n: 1 + r/n = 1 + {r_over_n:.6f} = {base:.6f}.",
        "step5": f"Compute n * t: n * t = {n} * {t} = {n_times_t}.",
        "step6": f"Raise to the power n*t: (1 + r/n)^(n*t) = {base:.6f}^{n_times_t} ≈ {power_value:.6f}.",
        "step7": f"Multiply by principal: A = P * (1 + r/n)^(n*t) = £{P} * {power_value:.6f} ≈ £{A:.2f}."
    }

    return round(A, 2), steps


def get_hint(concept):
    hints = {
        "Principal": "Principal is the starting amount of money you invest or deposit.",
        "Rate": "Rate is the interest percentage per year. Convert it to decimal by dividing by 100.",
        "Time": "Time is how long the money is invested, measured in years in this system.",
        "Compounding": "Compounding is how many times per year interest is added to the balance (yearly, monthly, etc.)."
    }
    return hints.get(concept, "No hint available.")


def difficulty_label(d):
    return {1: "EASY", 2: "MEDIUM", 3: "HARD"}.get(d, "EASY")


def init_quiz_session():
    if "difficulty" not in session:
        session["difficulty"] = 1
    if "correct_streak" not in session:
        session["correct_streak"] = 0


# -------------------- ROUTES --------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- Calculator ----------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.json or {}
    formula_indiv = ontology.search_one(iri="*formula_ci")

    if not formula_indiv:
        return jsonify({"error": "Ontology individual 'formula_ci' not found."})

    P = float(data.get("principal") or get_data_property(formula_indiv, "hasPrincipalValue") or 0)
    rate = float(data.get("rate") or get_data_property(formula_indiv, "hasRateValue") or 0)
    t = float(data.get("time") or get_data_property(formula_indiv, "hasTimeValue") or 0)
    n = int(data.get("n") or get_data_property(formula_indiv, "hasCompoundingValue") or 1)

    # Update ontology
    formula_indiv.hasPrincipalValue = [P]
    formula_indiv.hasRateValue = [rate]
    formula_indiv.hasTimeValue = [t]
    formula_indiv.hasCompoundingValue = [n]

    A, steps = compound_interest_detailed(P, rate, t, n)
    formula_indiv.hasValue = [A]

    hints = {k: get_hint(k) for k in ["Principal", "Rate", "Time", "Compounding"]}

    ontology.save(file=OWL_FILE_PATH)

    return jsonify({
        "amount": A,
        "steps": steps,
        "hints": hints
    })


# ---------- MCQ Quiz ----------
@app.route("/quiz", methods=["GET"])
def quiz():
    init_quiz_session()
    difficulty = session["difficulty"]
    d_label = difficulty_label(difficulty)

    # generate parameters based on difficulty
    if difficulty == 1:  # EASY – simple numbers
        P = random.choice([100, 200, 300])
        rate = random.choice([2, 3, 4])
        t = random.choice([1, 2])
        n = random.choice([1, 2])
        question = (
            f"If you invest £{P} at {rate}% per year for {t} year(s), "
            f"compounded {n} time(s) per year, what is the final amount?"
        )

    elif difficulty == 2:  # MEDIUM – word problem
        P = random.choice([500, 800, 1000, 1500])
        rate = random.choice([4, 5, 6])
        t = random.choice([2, 3])
        n = random.choice([2, 4, 12])
        question = (
            f"You deposit £{P} into a savings account that pays {rate}% interest per year, "
            f"compounded {n} time(s) per year, for {t} year(s).\n"
            f"How much money will you have in the account at the end?"
        )

    else:  # HARD – more conceptual wording, still numeric answer
        P = random.choice([1000, 1500, 2000, 2500])
        rate = random.choice([5, 6, 7, 8])
        t = random.choice([3, 4, 5])
        n = random.choice([4, 12])
        question = (
            f"Bank A offers {rate}% annual interest, compounded {n} time(s) per year, "
            f"on an investment of £{P} for {t} year(s).\n"
            f"Knowing that compound interest grows faster than simple interest, "
            f"what is the final amount you would have with Bank A?"
        )

    # correct answer + detailed steps
    correct_amount, steps = compound_interest_detailed(P, rate, t, n)

    # --- Build MCQ options (Style B: realistic conceptual mistakes) ---
    r = rate / 100.0
    # Simple interest (wrong: ignores compounding)
    simple_interest_amount = round(P * (1 + r * t), 2)
    # Only 1 year of growth
    one_year_only = round(P * (1 + r), 2)
    # No growth
    no_growth = round(P, 2)

    options = [correct_amount, simple_interest_amount, one_year_only, no_growth]

    # Ensure options are unique-ish
    options = list(dict.fromkeys(options))  # remove duplicates while preserving order
    while len(options) < 4:
        options.append(round(correct_amount + random.choice([-50, 50, 75]), 2))

    # Trim to exactly 4
    options = options[:4]

    # Shuffle options but remember correct index
    indexed = list(enumerate(options))
    random.shuffle(indexed)
    shuffled_options = [v for i, v in indexed]
    correct_index = [idx for idx, (orig_i, v) in enumerate(indexed) if orig_i == 0][0]

    hints = {
        "Principal": get_hint("Principal"),
        "Rate": get_hint("Rate"),
        "Time": get_hint("Time"),
        "Compounding": get_hint("Compounding")
    }

    return jsonify({
        "difficulty": d_label,
        "question": question,
        "options": shuffled_options,
        "correct_index": correct_index,
        "steps": steps,
        "hints": hints
    })


@app.route("/update_difficulty", methods=["POST"])
def update_difficulty():
    """Increase difficulty after 2 correct answers in a row. No decrease."""
    init_quiz_session()
    data = request.json or {}
    correct = bool(data.get("correct", False))

    if correct:
        session["correct_streak"] += 1
        if session["correct_streak"] >= 2 and session["difficulty"] < 3:
            session["difficulty"] += 1
            session["correct_streak"] = 0
    else:
        session["correct_streak"] = 0

    return jsonify({
        "difficulty": session["difficulty"],
        "difficulty_label": difficulty_label(session["difficulty"]),
        "correct_streak": session["correct_streak"]
    })


if __name__ == "__main__":
    app.run(debug=True)
