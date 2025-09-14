from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    contact_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), unique=True, nullable=False)
    orders = db.relationship("Order", backref="client", lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    status = db.Column(db.String(50), default="Pending")
    items = db.relationship("OrderItem", backref="order", lazy=True)
    delivery_notes = db.relationship("DeliveryNote", backref="order", lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    remaining_quantity = db.Column(db.Integer, nullable=False)
    delivery_notes = db.relationship("DeliveryNote", backref="order_item", lazy=True)

class DeliveryNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    bl_phy = db.Column(db.String(100))  # Nouveau champ BL physique
