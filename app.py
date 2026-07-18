"""
AgroVision backend — Phase 2

Endpoints:
  POST   /api/auth/register
  POST   /api/auth/login
  GET    /api/auth/me

  GET    /api/farms
  POST   /api/farms
  GET    /api/farms/<farm_id>
  PUT    /api/farms/<farm_id>
  DELETE /api/farms/<farm_id>

  GET    /api/farms/<farm_id>/crops
  POST   /api/farms/<farm_id>/crops
  PUT    /api/crops/<crop_id>
  DELETE /api/crops/<crop_id>

  GET    /api/crops/<crop_id>/harvests
  POST   /api/crops/<crop_id>/harvests

  GET    /api/farms/<farm_id>/records
  POST   /api/farms/<farm_id>/records

Run locally:
  pip install flask pyjwt
  python app.py
  -> serves on http://localhost:5000
"""
from functools import wraps
from datetime import datetime, timedelta, timezone

import jwt
from flask import Flask, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db, row_to_dict, rows_to_list

app = Flask(__name__)
SECRET_KEY = "dev-secret-change-this-before-deploying"  # move to an env var in production
TOKEN_TTL_HOURS = 24 * 7


# ---------------------------------------------------------------- CORS ----
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


# ------------------------------------------------------------ helpers -----
def make_token(user):
    payload = {
        "sub": user["id"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="Missing or invalid Authorization header"), 401
        token = header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify(error="Token expired, please log in again"), 401
        except jwt.InvalidTokenError:
            return jsonify(error="Invalid token"), 401
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
        db.close()
        if not user:
            return jsonify(error="User no longer exists"), 401
        g.user = dict(user)
        return fn(*args, **kwargs)
    return wrapper


def owns_farm_or_staff(db, farm_id, user):
    farm = db.execute("SELECT * FROM farms WHERE id = ?", (farm_id,)).fetchone()
    if not farm:
        return None
    if farm["owner_id"] != user["id"] and user["role"] not in ("admin", "agronomist"):
        return False
    return farm


# --------------------------------------------------------------- auth -----
@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    name, email, password = data.get("name"), data.get("email"), data.get("password")
    role = data.get("role", "farmer")
    if not name or not email or not password:
        return jsonify(error="name, email and password are required"), 400
    if role not in ("farmer", "agronomist", "admin"):
        role = "farmer"

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify(error="An account with that email already exists"), 409

    pw_hash = generate_password_hash(password)
    cur = db.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, email, pw_hash, role),
    )
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()

    user = dict(user)
    token = make_token(user)
    user.pop("password_hash")
    return jsonify(token=token, user=user), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify(error="email and password are required"), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Invalid email or password"), 401

    user = dict(user)
    token = make_token(user)
    user.pop("password_hash")
    return jsonify(token=token, user=user)


@app.get("/api/auth/me")
@auth_required
def me():
    user = dict(g.user)
    user.pop("password_hash")
    return jsonify(user=user)


# -------------------------------------------------------------- farms -----
@app.get("/api/farms")
@auth_required
def list_farms():
    db = get_db()
    if g.user["role"] in ("admin", "agronomist"):
        rows = db.execute("SELECT * FROM farms ORDER BY created_at DESC").fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM farms WHERE owner_id = ? ORDER BY created_at DESC", (g.user["id"],)
        ).fetchall()
    db.close()
    return jsonify(farms=rows_to_list(rows))


@app.post("/api/farms")
@auth_required
def create_farm():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify(error="name is required"), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO farms (owner_id, name, location, size_ha) VALUES (?, ?, ?, ?)",
        (g.user["id"], name, data.get("location"), data.get("size_ha")),
    )
    db.commit()
    farm = db.execute("SELECT * FROM farms WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(farm=row_to_dict(farm)), 201


@app.get("/api/farms/<int:farm_id>")
@auth_required
def get_farm(farm_id):
    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    db.close()
    if farm is None:
        return jsonify(error="Farm not found"), 404
    if farm is False:
        return jsonify(error="You don't have access to this farm"), 403
    return jsonify(farm=row_to_dict(farm))


@app.put("/api/farms/<int:farm_id>")
@auth_required
def update_farm(farm_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if farm is None:
        db.close()
        return jsonify(error="Farm not found"), 404
    if farm is False:
        db.close()
        return jsonify(error="You don't have access to this farm"), 403

    db.execute(
        "UPDATE farms SET name = ?, location = ?, size_ha = ? WHERE id = ?",
        (
            data.get("name", farm["name"]),
            data.get("location", farm["location"]),
            data.get("size_ha", farm["size_ha"]),
            farm_id,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM farms WHERE id = ?", (farm_id,)).fetchone()
    db.close()
    return jsonify(farm=row_to_dict(updated))


@app.delete("/api/farms/<int:farm_id>")
@auth_required
def delete_farm(farm_id):
    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if farm is None:
        db.close()
        return jsonify(error="Farm not found"), 404
    if farm is False:
        db.close()
        return jsonify(error="You don't have access to this farm"), 403
    db.execute("DELETE FROM farms WHERE id = ?", (farm_id,))
    db.commit()
    db.close()
    return jsonify(message="Farm deleted")


# -------------------------------------------------------------- crops -----
@app.get("/api/farms/<int:farm_id>/crops")
@auth_required
def list_crops(farm_id):
    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if not farm:
        db.close()
        return jsonify(error="Farm not found or access denied"), 404
    rows = db.execute(
        "SELECT * FROM crops WHERE farm_id = ? ORDER BY created_at DESC", (farm_id,)
    ).fetchall()
    db.close()
    return jsonify(crops=rows_to_list(rows))


@app.post("/api/farms/<int:farm_id>/crops")
@auth_required
def add_crop(farm_id):
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify(error="name is required"), 400

    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if not farm:
        db.close()
        return jsonify(error="Farm not found or access denied"), 404

    cur = db.execute(
        "INSERT INTO crops (farm_id, name, variety, area_ha, planting_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            farm_id,
            name,
            data.get("variety"),
            data.get("area_ha"),
            data.get("planting_date"),
            data.get("status", "growing"),
        ),
    )
    db.commit()
    crop = db.execute("SELECT * FROM crops WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(crop=row_to_dict(crop)), 201


@app.put("/api/crops/<int:crop_id>")
@auth_required
def update_crop(crop_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    crop = db.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    if not crop:
        db.close()
        return jsonify(error="Crop not found"), 404
    farm = owns_farm_or_staff(db, crop["farm_id"], g.user)
    if not farm:
        db.close()
        return jsonify(error="Access denied"), 403

    db.execute(
        "UPDATE crops SET name=?, variety=?, area_ha=?, planting_date=?, status=? WHERE id=?",
        (
            data.get("name", crop["name"]),
            data.get("variety", crop["variety"]),
            data.get("area_ha", crop["area_ha"]),
            data.get("planting_date", crop["planting_date"]),
            data.get("status", crop["status"]),
            crop_id,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    db.close()
    return jsonify(crop=row_to_dict(updated))


@app.delete("/api/crops/<int:crop_id>")
@auth_required
def delete_crop(crop_id):
    db = get_db()
    crop = db.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    if not crop:
        db.close()
        return jsonify(error="Crop not found"), 404
    farm = owns_farm_or_staff(db, crop["farm_id"], g.user)
    if not farm:
        db.close()
        return jsonify(error="Access denied"), 403
    db.execute("DELETE FROM crops WHERE id = ?", (crop_id,))
    db.commit()
    db.close()
    return jsonify(message="Crop deleted")


# ----------------------------------------------------------- harvests -----
@app.get("/api/crops/<int:crop_id>/harvests")
@auth_required
def list_harvests(crop_id):
    db = get_db()
    crop = db.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    if not crop:
        db.close()
        return jsonify(error="Crop not found"), 404
    farm = owns_farm_or_staff(db, crop["farm_id"], g.user)
    if not farm:
        db.close()
        return jsonify(error="Access denied"), 403
    rows = db.execute(
        "SELECT * FROM harvests WHERE crop_id = ? ORDER BY harvest_date DESC", (crop_id,)
    ).fetchall()
    db.close()
    return jsonify(harvests=rows_to_list(rows))


@app.post("/api/crops/<int:crop_id>/harvests")
@auth_required
def add_harvest(crop_id):
    data = request.get_json(silent=True) or {}
    harvest_date, quantity_kg = data.get("harvest_date"), data.get("quantity_kg")
    if not harvest_date or quantity_kg is None:
        return jsonify(error="harvest_date and quantity_kg are required"), 400

    db = get_db()
    crop = db.execute("SELECT * FROM crops WHERE id = ?", (crop_id,)).fetchone()
    if not crop:
        db.close()
        return jsonify(error="Crop not found"), 404
    farm = owns_farm_or_staff(db, crop["farm_id"], g.user)
    if not farm:
        db.close()
        return jsonify(error="Access denied"), 403

    cur = db.execute(
        "INSERT INTO harvests (crop_id, harvest_date, quantity_kg, quality_grade, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (crop_id, harvest_date, quantity_kg, data.get("quality_grade"), data.get("notes")),
    )
    db.execute("UPDATE crops SET status = 'harvested' WHERE id = ?", (crop_id,))
    db.commit()
    harvest = db.execute("SELECT * FROM harvests WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(harvest=row_to_dict(harvest)), 201


# ------------------------------------------------------- expenses/income --
@app.get("/api/farms/<int:farm_id>/records")
@auth_required
def list_records(farm_id):
    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if not farm:
        db.close()
        return jsonify(error="Farm not found or access denied"), 404
    rows = db.execute(
        "SELECT * FROM farm_records WHERE farm_id = ? ORDER BY record_date DESC", (farm_id,)
    ).fetchall()
    db.close()
    records = rows_to_list(rows)
    income = sum(r["amount"] for r in records if r["type"] == "income")
    expense = sum(r["amount"] for r in records if r["type"] == "expense")
    return jsonify(records=records, summary={"income": income, "expense": expense, "net": income - expense})


@app.post("/api/farms/<int:farm_id>/records")
@auth_required
def add_record(farm_id):
    data = request.get_json(silent=True) or {}
    rtype, category, amount, record_date = (
        data.get("type"), data.get("category"), data.get("amount"), data.get("record_date")
    )
    if rtype not in ("expense", "income") or not category or amount is None or not record_date:
        return jsonify(error="type ('expense'|'income'), category, amount and record_date are required"), 400

    db = get_db()
    farm = owns_farm_or_staff(db, farm_id, g.user)
    if not farm:
        db.close()
        return jsonify(error="Farm not found or access denied"), 404

    cur = db.execute(
        "INSERT INTO farm_records (farm_id, type, category, amount, record_date, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (farm_id, rtype, category, amount, record_date, data.get("notes")),
    )
    db.commit()
    record = db.execute("SELECT * FROM farm_records WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(record=row_to_dict(record)), 201


@app.get("/api/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
