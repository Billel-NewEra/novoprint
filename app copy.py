from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from models import db, Client, Order, OrderItem, DeliveryNote

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jack_orders_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "change_this_to_a_real_secret_key"

# Initialise SQLAlchemy
db.init_app(app)

with app.app_context():
    db.create_all()


# ---- Dashboard ----
@app.route("/")
def index():
    total_clients = Client.query.count()
    total_orders = Order.query.count()
    total_delivery_notes = DeliveryNote.query.count()
    total_remaining = db.session.query(func.sum(OrderItem.remaining_quantity)).scalar() or 0

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
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()

        if not company_name or not contact_name or not email:
            flash("⚠️ Company, contact and email are required.", "danger")
            return redirect(url_for("clients"))

        existing = Client.query.filter_by(email=email).first()
        if existing:
            flash("⚠️ This email is already used by another client.", "danger")
            return redirect(url_for("clients"))

        client = Client(
            company_name=company_name,
            contact_name=contact_name,
            phone=phone,
            email=email,
        )
        db.session.add(client)
        db.session.commit()
        flash(f"✅ Client « {company_name} » ajouté.", "success")
        return redirect(url_for("clients"))

    clients_list = Client.query.order_by(Client.id.desc()).all()
    return render_template("clients.html", clients=clients_list)


# ---- Orders (create + list) ----
@app.route("/orders", methods=["GET", "POST"])
def orders():
    if request.method == "POST":
        client_id = request.form.get("client_id")
        products = request.form.getlist("product[]") or request.form.getlist("product")
        quantities = request.form.getlist("quantity[]") or request.form.getlist("quantity")

        if not client_id:
            flash("⚠️ You must select a client.", "danger")
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
            return redirect(url_for("orders"))

        order = Order(client_id=int(client_id), status="Pending")
        db.session.add(order)
        db.session.flush()  # get order.id

        for prod, qty in pairs:
            item = OrderItem(order_id=order.id, product=prod, quantity=qty, remaining_quantity=qty)
            db.session.add(item)

        db.session.commit()
        flash("✅ Commande créée avec succès.", "success")
        return redirect(url_for("orders"))

    client_filter = request.args.get("client_id")
    status_filter = request.args.get("status")

    query = Order.query
    if client_filter and client_filter != "all":
        query = query.filter_by(client_id=int(client_filter))
    if status_filter and status_filter != "all":
        query = query.filter_by(status=status_filter)

    orders_list = query.order_by(Order.id.desc()).all()
    clients_list = Client.query.order_by(Client.company_name).all()
    return render_template("orders.html", orders=orders_list, clients=clients_list)


# ---- Orders by client ----
@app.route("/clients/<int:client_id>/orders")
def client_orders(client_id):
    client = Client.query.get_or_404(client_id)
    orders_list = Order.query.filter_by(client_id=client_id).order_by(Order.id.desc()).all()
    return render_template("client_orders.html", client=client, orders=orders_list)


# ---- Delivery history ----
@app.route("/orders/<int:order_id>/deliveries")
def delivery_notes(order_id):
    order = Order.query.get_or_404(order_id)

    remaining_by_product = {item.product: item.remaining_quantity for item in order.items}

    from_client = request.args.get("from_client")

    return render_template(
        "delivery_notes.html",
        order=order,
        remaining_by_product=remaining_by_product,
        from_client=from_client
    )


# ---- Add delivery ----
@app.route("/orders/<int:order_id>/deliveries/add", methods=["GET", "POST"])
def add_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    available_items = [it for it in order.items if it.remaining_quantity > 0]

    from_client = request.args.get("from_client")

    if request.method == "POST":
        order_item_id = request.form.get("order_item_id")
        quantity_raw = request.form.get("quantity")
        bl_phy = request.form.get("bl_phy", "").strip()

        if not order_item_id or not quantity_raw:
            flash("⚠️ Select product and quantity.", "danger")
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        try:
            quantity = int(quantity_raw)
        except ValueError:
            flash("⚠️ Quantity must be an integer.", "danger")
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        item = OrderItem.query.get_or_404(int(order_item_id))

        if quantity <= 0 or quantity > item.remaining_quantity:
            flash("⚠️ Invalid quantity (must be between 1 and remaining quantity).", "danger")
            return redirect(url_for("add_delivery", order_id=order_id, from_client=from_client))

        delivery = DeliveryNote(order_id=order.id, order_item_id=item.id, quantity=quantity, bl_phy=bl_phy)
        db.session.add(delivery)

        item.remaining_quantity -= quantity

        all_items = OrderItem.query.filter_by(order_id=order.id).all()
        if all(i.remaining_quantity == 0 for i in all_items):
            order.status = "Completed"
        elif any(i.remaining_quantity < i.quantity for i in all_items):
            order.status = "In progress"
        else:
            order.status = "Pending"

        db.session.commit()
        flash(f"✅ Livraison ajoutée pour « {item.product} » (BL: {bl_phy}).", "success")
        return redirect(url_for("delivery_notes", order_id=order.id, from_client=from_client))

    return render_template("add_delivery.html", order=order, available_items=available_items, from_client=from_client)


if __name__ == "__main__":
    app.run(debug=True)
