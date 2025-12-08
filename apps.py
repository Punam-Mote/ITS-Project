from owlready2 import *
from flask import Flask, render_template, request, jsonify
import os

# -------------------- Load Ontology --------------------
# Use absolute path to avoid path issues
OWL_FILE_PATH = os.path.join(os.path.dirname(__file__), "ITS_System_Ontology.owl")
ontology = get_ontology(OWL_FILE_PATH).load()
print(f"Loaded ontology from: {OWL_FILE_PATH}")

# -------------------- Flask App --------------------
app = Flask(__name__)

# -------------------- Helpers --------------------
def get_data_property(indiv, prop_name):
    """Safely get numeric data property from ontology individual"""
    if indiv and hasattr(indiv, prop_name):
        val = getattr(indiv, prop_name, [0])
        try:
            return float(val[0]) if val else None
        except:
            return None
    return None

def compound_interest(P, rate_percent, t, n):
    r = rate_percent / 100
    A = P * (1 + r/n) ** (n*t)
    steps = {
        "step1": "Formula: A = P*(1+r/n)^(n*t)",
        "step2": f"Substitute: A = {P}*(1+{r}/{n})^({n}*{t})",
        "step3": f"Bracket: 1 + r/n = {1 + r/n:.5f}",
        "step4": f"Exponent: n*t = {n*t}",
        "step5": f"Final Amount: A = {A:.2f}"
    }
    return round(A, 2), steps

def get_hint(concept):
    hints = {
        "Principal": "The initial amount invested.",
        "Rate": "The interest rate as a percentage.",
        "Time": "Duration of the investment in years.",
        "Compounding": "Times interest is calculated per year."
    }
    return hints.get(concept, "No hint available.")

# -------------------- Routes --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.json or {}

    formula_name = data.get("formula_name", "formula_ci")
    formula_indiv = ontology.search_one(iri=f"*{formula_name}")
    if not formula_indiv:
        return jsonify({"error": f"Individual '{formula_name}' not found in ontology."})

    # Read input or fallback to ontology
    P = float(data.get("principal") or get_data_property(formula_indiv, "Principal") or 0)
    rate = float(data.get("rate") or get_data_property(formula_indiv, "Rate") or 0)
    t = float(data.get("time") or get_data_property(formula_indiv, "Time") or 0)
    n = int(data.get("n") or get_data_property(formula_indiv, "Compounding") or 1)

    # Update ontology values
    formula_indiv.Principal = [P]
    formula_indiv.Rate = [rate]
    formula_indiv.Time = [t]
    formula_indiv.Compounding = [n] 

    # Calculate
    A, steps = compound_interest(P, rate, t, n)
    hints = {k: get_hint(k) for k in ["Principal","Rate","Time","Compounding"]}
    formula_indiv.hasValue =[A]
    formula_indiv.unit.append("Pound Sterling")

    # Save ontology
    ontology.save(file=OWL_FILE_PATH)
    print(f"Saved updated values to ontology: {formula_name} -> P:{P}, R:{rate}, T:{t}, N:{n}")

    return jsonify({
        "amount": A,
        "steps": steps,
        "hints": hints,
        "saved_to_ontology": True
    })

@app.route("/quiz", methods=["GET"])
def quiz():
    import random
    P = random.choice([500, 800, 1000, 1200, 1500])
    rate = random.choice([3, 4, 5, 6, 7])
    t = random.choice([1, 2, 3])
    n = random.choice([1, 2, 4, 12])

    A, steps = compound_interest(P, rate, t, n)
    question = f"If you invest £{P} at {rate}% for {t} year(s), compounded {n} times/year, what is the final amount?"
    hints = {k: get_hint(k) for k in ["Principal","Rate","Time","Compounding"]}

    return jsonify({"question": question, "answer": A, "steps": steps, "hints": hints})

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=True)
