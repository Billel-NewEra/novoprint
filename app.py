from flask import Flask, render_template, request
import sqlite3
from datetime import datetime, timedelta

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
    total_delivery = conn.execute("SELECT COUNT(*) FROM delivery").fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_clients=total_clients,
        total_orders=total_orders,
        total_delivery=total_delivery
    )


# ---- Clients (pagination) ----
@app.route("/clients")
def clients():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 10

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


# ---- Orders (pagination + filtre) ----
@app.route("/orders")
def orders():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 10
    period = request.args.get("period", "all")

    query = """
        SELECT 
            num_reservation, cmdl, client, produit, qte,
            date_reservation, situation, reste
        FROM orders
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM orders WHERE 1=1"
    params, count_params = [], []

    today = datetime.today().date()
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

    query += " ORDER BY num_reservation ASC LIMIT ? OFFSET ?"
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
        period=period
    )



# ---- Orders by client (pas de filtre ici) ----
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

    page = request.args.get("page", 1, type=int)
    per_page = 10

    orders_list = conn.execute(
        """
        SELECT 
            num_reservation, cmdl, client, produit, qte,
            date_reservation, situation, reste
        FROM orders
        WHERE client = ?
        ORDER BY num_reservation ASC
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


# ---- Delivery (pagination + filtre) ----
@app.route("/delivery")
def delivery():
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 10
    period = request.args.get("period", "all")

    query = """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE 1=1
    """
    params = []

    today = datetime.today().date()
    if period == "today":
        query += " AND date(date_livraison) = ?"
        params.append(today)
    elif period == "yesterday":
        query += " AND date(date_livraison) = ?"
        params.append(today - timedelta(days=1))
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        query += " AND date(date_livraison) >= ?"
        params.append(start)
    elif period == "month":
        start = today.replace(day=1)
        query += " AND date(date_livraison) >= ?"
        params.append(start)
    elif period == "year":
        start = today.replace(month=1, day=1)
        query += " AND date(date_livraison) >= ?"
        params.append(start)

    query += " ORDER BY nl ASC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    delivery_list = conn.execute(query, params).fetchall()

    total_delivery = conn.execute("SELECT COUNT(*) FROM delivery").fetchone()[0]
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
        period=period
    )


# ---- Delivery by client (pas de filtre ici) ----
@app.route("/clients/<int:client_id>/delivery")
def client_delivery(client_id):
    conn = get_db_connection()

    client = conn.execute(
        "SELECT N AS id, Entreprise AS company_name FROM client WHERE N = ?",
        (client_id,)
    ).fetchone()
    if not client:
        conn.close()
        return "Client not found", 404

    page = request.args.get("page", 1, type=int)
    per_page = 10

    delivery_list = conn.execute(
        """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE code_client = ?
        ORDER BY nl ASC
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


# ---- Delivery by order (pagination + retour dynamique) ----
@app.route("/orders/<int:order_id>/delivery")
def order_delivery(order_id):
    conn = get_db_connection()

    page = request.args.get("page", 1, type=int)
    per_page = 10
    from_client = request.args.get("from_client")

    delivery_list = conn.execute(
        """
        SELECT 
            nl, code_client, client, qte, montant, num_reservation,
            utilisateur, date_livraison, facture, num_livraison,
            observation, produit
        FROM delivery
        WHERE num_reservation = ?
        ORDER BY nl ASC
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


if __name__ == "__main__":
    app.run(debug=True)
