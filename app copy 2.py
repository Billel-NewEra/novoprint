from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3

app = Flask(__name__)
app.secret_key = "change_this_to_a_real_secret_key"

# --- Connexion sqlite3 brut ---
def get_db_connection():
    conn = sqlite3.connect("jack_orders_v3.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---- Dashboard ----
@app.route("/")
def index():
    conn = get_db_connection()

    total_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
    total_orders = conn.execute("SELECT COUNT(*) FROM 'order'").fetchone()[0]
    total_delivery_notes = conn.execute("SELECT COUNT(*) FROM deliverynote").fetchone()[0]
    total_remaining = conn.execute(
        "SELECT COALESCE(SUM(remaining_quantity), 0) FROM orderitem"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        total_clients=total_clients,
        total_orders=total_orders,
        total_delivery_notes=total_delivery_notes,
        total_remaining=total_remaining,
    )


# ---- Clients ----
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
            "SELECT id FROM client WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            flash("⚠️ This email is already used by another client.", "danger")
            conn.close()
            return redirect(url_for("clients"))

        conn.execute(
            "INSERT INTO client (company_name, contact_name, phone, email) VALUES (?, ?, ?, ?)",
            (company_name, contact_name, phone, email),
        )
        conn.commit()
        flash(f"✅ Client « {company_name} » ajouté.", "success")

    clients_list = conn.execute(
        "SELECT id, company_name, contact_name, phone, email FROM client ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("clients.html", clients=clients_list)


# ---- Orders (create + list) ----
@app.route("/orders", methods=["GET", "POST"])
def orders():
    conn = get_db_connection()

    if request.method == "POST":
        client_id = request.form.get("client_id")
        products = request.form.getlist("product[]") or request.form.getlist("product")
        quantities = request.form.getlist("quantity[]") or request.form.getlist("quantity")

        if not client_id:
            flash("⚠️ You must select a client.", "danger")
            conn.close()
            return redirect(url_for("orders"))

        pairs = []
        for p, q in zip(products, quantities):
            p = (p or "").strip()
            try:
                q_int = int(q)
            except Exception:
                q_int = 0
            if p and q_int > 0:
                pairs.append((p, q_int))

        if not pairs:
            flash("⚠️ You must provide at least one product with a positive quantity.", "danger")
            conn.close()
            return redirect(url_for("orders"))

        # Créer la commande
        cur = conn.execute(
            "INSERT INTO 'order' (client_id, status) VALUES (?, ?)",
            (int(client_id), "Pending"),
        )
        order_id = cur.lastrowid

        # Insérer les items
        for prod, qty in pairs:
            conn.execute(
                "INSERT INTO orderitem (order_id, product, quantity, remaining_quantity) VALUES (?, ?, ?, ?)",
                (order_id, prod, qty, qty),
            )

        conn.commit()
        flash("✅ Commande créée avec succès.", "success")
        conn.close()
        return redirect(url_for("orders"))

    client_filter = request.args.get("client_id")
    status_filter = request.args.get("status")

    query = "SELECT * FROM 'order'"
    params = []
    conditions = []

    if client_filter and client_filter != "all":
        conditions.append("client_id = ?")
        params.append(int(client_filter))
    if status_filter and status_filter != "all":
        conditions.append("status = ?")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC"
    orders_list = conn.execute(query, params).fetchall()

    clients_list = conn.execute(
        "SELECT id, company_name FROM client ORDER BY company_name"
    ).fetchall()

    conn.close()
    return render_template("orders.html", orders=orders_list, clients=clients_list)


# ---- Orders by client ----
@app.route("/clients/<int:client_id>/orders")
def client_orders(client_id):
    conn = get_db_connection()
    client = conn.execute("SELECT * FROM client WHERE id = ?", (client_id,)).fetchone()
    if not client:
        conn.close()
        return "Client not found", 404

    orders_list = conn.execute(
        "SELECT * FROM 'order' WHERE client_id = ? ORDER BY id DESC", (client_id,)
    ).fetchall()
    conn.close()
    return render_template("client_orders.html", client=client, orders=orders_list)


# ---- Delivery history ----
@app.route("/orders/<int:order_id>/deliveries")
def delivery_notes(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM 'order' WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return "Order not found", 404

    items = conn.execute(
        "SELECT product, remaining_quantity FROM orderitem WHERE order_id = ?", (order_id,)
    ).fetchall()

    remaining_by_product = {item["product"]: item["remaining_quantity"] for item in items}

    from_client = request.args.get("from_client")
    conn.close()

    return render_template(
        "delivery_notes.html",
        order=order,
        remaining_by_product=remaining_by_product,
        from_client=from_client,
    )


# ---- Add delivery ----
@app.route("/orders/<int:order_id>/deliveries/add", methods=["GET", "POST"])
def add_delivery(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM 'order' WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return "Order not found", 404

    available_items = conn.execute(
        "SELECT * FROM orderitem WHERE order_id = ? AND remaining_quantity > 0", (order_id,)
    ).fetchall()

    from_client = request.args.get("from_client")

    if request.method == "POST":
        order_item_id = request.form.get("order_item_id")
        quantity_raw = request.form.get("quantity")
        bl_phy = request.form.get("bl_phy", "").strip()

        if not order_item_id or not quantity_raw:
            flash("⚠️ Select product and quantity.", "danger")
            conn.close()
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        try:
            quantity = int(quantity_raw)
        except ValueError:
            flash("⚠️ Quantity must be an integer.", "danger")
            conn.close()
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        item = conn.execute(
            "SELECT * FROM orderitem WHERE id = ?", (order_item_id,)
        ).fetchone()

        if not item:
            conn.close()
            return "Item not found", 404

        if quantity <= 0 or quantity > item["remaining_quantity"]:
            flash("⚠️ Invalid quantity (must be between 1 and remaining quantity).", "danger")
            conn.close()
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        # Ajouter la livraison
        conn.execute(
            "INSERT INTO deliverynote (order_id, order_item_id, quantity, bl_phy) VALUES (?, ?, ?, ?)",
            (order_id, order_item_id, quantity, bl_phy),
        )

        # Mettre à jour la quantité restante
        conn.execute(
            "UPDATE orderitem SET remaining_quantity = remaining_quantity - ? WHERE id = ?",
            (quantity, order_item_id),
        )

        # Vérifier le statut de la commande
        all_items = conn.execute(
            "SELECT quantity, remaining_quantity FROM orderitem WHERE order_id = ?",
            (order_id,),
        ).fetchall()

        if all(i["remaining_quantity"] == 0 for i in all_items):
            status = "Completed"
        elif any(i["remaining_quantity"] < i["quantity"] for i in all_items):
            status = "In progress"
        else:
            status = "Pending"

        conn.execute("UPDATE 'order' SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()

        flash(f"✅ Livraison ajoutée (BL: {bl_phy}).", "success")
        conn.close()
        return redirect(url_for("delivery_notes", order_id=order_id, from_client=from_client))

    conn.close()
    return render_template(
        "add_delivery.html", order=order, available_items=available_items, from_client=from_client
    )


if __name__ == "__main__":
    app.run(debug=True)
