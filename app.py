# app.py
import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("JWT_SECRET", "pharmalink-demo-key")
DB_FILE = os.getenv("DB_FILE", "sqlite:///pharmalink.db")

app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

# --- DB setup ---
engine = create_engine(DB_FILE, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(50), default="doctor")  # doctor or pharmacist
    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role}


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    address = Column(String(300), nullable=True)
    phone = Column(String(50), nullable=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "address": self.address, "phone": self.phone}


class Transfer(Base):
    __tablename__ = "transfers"
    id = Column(Integer, primary_key=True)
    patient_name = Column(String(200), nullable=False)
    medication = Column(String(300), nullable=False)
    from_pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"))
    to_pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"))
    status = Column(String(50), default="pending")  # pending / approved / completed
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())

    from_pharmacy = relationship("Pharmacy", foreign_keys=[from_pharmacy_id])
    to_pharmacy = relationship("Pharmacy", foreign_keys=[to_pharmacy_id])
    created_by = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "patient_name": self.patient_name,
            "medication": self.medication,
            "from_pharmacy": self.from_pharmacy.to_dict() if self.from_pharmacy else None,
            "to_pharmacy": self.to_pharmacy.to_dict() if self.to_pharmacy else None,
            "status": self.status,
            "created_by": self.created_by.to_dict() if self.created_by else None,
            "created_at": self.created_at.isoformat(),
        }


Base.metadata.create_all(engine)


# --- helpers ---
def create_token(user):
    payload = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(days=1),
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    # jwt.encode returns a str in PyJWT >=2.x
    return token


def get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"])
    except Exception:
        return None
    user_id = data.get("user_id")
    if not user_id:
        return None
    session = SessionLocal()
    try:
        user = session.get(User, user_id)
        return user
    finally:
        session.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(user, *args, **kwargs)
    return wrapper


# --- API routes ---
@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name")
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    role = data.get("role", "doctor")
    if not (name and email and password):
        return jsonify({"error": "Missing fields"}), 400

    session = SessionLocal()
    try:
        if session.query(User).filter_by(email=email).first():
            return jsonify({"error": "Email already registered"}), 400
        u = User(name=name, email=email, password_hash=generate_password_hash(password), role=role)
        session.add(u)
        session.commit()
        token = create_token(u)
        return jsonify({"token": token, "user": u.to_dict()})
    finally:
        session.close()


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email", "").lower().strip()
    password = data.get("password", "")
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401
        token = create_token(user)
        return jsonify({"token": token, "user": user.to_dict()})
    finally:
        session.close()


@app.route("/api/me", methods=["GET"])
@login_required
def me(user):
    return jsonify({"user": user.to_dict()})


@app.route("/api/pharmacies", methods=["GET", "POST"])
@login_required
def pharmacies(user):
    session = SessionLocal()
    try:
        if request.method == "POST":
            data = request.json or {}
            name = data.get("name")
            if not name:
                return jsonify({"error": "name is required"}), 400
            p = Pharmacy(name=name, address=data.get("address"), phone=data.get("phone"))
            session.add(p)
            session.commit()
            return jsonify({"pharmacy": p.to_dict()})
        else:
            items = session.query(Pharmacy).order_by(Pharmacy.name).all()
            return jsonify({"pharmacies": [p.to_dict() for p in items]})
    finally:
        session.close()


@app.route("/api/transfers", methods=["GET", "POST"])
@login_required
def transfers(user):
    session = SessionLocal()
    try:
        if request.method == "POST":
            data = request.json or {}
            patient_name = data.get("patient_name")
            medication = data.get("medication")
            from_pharmacy_id = data.get("from_pharmacy_id")
            to_pharmacy_id = data.get("to_pharmacy_id")
            if not (patient_name and medication and from_pharmacy_id and to_pharmacy_id):
                return jsonify({"error": "missing fields"}), 400
            t = Transfer(
                patient_name=patient_name,
                medication=medication,
                from_pharmacy_id=from_pharmacy_id,
                to_pharmacy_id=to_pharmacy_id,
                status="pending",
                created_by_id=user.id,
            )
            session.add(t)
            session.commit()
            session.refresh(t)
            return jsonify({"transfer": t.to_dict()})
        else:
            items = session.query(Transfer).order_by(Transfer.created_at.desc()).all()
            return jsonify({"transfers": [t.to_dict() for t in items]})
    finally:
        session.close()


@app.route("/api/transfers/<int:transfer_id>/status", methods=["PUT"])
@login_required
def update_transfer_status(user, transfer_id):
    data = request.json or {}
    new_status = data.get("status")
    if new_status not in ("pending", "approved", "completed"):
        return jsonify({"error": "invalid status"}), 400
    session = SessionLocal()
    try:
        t = session.get(Transfer, transfer_id)
        if not t:
            return jsonify({"error": "not found"}), 404
        # For demo: allow any authenticated user to change status; to restrict, check user.role
        t.status = new_status
        session.commit()
        return jsonify({"transfer": t.to_dict()})
    finally:
        session.close()


# Serve frontend
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# --- Seed some demo data on first run ---
def seed():
    session = SessionLocal()
    try:
        if session.query(User).count() == 0:
            demo_doc = User(name="Demo Doctor", email="doctor@demo.com", password_hash=generate_password_hash("password"), role="doctor")
            demo_pharm = User(name="Demo Pharmacist", email="pharm@demo.com", password_hash=generate_password_hash("password"), role="pharmacist")
            session.add_all([demo_doc, demo_pharm])
            session.commit()
        if session.query(Pharmacy).count() == 0:
            p1 = Pharmacy(name="Central Pharmacy", address="123 Main St")
            p2 = Pharmacy(name="Eastside Pharmacy", address="45 East Ave")
            session.add_all([p1, p2])
            session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    seed()
    print("Starting PharmaLink demo on http://localhost:5100")
    app.run(host="0.0.0.0", port=5100, debug=True)
