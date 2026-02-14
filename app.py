from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import sqlite3
import calendar
from datetime import date, datetime, timedelta, timezone
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os

app = Flask(__name__)
# SECRET KEY
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

# Remember me
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_SECURE"] = not app.debug

# Session cookies
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = not app.debug

# Protection
app.config["SESSION_PROTECTION"] = "strong"

# Durée session normale
app.permanent_session_lifetime = timedelta(days=7)

# chemin absolu vers ton vrai dossier static
static_folder = os.path.join(os.path.dirname(__file__), 'static')

# ============================
#   FILTRE JINJA - Format Date
# ============================
@app.template_filter('datetime_format')
def datetime_format(value):
    """Convertit une date ISO (YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS) 
    en JJ-MM-YYYY pour l'affichage."""
    if not value:
        return ""
    try:
        # Cas avec heure
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d-%m-%Y %H:%M:%S")
    except ValueError:
        try:
            # Cas sans heure
            dt = datetime.strptime(value, "%Y-%m-%d")
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            return value

# --- Flask-Login config ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # si accès non autorisé → /login

# --- Connexion sqlite3 brut ---
def get_db_connection():
    conn = sqlite3.connect("instance/local.sqlite")
    conn.row_factory = sqlite3.Row
    return conn

# --- Connexion SQLite pour authentification (users) ---
def get_auth_connection():
    conn = sqlite3.connect("instance/auth.sqlite")
    conn.row_factory = sqlite3.Row
    return conn

# --- Connexion planning DB ---
def get_app_connection():
    conn = sqlite3.connect("instance/app.sqlite")
    conn.row_factory = sqlite3.Row
    return conn

# --- User class (Flask-Login) ---
class User(UserMixin):
    def __init__(self, id, username, password_hash, role, client_id):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.client_id = client_id

def get_user_by_id(user_id):
    conn = get_auth_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row["id"], row["username"], row["password_hash"], row["role"], row["client_id"])
    return None

def get_user_by_username(username):
    conn = get_auth_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row:
        return User(row["id"], row["username"], row["password_hash"], row["role"], row["client_id"])
    return None

def _period_bounds(periode: str, date_exact: str|None, start: str|None, end: str|None):
    """Retourne (start_iso, end_iso) selon la période choisie.
       - 'exact' => une seule date
       - 'custom' => plage
       - autres => bornes calculées
       Renvoie (None, None) si 'all'."""
    today = datetime.now(timezone.utc).date()

    if periode == "all":
        return None, None

    if periode == "exact" and date_exact:
        # début = fin = cette date
        return date_exact, date_exact

    if periode == "custom":
        if start and end:
            return start, end
        if start and not end:
            return start, start
        if end and not start:
            return end, end
        return None, None

    if periode == "today":
        d = today.isoformat()
        return d, d

    if periode == "yesterday":
        d = (today - timedelta(days=1)).isoformat()
        return d, d

    if periode == "week":
        # semaine en cours (lundi→dimanche)
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat()

    if periode == "month":
        first = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        last = today.replace(day=last_day)
        return first.isoformat(), last.isoformat()

    if periode == "year":
        first = date(today.year, 1, 1)
        last = date(today.year, 12, 31)
        return first.isoformat(), last.isoformat()

    return None, None


def _period_bounds_impression(periode: str, date_start: str|None, date_end: str|None):
    """Retourne (start_iso, end_iso) selon la période choisie pour la page Impression."""
    today = datetime.now(timezone.utc).date()

    if periode == "all":
        return None, None

    if periode == "custom":
        # plage personnalisée saisie par l'utilisateur
        if date_start and date_end:
            return date_start, date_end
        elif date_start:
            return date_start, date_start
        elif date_end:
            return date_end, date_end
        else:
            return None, None

    if periode == "today":
        d = today.isoformat()
        return d, d

    if periode == "yesterday":
        d = (today - timedelta(days=1)).isoformat()
        return d, d

    if periode == "week":
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat()

    if periode == "month":
        first = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        last = today.replace(day=last_day)
        return first.isoformat(), last.isoformat()

    if periode == "year":
        first = date(today.year, 1, 1)
        last = date(today.year, 12, 31)
        return first.isoformat(), last.isoformat()

    return None, None

def init_app_db():
    conn = get_app_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planning_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_by TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planning_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            num_reservation INTEGER NOT NULL,
            position INTEGER NOT NULL,
            status_snapshot TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(version_id, num_reservation),
            FOREIGN KEY(version_id) REFERENCES planning_version(id)
        )
    """)

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_planning_items_version_pos "
        "ON planning_items(version_id, position)"
    )

    conn.commit()
    conn.close()

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# ============================
#   ROUTES AUTHENTIFICATION
# ============================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == "planning":
            return redirect(url_for("planning_view"))
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        user = get_user_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            # 👇 redirection selon rôle
            if user.role == "planning":
                return redirect(url_for("planning_view"))
            flash("Connexion réussie ✅", "success")
            return redirect(url_for("index"))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect ❌", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous être déconnecté maintenant ✅", "info")
    return redirect(url_for("login"))

@app.route("/whoami")
@login_required
def whoami():
    return f"Utilisateur connecté : {current_user.username} | rôle = {current_user.role} | client_id = {current_user.client_id}"

# ============================
#   CONTEXT PROCESSOR
# ============================

@app.context_processor
def inject_now():
    from datetime import datetime
    return {'current_year': datetime.now().year}
@app.context_processor
def inject_client_name():
    client_name = None
    if current_user.is_authenticated and current_user.role == "client":
        conn = get_db_connection()
        row = conn.execute(
            "SELECT Entreprise FROM client WHERE N = ?", (current_user.client_id,)
        ).fetchone()
        conn.close()
        if row:
            client_name = row["Entreprise"]
    return dict(client_name=client_name)

# ============================
#   ROUTES PRINCIPALES
# ============================

@app.route('/manifest.json')
def manifest():
    return send_from_directory(static_folder, 'manifest.json', mimetype='application/json')

@app.route('/service-worker.js')
def sw():
    return send_from_directory(static_folder, 'service-worker.js', mimetype='application/javascript')

@app.route("/")
def home():
    if current_user.is_authenticated:
        
        if current_user.role == "planning":
            return redirect(url_for("planning_view"))

        return redirect(url_for("index"))

    return redirect(url_for("login"))

# ---- Dashboard ----
@app.route("/index")
@login_required
def index():
    if current_user.role == "planning":
        return redirect(url_for("planning_view"))
    
    conn = get_db_connection()
    # Vue admin → totaux globaux
    if current_user.role == "admin":
        total_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        orders_livree = conn.execute("SELECT COUNT(*) FROM orders WHERE situation = 'LIVREE'").fetchone()[0]
        orders_encours = conn.execute("SELECT COUNT(*) FROM orders WHERE situation = 'EN COURS'").fetchone()[0]
        orders_livraison = conn.execute("SELECT COUNT(*) FROM orders WHERE situation = 'LIVRAISON'").fetchone()[0]
        total_delivery = conn.execute("SELECT COUNT(*) FROM delivery").fetchone()[0]
        # Comptage impressions
        total_impressions = conn.execute(
            "SELECT COUNT(*) FROM impressions_simplifiees"
        ).fetchone()[0]
    else:
        # Vue client → totaux spécifiques à son entreprise
        client = conn.execute("SELECT Entreprise FROM client WHERE N = ?", (current_user.client_id,)).fetchone()
        if client:
            client_name = client["Entreprise"]

            total_clients = 1
            total_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE client = ?", (client_name,)).fetchone()[0]
            orders_livree = conn.execute("SELECT COUNT(*) FROM orders WHERE client = ? AND situation = 'LIVREE'", (client_name,)).fetchone()[0]
            orders_encours = conn.execute("SELECT COUNT(*) FROM orders WHERE client = ? AND situation = 'EN COURS'", (client_name,)).fetchone()[0]
            orders_livraison = conn.execute("SELECT COUNT(*) FROM orders WHERE client = ? AND situation = 'LIVRAISON'", (client_name,)).fetchone()[0]
            total_delivery = conn.execute("SELECT COUNT(*) FROM delivery WHERE client = ?", (client_name,)).fetchone()[0]
            total_impressions = 0
        else:
            total_clients = 0
            total_orders = 0
            orders_livree = 0
            orders_encours = 0
            orders_livraison = 0
            total_delivery = 0
            total_impressions = 0

    conn.close()

    return render_template(
        "index.html",
        total_clients=total_clients,
        total_orders=total_orders,
        total_delivery=total_delivery,
        orders_livree=orders_livree,
        orders_encours=orders_encours,
        orders_livraison=orders_livraison,
        total_impressions=total_impressions
    )

# ---- Clients (pagination) ----
@app.route("/clients")
@login_required
def clients():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 20

    clients_list = conn.execute(
        """
        SELECT N AS id, Entreprise AS company_name, Contact AS contact_name, 
               Tel AS phone, Email AS email
        FROM client
        ORDER BY N ASC
        LIMIT ? OFFSET ?
        """,
        (per_page, (page - 1) * per_page),
    ).fetchall()

    total_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
    total_pages = (total_clients + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_clients > 0 else 0
    end = min(page * per_page, total_clients)

    conn.close()

    return render_template(
        "clients.html",
        clients=clients_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_clients=total_clients
    )

# ---- Orders (pagination + filtres) ----
@app.route("/orders")
@login_required
def orders():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 20
    period = request.args.get("period", "all")
    status = request.args.get("status", "all")
    client = request.args.get("client", "").strip()
    product = request.args.get("product", "").strip()
    cmdcl = request.args.get("cmdcl", "").strip()

    query = """
        SELECT 
            num_reservation, cmdl, client, produit, qte,
            date_reservation, situation, reste, total_livre
        FROM orders
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM orders WHERE 1=1"
    params, count_params = [], []

    today = datetime.now(timezone.utc).date()

    # Restriction si client connecté
    if current_user.role == "client":
        client_name = conn.execute(
            "SELECT Entreprise FROM client WHERE N = ?", (current_user.client_id,)
        ).fetchone()["Entreprise"]
        query += " AND client = ?"
        count_query += " AND client = ?"
        params.append(client_name)
        count_params.append(client_name)

    # Filtres...
    if period == "today":
        query += " AND date(date_reservation) = ?"
        count_query += " AND date(date_reservation) = ?"
        params.append(today)
        count_params.append(today)
    elif period == "yesterday":
        y = today - timedelta(days=1)
        query += " AND date(date_reservation) = ?"
        count_query += " AND date(date_reservation) = ?"
        params.append(y)
        count_params.append(y)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        query += " AND date(date_reservation) >= ?"
        count_query += " AND date(date_reservation) >= ?"
        params.append(start)
        count_params.append(start)
    elif period == "month":
        start = today.replace(day=1)
        query += " AND date(date_reservation) >= ?"
        count_query += " AND date(date_reservation) >= ?"
        params.append(start)
        count_params.append(start)
    elif period == "year":
        start = today.replace(month=1, day=1)
        query += " AND date(date_reservation) >= ?"
        count_query += " AND date(date_reservation) >= ?"
        params.append(start)
        count_params.append(start)

    if status != "all":
        query += " AND situation = ?"
        count_query += " AND situation = ?"
        params.append(status)
        count_params.append(status)

    if cmdcl:
        raw = cmdcl.strip()
    
        # --- Recherche EXACTE entre guillemets " ... "
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            exact_value = raw[1:-1].strip()  # enlever guillemets
            query += " AND TRIM(cmdl) = TRIM(?) COLLATE NOCASE"
            count_query += " AND TRIM(cmdl) = TRIM(?) COLLATE NOCASE"
            params.append(exact_value)
            count_params.append(exact_value)
    
        # --- Recherche EXACTE format [ ... ] (optionnel mais pratique)
        elif raw.startswith("[") and raw.endswith("]"):
            exact_value = raw[1:-1].strip()
            query += " AND TRIM(cmdl) = TRIM(?) COLLATE NOCASE"
            count_query += " AND TRIM(cmdl) = TRIM(?) COLLATE NOCASE"
            params.append(exact_value)
            count_params.append(exact_value)
    
        # --- Recherche floue (LIKE)
        else:
            tokens = [t for t in raw.split() if t]
            pattern = "%" + "%".join(tokens) + "%"
            query += " AND cmdl LIKE ? COLLATE NOCASE"
            count_query += " AND cmdl LIKE ? COLLATE NOCASE"
            params.append(pattern)
            count_params.append(pattern)

    if client and current_user.role == "admin":
        tokens = [t for t in client.split() if t]
        pattern = "%" + "%".join(tokens) + "%"
        query += " AND client LIKE ? COLLATE NOCASE"
        count_query += " AND client LIKE ? COLLATE NOCASE"
        params.append(pattern)
        count_params.append(pattern)

    if product:
        tokens = [t for t in product.split() if t]
        pattern = "%" + "%".join(tokens) + "%"
        query += " AND produit LIKE ? COLLATE NOCASE"
        count_query += " AND produit LIKE ? COLLATE NOCASE"
        params.append(pattern)
        count_params.append(pattern)

    query += " ORDER BY date_reservation DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    orders_list = conn.execute(query, params).fetchall()
    total_orders = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = (total_orders + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_orders > 0 else 0
    end = min(page * per_page, total_orders)

    conn.close()
    return render_template(
        "orders.html",
        orders=orders_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_orders=total_orders,
        period=period,
        status=status,
        client=client,
        product=product,
        cmdcl=cmdcl
    )

# ---- Orders by client ----
@app.route("/clients/<int:client_id>/orders")
@login_required
def client_orders(client_id):
    conn = get_db_connection()

    client = conn.execute(
        "SELECT N AS id, Entreprise AS company_name FROM client WHERE N = ?",
        (client_id,)
    ).fetchone()
    if not client:
        conn.close()
        return "Client not found", 404

    if current_user.role == "client" and current_user.client_id != client_id:
        conn.close()
        flash("Accès refusé ❌", "danger")
        return redirect(url_for("orders"))

    page = request.args.get("page", 1, type=int)
    per_page = 20

    orders_list = conn.execute(
        """
        SELECT 
            num_reservation, cmdl, client, produit, qte,
            date_reservation, situation, reste, total_livre
        FROM orders
        WHERE client = ?
        ORDER BY date_reservation DESC
        LIMIT ? OFFSET ?
        """,
        (client["company_name"], per_page, (page - 1) * per_page),
    ).fetchall()

    total_orders = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE client = ?",
        (client["company_name"],)
    ).fetchone()[0]
    total_pages = (total_orders + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_orders > 0 else 0
    end = min(page * per_page, total_orders)

    conn.close()
    return render_template(
        "client_orders.html",
        client=client,
        orders=orders_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_orders=total_orders
    )

# ---- Delivery (pagination + filtres) ----
@app.route("/delivery")
@login_required
def delivery():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 20
    period = request.args.get("period", "all")
    client = request.args.get("client", "").strip()
    product = request.args.get("product", "").strip()

    query = """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM delivery WHERE 1=1"
    params, count_params = [], []

    today = datetime.now(timezone.utc).date()

    if current_user.role == "client":
        query += " AND code_client = ?"
        count_query += " AND code_client = ?"
        params.append(current_user.client_id)
        count_params.append(current_user.client_id)

    if period == "today":
        query += " AND date(date_livraison) = ?"
        count_query += " AND date(date_livraison) = ?"
        params.append(today)
        count_params.append(today)
    elif period == "yesterday":
        y = today - timedelta(days=1)
        query += " AND date(date_livraison) = ?"
        count_query += " AND date(date_livraison) = ?"
        params.append(y)
        count_params.append(y)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        query += " AND date(date_livraison) >= ?"
        count_query += " AND date(date_livraison) >= ?"
        params.append(start)
        count_params.append(start)
    elif period == "month":
        start = today.replace(day=1)
        query += " AND date(date_livraison) >= ?"
        count_query += " AND date(date_livraison) >= ?"
        params.append(start)
        count_params.append(start)
    elif period == "year":
        start = today.replace(month=1, day=1)
        query += " AND date(date_livraison) >= ?"
        count_query += " AND date(date_livraison) >= ?"
        params.append(start)
        count_params.append(start)

    if client and current_user.role == "admin":
        tokens = [t for t in client.split() if t]
        pattern = "%" + "%".join(tokens) + "%"
        query += " AND client LIKE ? COLLATE NOCASE"
        count_query += " AND client LIKE ? COLLATE NOCASE"
        params.append(pattern)
        count_params.append(pattern)

    if product:
        tokens = [t for t in product.split() if t]
        pattern = "%" + "%".join(tokens) + "%"
        query += " AND produit LIKE ? COLLATE NOCASE"
        count_query += " AND produit LIKE ? COLLATE NOCASE"
        params.append(pattern)
        count_params.append(pattern)

    query += " ORDER BY date_livraison DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    delivery_list = conn.execute(query, params).fetchall()
    total_delivery = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = (total_delivery + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_delivery > 0 else 0
    end = min(page * per_page, total_delivery)

    conn.close()

    return render_template(
        "delivery.html",
        delivery=delivery_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_delivery=total_delivery,
        period=period,
        client=client,
        product=product
    )

# ---- Delivery by client ----
@app.route("/clients/<int:client_id>/delivery")
@login_required
def client_delivery(client_id):
    conn = get_db_connection()

    client = conn.execute(
        "SELECT N AS id, Entreprise AS company_name FROM client WHERE N = ?",
        (client_id,)
    ).fetchone()
    if not client:
        conn.close()
        return "Client not found", 404

    if current_user.role == "client" and current_user.client_id != client_id:
        conn.close()
        flash("Accès refusé ❌", "danger")
        return redirect(url_for("delivery"))

    page = request.args.get("page", 1, type=int)
    per_page = 20

    delivery_list = conn.execute(
        """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE code_client = ?
        ORDER BY date_livraison DESC
        LIMIT ? OFFSET ?
        """,
        (client_id, per_page, (page - 1) * per_page),
    ).fetchall()

    total_delivery = conn.execute(
        "SELECT COUNT(*) FROM delivery WHERE code_client = ?",
        (client_id,)
    ).fetchone()[0]
    total_pages = (total_delivery + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_delivery > 0 else 0
    end = min(page * per_page, total_delivery)

    conn.close()
    return render_template(
        "client_delivery.html",
        client=client,
        delivery=delivery_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_delivery=total_delivery
    )

# ---- Delivery by order ----
@app.route("/orders/<int:order_id>/delivery")
@login_required
def order_delivery(order_id):
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 20
    from_client = request.args.get("from_client")

    delivery_list = conn.execute(
        """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE num_reservation = ?
        ORDER BY date_livraison DESC
        LIMIT ? OFFSET ?
        """,
        (order_id, per_page, (page - 1) * per_page),
    ).fetchall()

    total_delivery = conn.execute(
        "SELECT COUNT(*) FROM delivery WHERE num_reservation = ?",
        (order_id,)
    ).fetchone()[0]
    total_pages = (total_delivery + per_page - 1) // per_page

    start = (page - 1) * per_page + 1 if total_delivery > 0 else 0
    end = min(page * per_page, total_delivery)

    conn.close()

    if current_user.role == "client":
        check = get_db_connection().execute(
            "SELECT client FROM orders WHERE num_reservation = ?", (order_id,)
        ).fetchone()
        if not check:
            flash("Commande introuvable ❌", "danger")
            return redirect(url_for("orders"))
        client_name = get_db_connection().execute(
            "SELECT Entreprise FROM client WHERE N = ?", (current_user.client_id,)
        ).fetchone()["Entreprise"]
        if check["client"] != client_name:
            flash("Accès refusé ❌", "danger")
            return redirect(url_for("orders"))

    return render_template(
        "order_delivery.html",
        order_id=order_id,
        delivery=delivery_list,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_delivery=total_delivery,
        from_client=from_client
    )

# ---- Créer un compte utilisateur pour un client ----
@app.route("/admin/create_user", methods=["GET", "POST"])
@login_required
def create_user():
    if current_user.role != "admin":
        flash("Accès refusé : réservé aux administrateurs ❌", "danger")
        return redirect(url_for("index"))

    # --- Liste des clients depuis local.sqlite ---
    conn_local = get_db_connection()
    clients = conn_local.execute("SELECT N AS id, Entreprise AS company_name FROM client ORDER BY Entreprise ASC").fetchall()
    conn_local.close()

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        client_id = request.form.get("client_id")

        # Si aucun client n’est sélectionné
        client_id = int(client_id) if client_id and client_id.isdigit() else None

        # --- Vérifier unicité du username ---
        conn_auth = get_auth_connection()
        try:
            exists = conn_auth.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                flash("❌ Ce nom d'utilisateur existe déjà", "danger")
                return redirect(url_for("create_user"))

            password_hash = generate_password_hash(password)
            conn_auth.execute(
                "INSERT INTO users (username, password_hash, role, client_id) VALUES (?, ?, ?, ?)",
                (username, password_hash, "client", client_id)
            )
            conn_auth.commit()
            flash(f"✅ Compte '{username}' créé avec succès", "success")

        except Exception as e:
            flash(f"Erreur lors de la création du compte : {e}", "danger")
        finally:
            conn_auth.close()

        # Redirection vers la page des utilisateurs, pas celle des clients
        return redirect(url_for("list_users"))

    # --- Si méthode GET ---
    return render_template("create_user.html", clients=clients)


# ---- Liste et suppression des utilisateurs ----
@app.route("/admin/users")
@login_required
def list_users():
    if current_user.role != "admin":
        flash("Accès refusé ❌", "danger")
        return redirect(url_for("index"))

    # 1️⃣ Connexion à auth.sqlite → pour les utilisateurs
    conn_auth = get_auth_connection()
    users = conn_auth.execute("SELECT id, username, role, client_id, is_active, created_at FROM users").fetchall()
    conn_auth.close()

    # 2️⃣ Connexion à local.sqlite → pour les clients
    conn_local = get_db_connection()
    clients = conn_local.execute("SELECT N, Entreprise FROM client").fetchall()
    conn_local.close()

    # 3️⃣ Créer un mapping {id_client: nom_entreprise}
    clients_map = {c["N"]: c["Entreprise"] for c in clients}

    # 4️⃣ Fusionner proprement côté Python
    enriched_users = []
    for u in users:
        enriched_users.append({
            "id": u["id"],
            "username": u["username"],
            "role": u["role"],
            "client_name": clients_map.get(u["client_id"], "(aucun)"),
            "is_active": u["is_active"],
            "created_at": u["created_at"]
        })

    return render_template("list_users.html", users=enriched_users)

@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.role != "admin":
        flash("Accès refusé ❌", "danger")
        return redirect(url_for("index"))

    conn_auth  = get_auth_connection()
    conn_auth.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn_auth.commit()
    conn_auth.close()

    flash("✅ Utilisateur supprimé avec succès", "success")
    return redirect(url_for("list_users"))


# ---- Afficher la table des impressions ----
@app.route("/impression", methods=["GET"])
@login_required
def impression():
    # Lecture des filtres transmis par l'URL
    periode     = (request.args.get("periode") or "all").strip()
    date_start  = request.args.get("date_start")
    date_end    = request.args.get("date_end")
    user_filter = (request.args.get("user_filter") or "all").strip()
    article_filter = (request.args.get("article_filter") or "all").strip()

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 20

    # Détermination de la plage de dates (via helper)
    start_iso, end_iso = _period_bounds_impression(periode, date_start, date_end)

    # Connexion SQLite
    conn = get_db_connection()
    cur = conn.cursor()

    # Liste distincte des utilisateurs
    cur.execute("""
        SELECT DISTINCT utilisateur 
        FROM impressions_simplifiees 
        WHERE utilisateur IS NOT NULL 
        ORDER BY utilisateur
    """)
    users = [r["utilisateur"] for r in cur.fetchall()]

    # Liste articles des utilisateurs
    cur.execute("""
    SELECT DISTINCT article
    FROM impressions_simplifiees
    WHERE article IS NOT NULL
    ORDER BY article
    """)
    articles = [r["article"] for r in cur.fetchall()]

    # Requête principale
    query = """
        SELECT tirage, date_impression, commande, machine, article, longueur, etiquettes, chutes_ml, utilisateur
        FROM impressions_simplifiees
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM impressions_simplifiees WHERE 1=1"
    params, count_params = [], []

    # Filtre période
    if start_iso and end_iso:
        query += " AND date(date_impression) BETWEEN date(?) AND date(?)"
        count_query += " AND date(date_impression) BETWEEN date(?) AND date(?)"
        params.extend([start_iso, end_iso])
        count_params.extend([start_iso, end_iso])

    # Filtre utilisateur
    if user_filter != "all":
        query += " AND utilisateur = ?"
        count_query += " AND utilisateur = ?"
        params.append(user_filter)
        count_params.append(user_filter)

    # Filtre article
    if article_filter != "all":
        query += " AND article = ?"
        count_query += " AND article = ?"
        params.append(article_filter)
        count_params.append(article_filter)

    # Tri + pagination
    query += " ORDER BY date_impression DESC, tirage DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    # Exécution
    rows = cur.execute(query, params).fetchall()
    total_rows = cur.execute(count_query, count_params).fetchone()[0]
    conn.close()

    # Pagination calculée
    total_pages = (total_rows + per_page - 1) // per_page
    start = (page - 1) * per_page + 1 if total_rows > 0 else 0
    end = min(page * per_page, total_rows)

    return render_template(
        "impression.html",
        rows=rows,
        users=users,
        articles=articles,
        periode=periode,
        date_start=date_start or "",
        date_end=date_end or "",
        user_filter=user_filter,
        article_filter=article_filter,
        page=page,
        total_pages=total_pages,
        start=start,
        end=end,
        total_rows=total_rows,
    )

######### Planning ##########

@app.route("/admin/planning/test")
@login_required
def planning_test():
    if current_user.role not in ("admin", "superadmin"):
        return "Forbidden", 403

    conn = get_app_connection()
    v = conn.execute("SELECT COUNT(*) AS c FROM planning_version").fetchone()["c"]
    conn.close()
    return f"✅ app.sqlite OK — planning_version rows = {v}"


@app.route("/admin/planning/create", methods=["POST"])
@login_required
def planning_create():

    if current_user.role not in ("admin","superadmin"):
        return "Forbidden", 403

    conn = get_db_connection()

    rows = conn.execute("""
        SELECT 
            num_reservation,
            cmdl,
            client,
            produit,
            qte,
            reste,
            situation
        FROM orders
        WHERE situation != 'LIVREE'
          AND date_reservation IS NOT NULL
        ORDER BY date_reservation ASC
        LIMIT 10
    """).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "orders":[
            {
                "num": r["num_reservation"],
                "cmdcl": r["cmdl"] or "",
                "client": r["client"] or "",
                "produit": r["produit"] or "",
                "qte": int(r["qte"] or 0),
                "reste": int(r["reste"] or 0),
                "statut": (r["situation"] or "").strip()
            }
            for r in rows
        ]
    })


@app.route("/planning")
@login_required
def planning():

    if current_user.role not in ("admin"):
        return "Forbidden",403
    conn_app = get_app_connection()
    conn_local = get_db_connection()

    try:
        # 1️⃣ récupérer LIVRÉES depuis local.sqlite
        livrees = conn_local.execute("""
            SELECT num_reservation
            FROM orders
            WHERE situation='LIVREE'
        """).fetchall()

        if livrees:
        
            ids = [str(r["num_reservation"]) for r in livrees]
            placeholders = ",".join(["?"] * len(ids))

            # 2️⃣ supprimer dans app.sqlite
            conn_app.execute(f"""
                DELETE FROM planning_items
                WHERE num_reservation IN ({placeholders})
            """, ids)

            conn_app.commit()

        # 1️⃣ Dernière version
        v = conn_app.execute("""
            SELECT id
            FROM planning_version
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if not v:
            return render_template("planning.html", orders=[])

        version_id = v["id"]

        # 2️⃣ Items planning
        items = conn_app.execute("""
            SELECT num_reservation, position
            FROM planning_items
            WHERE version_id = ?
            ORDER BY position ASC
        """, (version_id,)).fetchall()

        if not items:
            return render_template("planning.html", orders=[])

        nums = [it["num_reservation"] for it in items]

        # sécurité SQL
        placeholders = ",".join(["?"] * len(nums))

        # 3️⃣ Récupérer commandes
        orders_data = conn_local.execute(f"""
            SELECT 
                num_reservation,
                cmdl,
                client,
                produit,
                qte,
                reste,
                situation
            FROM orders
            WHERE num_reservation IN ({placeholders})
        """, nums).fetchall()

        # mapping
        orders_map = {
            r["num_reservation"]: r
            for r in orders_data
        }

        orders = []

        for it in items:
            o = orders_map.get(it["num_reservation"])

            if not o:
                continue

            orders.append({
                "num": it["num_reservation"],
                "cmdcl": o["cmdl"] or "",
                "client": o["client"] or "",
                "produit": o["produit"] or "",
                "qte": int(o["qte"] or 0),
                "reste": int(o["reste"] or 0),
                "statut": (o["situation"] or "").strip(),
                "pos": it["position"]
            })

        return render_template("planning.html", orders=orders)

    finally:
        conn_app.close()
        conn_local.close()

@app.route("/api/planning/save", methods=["POST"])
@login_required
def planning_save():

    if current_user.role not in ("admin","superadmin"):
        return "Forbidden", 403

    data = request.get_json()
    order = data.get("order", [])

    conn = get_app_connection()
    now = datetime.utcnow().isoformat()

    # 🔥 1️⃣ créer nouvelle version
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO planning_version (created_at, created_by)
        VALUES (?,?)
    """,(now,current_user.username))

    version_id = cur.lastrowid

    # 🔥 2️⃣ insérer items
    pos = 1

    for num in order:
        conn.execute("""
            INSERT INTO planning_items
            (version_id,num_reservation,position,updated_at)
            VALUES (?,?,?,?)
        """,(version_id,num,pos,now))

        pos += 1

    conn.commit()
    conn.close()

    return jsonify({"success":True})



@app.route("/api/planning/version")
@login_required
def planning_version_api():

    conn = get_app_connection()

    v = conn.execute("""
        SELECT MAX(id) as version
        FROM planning_version
    """).fetchone()

    conn.close()

    return jsonify({
        "version": v["version"] if v and v["version"] else 0
    })

@app.route("/admin/planning/new", methods=["POST"])
@login_required
def planning_new():

    if current_user.role not in ("admin","superadmin"):
        return "Forbidden", 403

    # ❌ plus d'insert DB ici
    # juste signaler au front de reset l'UI

    return jsonify({"success":True})



@app.route("/planning/add", methods=["POST"])
@login_required
def planning_add():

    if current_user.role not in ("admin","superadmin"):
        return "Forbidden", 403

    data = request.get_json()
    num = data.get("num")

    if not num:
        return jsonify({"error":"missing num"}),400

    conn = get_app_connection()

    # dernière version
    v = conn.execute("""
        SELECT id
        FROM planning_version
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if not v:
        return jsonify({"error":"no version"}),400

    version_id = v["id"]

    # position suivante
    p = conn.execute("""
        SELECT COALESCE(MAX(position),0)+1 AS pos
        FROM planning_items
        WHERE version_id = ?
    """,(version_id,)).fetchone()["pos"]

    count = conn.execute("""
        SELECT COUNT(*) as c
        FROM planning_items
        WHERE version_id = ?
    """,(version_id,)).fetchone()["c"]

    if count >= 10:
        conn.close()
        return jsonify({"error":"max reached"}),400
    
    exists = conn.execute("""
    SELECT 1 FROM planning_items
    WHERE version_id=? AND num_reservation=?
    """,(version_id,num)).fetchone()

    if exists:
        conn.close()
        return jsonify({"error":"already exists"}),400

    conn.execute("""
        INSERT INTO planning_items
        (version_id,num_reservation,position,updated_at)
        VALUES (?,?,?,?)
    """,(version_id,num,p,datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    return jsonify({"success":True})

@app.route("/api/planning/search")
@login_required
def planning_search():

    if current_user.role not in ("admin"):
        return "Forbidden",403

    term = request.args.get("term","").strip()
    page = int(request.args.get("page",1))
    exclude = request.args.getlist("exclude[]")

    limit = 20
    offset = (page-1)*limit

    conn = get_db_connection()

    base_query = """
        FROM orders
        WHERE situation != 'LIVREE'
          AND date_reservation IS NOT NULL
    """

    params = []

    if term:
        base_query += """
            AND (
                cmdl LIKE ?
                OR client LIKE ?
                OR num_reservation LIKE ?
            )
        """
        like = f"%{term}%"
        params += [like,like,like]

    if exclude:
        placeholders = ",".join(["?"]*len(exclude))
        base_query += f" AND num_reservation NOT IN ({placeholders})"
        params += exclude

    rows = conn.execute(f"""
        SELECT 
            num_reservation,
            cmdl,
            client,
            produit,
            qte,
            reste,
            situation
        {base_query}
        ORDER BY date_reservation ASC
        LIMIT ? OFFSET ?
    """, params + [limit,offset]).fetchall()

    total = conn.execute(f"""
        SELECT COUNT(*) as c
        {base_query}
    """, params).fetchone()["c"]

    conn.close()

    return jsonify({
        "results":[
            {
                "id": str(r["num_reservation"]),
                "cmdcl": r["cmdl"] or "",
                "client": r["client"] or "",
                "produit": r["produit"] or "",
                "qte": int(r["qte"] or 0),
                "reste": int(r["reste"] or 0),
                "statut": r["situation"],
                "text": r["cmdl"] or "",
            }
            for r in rows
        ],
        "pagination":{
            "more": (page*limit) < total
        }
    })


@app.route("/planning/view")
@login_required
def planning_view():

    # autoriser admin ou planning
    if current_user.role not in ("admin","superadmin","planning"):
        return "Forbidden",403

    conn_app = get_app_connection()
    conn_local = get_db_connection()

    try:
        # 1️⃣ récupérer LIVRÉES depuis local.sqlite
        livrees = conn_local.execute("""
            SELECT num_reservation
            FROM orders
            WHERE situation='LIVREE'
        """).fetchall()

        if livrees:
        
            ids = [str(r["num_reservation"]) for r in livrees]
            placeholders = ",".join(["?"] * len(ids))

            # 2️⃣ supprimer dans app.sqlite
            conn_app.execute(f"""
                DELETE FROM planning_items
                WHERE num_reservation IN ({placeholders})
            """, ids)

            conn_app.commit()
        
        v = conn_app.execute("""
            SELECT id
            FROM planning_version
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if not v:
            return render_template("planning_view.html", orders=[])

        version_id = v["id"]

        items = conn_app.execute("""
            SELECT num_reservation, position
            FROM planning_items
            WHERE version_id = ?
            ORDER BY position ASC
        """,(version_id,)).fetchall()

        if not items:
            return render_template("planning_view.html", orders=[])

        nums=[it["num_reservation"] for it in items]
        placeholders=",".join(["?"]*len(nums))

        orders_data=conn_local.execute(f"""
            SELECT num_reservation,cmdl,client,produit,qte,reste,situation
            FROM orders
            WHERE num_reservation IN ({placeholders})
        """,nums).fetchall()

        orders_map={r["num_reservation"]:r for r in orders_data}

        orders=[]

        for it in items:
            o=orders_map.get(it["num_reservation"])
            if not o: continue

            orders.append({
                "num":it["num_reservation"],
                "cmdcl":o["cmdl"] or "",
                "client":o["client"] or "",
                "produit":o["produit"] or "",
                "qte":int(o["qte"] or 0),
                "reste":int(o["reste"] or 0),
                "statut":(o["situation"] or "").strip(),
                "pos":it["position"]
            })

        return render_template("planning_view.html",orders=orders)

    finally:
        conn_app.close()
        conn_local.close()


@app.route("/api/planning/data")
@login_required
def planning_data():

    if current_user.role not in ("admin","superadmin","planning"):
        return "Forbidden",403

    conn_app = get_app_connection()
    conn_local = get_db_connection()

    try:
        # nettoyage automatique
        livrees = conn_local.execute("""
            SELECT num_reservation
            FROM orders
            WHERE situation='LIVREE'
        """).fetchall()

        if livrees:
            ids=[str(r["num_reservation"]) for r in livrees]
            placeholders=",".join(["?"]*len(ids))

            conn_app.execute(f"""
                DELETE FROM planning_items
                WHERE num_reservation IN ({placeholders})
            """,ids)

            conn_app.commit()

        v = conn_app.execute("""
            SELECT id
            FROM planning_version
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if not v:
            return jsonify({"orders":[]})

        version_id = v["id"]

        items = conn_app.execute("""
            SELECT num_reservation, position
            FROM planning_items
            WHERE version_id=?
            ORDER BY position
        """,(version_id,)).fetchall()

        nums=[it["num_reservation"] for it in items]

        if not nums:
            return jsonify({"orders":[]})

        placeholders=",".join(["?"]*len(nums))

        orders=conn_local.execute(f"""
            SELECT num_reservation,cmdl,client,produit,qte,reste
            FROM orders
            WHERE num_reservation IN ({placeholders})
              AND situation != 'LIVREE'
        """,nums).fetchall()

        orders_map={o["num_reservation"]:o for o in orders}

        result=[]

        for it in items:
            o=orders_map.get(it["num_reservation"])
            if not o: continue

            result.append({
                "num":it["num_reservation"],
                "cmdcl":o["cmdl"],
                "client":o["client"],
                "produit":o["produit"],
                "qte":o["qte"],
                "reste":o["reste"]
            })

        return jsonify({"orders":result})

    finally:
        conn_app.close()
        conn_local.close()

@app.route("/api/planning/livrees")
@login_required
def planning_livrees():

    conn = get_db_connection()

    rows = conn.execute("""
        SELECT num_reservation
        FROM orders
        WHERE situation='LIVREE'
    """).fetchall()

    conn.close()

    return jsonify({
        "ids":[r["num_reservation"] for r in rows]
    })


init_app_db()
if __name__ == "__main__":
    app.run(debug=True)
