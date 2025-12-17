from flask import Flask, request, jsonify, render_template
from owlready2 import get_ontology, onto_path, Thing
import random
import time


# ===========================
# Ontology loading
# ===========================
OWL_FILE_PATH = "ITS_System_Ontology.owl"
onto_path.append(".")
ontology = get_ontology(OWL_FILE_PATH).load()
print("[INFO] Loaded ontology:", OWL_FILE_PATH)

app = Flask(__name__)


# ===========================
# Helper functions
# ===========================

def get_float_prop(indiv, prop_name, default=None):
    """Safely read a float data property from an individual."""
    if indiv is None:
        return default
    if not hasattr(indiv, prop_name):
        return default
    values = getattr(indiv, prop_name)
    if not values:
        return default
    try:
        return float(values[0])
    except Exception:
        return default


def get_int_prop(indiv, prop_name, default=None):
    """Same as get_float_prop, but casts to int."""
    val = get_float_prop(indiv, prop_name, default)
    if val is None:
        return default
    try:
        return int(val)
    except Exception:
        return default


def get_or_create_student():
    """Get or create the main Student individual (student_1)."""
    student = ontology.search_one(iri="*student_1")

    # If Student class doesn't exist, quietly skip learner model
    if student is None and not hasattr(ontology, "Student"):
        print("[WARN] No Student class in ontology.")
        return None

    with ontology:
        if student is None:
            print("[INFO] Creating student_1 individual")
            student = ontology.Student("student_1")

        # Ensure score, streak, difficulty exist
        if not getattr(student, "hasScore", []):
            student.hasScore = [0]
        if not getattr(student, "hasCorrectStreak", []):
            student.hasCorrectStreak = [0]
        if not getattr(student, "hasDifficultyLevel", []):
            student.hasDifficultyLevel = [1]

    return student


def get_hint(concept):
    hints = {
        "Principal": "The initial amount invested (P).",
        "Rate": "The interest rate as a percentage per year (r).",
        "Time": "The total number of years the money is invested (t).",
        "Compounding": "How many times per year interest is added (n)."
    }
    return hints.get(concept, "No hint available.")


def compound_interest(P, rate_percent, t, n):
    """
    A = P * (1 + r/n)^(n*t)
    Returns (rounded_amount, steps_dict)
    """
    r = rate_percent / 100.0
    A = P * (1 + r / n) ** (n * t)

    steps = {
        "1": "Formula: A = P × (1 + r/n)^(n × t)",
        "2": f"Step 1 – Convert rate: r = {rate_percent}% = {r:.4f}",
        "3": f"Step 2 – Compute r/n: r/n = {r}/{n} = {r/n:.5f}",
        "4": f"Step 3 – Inside bracket: 1 + r/n = {1 + r/n:.5f}",
        "5": f"Step 4 – Exponent: n × t = {n} × {t} = {n*t}",
        "6": f"Step 5 – Final: A = {P} × (1 + r/n)^(n×t) = £{A:.2f}"
    }

    return round(A, 2), steps


# ===========================
# Misconception detection
# ===========================

def detect_misconception(P, rate, t, n, user_answer, correct_amount):
    """Return a misconception name string or None."""
    # Simple interest: A = P(1 + r*t)
    si = P * (1 + (rate / 100) * t)
    if abs(user_answer - si) < 1.0:
        return "mis_simple_interest"

    # Ignore compounding frequency (treat n=1)
    annual = P * (1 + rate / 100) ** t
    if abs(user_answer - annual) < 1.0 and n != 1:
        return "mis_ignore_compounding"

    # One-year-only
    one_year = P * (1 + (rate / 100) / n) ** n
    if abs(user_answer - one_year) < 1.0 and t > 1:
        return "mis_one_year_only"

    # Wrong rate conversion (used 5 instead of 0.05)
    wrong_rate = P * (1 + rate / n) ** (n * t)
    if abs(user_answer - wrong_rate) < 1.0:
        return "mis_wrong_rate_conversion"

    return None


def log_calculation_record(student, P, rate, t, n, correct_amount,
                           difficulty, is_correct, misconception_name):
    """Save a CalculationRecord instance and link to Student + Misconception."""
    if student is None:
        return
    if not hasattr(ontology, "CalculationRecord"):
        print("[WARN] CalculationRecord class missing.")
        return

    with ontology:
        rec_name = f"record_{int(time.time())}"
        rec = ontology.CalculationRecord(rec_name)

        if hasattr(rec, "recordPrincipal"):
            rec.recordPrincipal = [P]
        if hasattr(rec, "recordRate"):
            rec.recordRate = [rate]
        if hasattr(rec, "recordTime"):
            rec.recordTime = [t]
        if hasattr(rec, "recordCompounding"):
            rec.recordCompounding = [n]
        if hasattr(rec, "recordResult"):
            rec.recordResult = [correct_amount]
        if hasattr(rec, "recordDifficulty"):
            rec.recordDifficulty = [difficulty]
        if hasattr(rec, "recordCorrect"):
            rec.recordCorrect = [1 if is_correct else 0]

        # Link student
        if hasattr(rec, "belongsToStudent"):
            rec.belongsToStudent = [student]
        if hasattr(student, "performsCalculation"):
            student.performsCalculation.append(rec)

        # Link misconception
        if misconception_name:
            mis_indiv = ontology.search_one(iri=f"*{misconception_name}")
            if mis_indiv and hasattr(rec, "hasMisconception"):
                rec.hasMisconception = [mis_indiv]

    print(f"[INFO] Logged CalculationRecord: {rec_name}")


def update_student_profile(student, difficulty, is_correct):
    """Update student score, streak and difficulty in ontology."""
    if student is None:
        return 0, 0, difficulty

    score = get_int_prop(student, "hasScore", 0)
    streak = get_int_prop(student, "hasCorrectStreak", 0)
    diff = get_int_prop(student, "hasDifficultyLevel", 1)

    if is_correct:
        score += 1
        streak += 1
    else:
        streak = 0

    # Difficulty adaptation
    if is_correct and streak >= 3 and diff < 3:
        diff += 1
        streak = 0
    elif (not is_correct) and diff > 1:
        diff -= 1

    with ontology:
        student.hasScore = [score]
        student.hasCorrectStreak = [streak]
        student.hasDifficultyLevel = [diff]

    return score, streak, diff


# ===========================
# Routes
# ===========================

@app.route("/")
def index():
    return render_template("index.html")


# ---------- CALCULATE (calculator) ----------
@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.json or {}
    try:
        P = float(data.get("principal", 0))
        rate = float(data.get("rate", 0))
        t = float(data.get("time", 0))
        n = int(data.get("n", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid input."}), 400

    A, steps = compound_interest(P, rate, t, n)
    hints = {
        "Principal": get_hint("Principal"),
        "Rate": get_hint("Rate"),
        "Time": get_hint("Time"),
        "Compounding": get_hint("Compounding")
    }

    # Save to formula_ci individual if it exists
    formula = ontology.search_one(iri="*formula_ci")
    with ontology:
        if formula:
            if hasattr(formula, "hasPrincipalValue"):
                formula.hasPrincipalValue = [P]
            if hasattr(formula, "hasRateValue"):
                formula.hasRateValue = [rate]
            if hasattr(formula, "hasTimeValue"):
                formula.hasTimeValue = [t]
            if hasattr(formula, "hasCompoundingValue"):
                formula.hasCompoundingValue = [n]
            if hasattr(formula, "hasAmountValue"):
                formula.hasAmountValue = [A]

    ontology.save(file=OWL_FILE_PATH)
    print("[INFO] Ontology saved after /calculate")

    return jsonify({"amount": A, "steps": steps, "hints": hints})


# ---------- QUIZ: Get new question ----------
@app.route("/quiz", methods=["GET"])
@app.route("/quiz", methods=["GET"])
def quiz():
    student = get_or_create_student()
    difficulty = get_int_prop(student, "hasDifficultyLevel", 1)

    # Generate numbers according to difficulty
    if difficulty == 1:  # Easy
        P = random.choice([100, 200, 300])
        rate = random.choice([2, 3, 4])
        t = random.choice([1, 2])   # <-- CHANGED: sometimes time > 1
        n = 1

    elif difficulty == 2:  # Medium
        P = random.choice([300, 500, 800])
        rate = random.choice([3, 4, 5])
        # 80% chance of time > 1 --> Helps trigger mis_one_year_only
        t = 2 if random.random() < 0.8 else 1
        n = random.choice([1, 2, 4])

    else:  # Hard
        P = random.choice([800, 1000, 1500])
        rate = random.choice([5, 6, 7])
        t = random.choice([2, 3])   # already > 1
        n = random.choice([4, 6, 12])

    question = (
        f"(Level {difficulty}) If you invest £{P} at {rate}% for {t} year(s), "
        f"compounded {n} times per year, what is the final amount?"
    )

    return jsonify({
        "question": question,
        "principal": P,
        "rate": rate,
        "time": t,
        "n": n,
        "difficulty": difficulty
    })

# ---------- QUIZ: Check answer ----------
@app.route("/quiz_check", methods=["POST"])
def quiz_check():
    data = request.json or {}
    try:
        P = float(data["principal"])
        rate = float(data["rate"])
        t = float(data["time"])
        n = int(data["n"])
        user_answer = float(data["user_answer"])
        difficulty = int(data["difficulty"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Invalid quiz data."}), 400

    correct_amount, steps = compound_interest(P, rate, t, n)
    hints = {
        "Principal": get_hint("Principal"),
        "Rate": get_hint("Rate"),
        "Time": get_hint("Time"),
        "Compounding": get_hint("Compounding")
    }

    is_correct = abs(user_answer - correct_amount) < 0.01

    # Misconception detection
    mis_name = None
    if not is_correct:
        mis_name = detect_misconception(P, rate, t, n, user_answer, correct_amount)

    # Student update + record logging
    student = get_or_create_student()
    score, streak, new_diff = update_student_profile(student, difficulty, is_correct)
    log_calculation_record(student, P, rate, t, n, correct_amount,
                           difficulty, is_correct, mis_name)

    ontology.save(file=OWL_FILE_PATH)
    print("[INFO] Ontology saved after /quiz_check")

    return jsonify({
        "correct": is_correct,
        "correct_amount": correct_amount,
        "steps": steps,
        "hints": hints,
        "misconception": mis_name,
        "difficulty": new_diff,
        "score": score,
        "streak": streak
    })


if __name__ == "__main__":
    app.run(debug=True)
