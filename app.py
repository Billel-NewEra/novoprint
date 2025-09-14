from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3

app = Flask(__name__)
app.secret_key = "change_this_to_a_real_secret_key"

# --- Connexion sqlite3 brut ---
def get_db_connection():
    conn = sqlite3.connect("instance/local.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


# ---- Dashboard ----
@app.route("/")
def index():
    conn = get_db_connection()

    total_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_qte = conn.execute("SELECT COALESCE(SUM(somme_qte), 0) FROM orders").fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_clients=total_clients,
        total_orders=total_orders,
        total_qte=total_qte,
    )


# ---- Clients (pagination + ajout) ----
@app.route("/clients", methods=["GET", "POST"])
def clients():
    conn = get_db_connection()

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()

        if not company_name or not contact_name or not email:
            flash("⚠️ Company, contact and email are required.", "danger")
            conn.close()
            return redirect(url_for("clients"))

        existing = conn.execute(
            "SELECT N FROM client WHERE Email = ?", (email,)
        ).fetchone()
        if existing:
            flash("⚠️ This email is already used by another client.", "danger")
            conn.close()
            return redirect(url_for("clients"))

        conn.execute(
            "INSERT INTO client (Entreprise, Contact, Tel, Email) VALUES (?, ?, ?, ?)",
            (company_name, contact_name, phone, email),
        )
        conn.commit()
        flash(f"✅ Client « {company_name} » ajouté.", "success")

    # --- Pagination ---
    page = request.args.get("page", 1, type=int)
    per_page = 10

    clients_list = conn.execute(
        """
        SELECT N AS id, Entreprise AS company_name, Contact AS contact_name, Tel AS phone, Email AS email
        FROM client
        ORDER BY N ASC
        LIMIT ? OFFSET ?
        """,
        (per_page, (page - 1) * per_page),
    ).fetchall()

    total_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
    total_pages = (total_clients + per_page - 1) // per_page

    conn.close()

    return render_template(
        "clients.html",
        clients=clients_list,
        page=page,
        total_pages=total_pages
    )


# ---- Orders (liste avec pagination) ----
@app.route("/orders")
def orders():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 10

    orders_list = conn.execute(
        """
        SELECT nr, num_reservation, num_commande, client, produit, somme_qte,
               situation, utilisateur, date_reservation, num_client,
               observation, code_maquette
        FROM orders
        ORDER BY date_reservation DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, (page - 1) * per_page),
    ).fetchall()

    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_pages = (total_orders + per_page - 1) // per_page

    conn.close()

    return render_template(
        "orders.html",
        orders=orders_list,
        page=page,
        total_pages=total_pages
    )


# ---- Orders by client (liste avec pagination) ----
@app.route("/clients/<int:client_id>/orders")
def client_orders(client_id):
    conn = get_db_connection()

    client = conn.execute(
        "SELECT N AS id, Entreprise AS company_name FROM client WHERE N = ?",
        (client_id,)
    ).fetchone()

    if not client:
        conn.close()
        return "Client not found", 404

    # --- Pagination ---
    page = request.args.get("page", 1, type=int)
    per_page = 10

    orders_list = conn.execute(
        """
        SELECT nr, num_reservation, num_commande, produit, somme_qte,
               situation, utilisateur, date_reservation, observation, code_maquette
        FROM orders
        WHERE num_client = ?
        ORDER BY date_reservation DESC
        LIMIT ? OFFSET ?
        """,
        (client_id, per_page, (page - 1) * per_page),
    ).fetchall()

    total_orders = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE num_client = ?", (client_id,)
    ).fetchone()[0]
    total_pages = (total_orders + per_page - 1) // per_page

    conn.close()
    return render_template(
        "client_orders.html",
        client=client,
        orders=orders_list,
        page=page,
        total_pages=total_pages
    )


if __name__ == "__main__":
    app.run(debug=True)
