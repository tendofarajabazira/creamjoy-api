from functools import wraps
from datetime import datetime, timedelta

import jwt
from flask import Blueprint, jsonify, request, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from app import mysql

main = Blueprint("main", __name__)


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Token is missing"}), 401

        try:
            parts = auth_header.split(" ")

            if len(parts) != 2 or parts[0] != "Bearer":
                return jsonify({"error": "Invalid token format"}), 401

            token = parts[1]

            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET"],
                algorithms=["HS256"]
            )

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401

        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(payload, *args, **kwargs)

    return decorated


@main.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "system": "CreamJoy API",
        "version": "1.0"
    })


@main.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")

    if not name or not email or not password or not role:
        return jsonify({"error": "name, email, password and role are required"}), 400

    password_hash = generate_password_hash(password)

    cur = mysql.connection.cursor()

    try:
        cur.execute("""
            INSERT INTO staff (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, password_hash, role))

        mysql.connection.commit()

    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({"error": str(e)}), 400

    cur.close()

    return jsonify({"message": "Staff registered successfully"}), 201


@main.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT staff_id, name, email, password_hash, role
        FROM staff
        WHERE email = %s
    """, (email,))

    staff = cur.fetchone()
    cur.close()

    if not staff:
        return jsonify({"error": "Invalid email or password"}), 401

    staff_id = staff[0]
    name = staff[1]
    saved_password_hash = staff[3]
    role = staff[4]

    if not check_password_hash(saved_password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    payload = {
        "staff_id": staff_id,
        "name": name,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }

    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET"],
        algorithm="HS256"
    )

    return jsonify({
        "message": "Login successful",
        "token": token
    })


@main.route("/api/auth/me", methods=["GET"])
@token_required
def auth_me(current_staff):
    return jsonify({
        "staff_id": current_staff["staff_id"],
        "name": current_staff["name"],
        "role": current_staff["role"]
    })


@main.route("/api/products", methods=["GET"])
def products():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT product_id, flavour, size
        FROM products
        ORDER BY flavour, size
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close()

    products_list = []
    for row in rows:
        products_list.append({
            "product_id": row[0],
            "flavour": row[1],
            "size": row[2]
        })

    return jsonify(products_list)


@main.route("/api/batches", methods=["GET"])
@token_required
def get_batches(current_staff):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            b.batch_id,
            b.batch_number,
            b.batch_date,
            b.status,
            COALESCE(SUM(bp.quantity_produced), 0) AS total_units
        FROM batches b
        LEFT JOIN batch_products bp ON b.batch_id = bp.batch_id
        GROUP BY b.batch_id, b.batch_number, b.batch_date, b.status
        ORDER BY b.batch_date DESC
    """)
    rows = cur.fetchall()
    cur.close()

    result = []
    for row in rows:
        result.append({
            "batch_id": row[0],
            "batch_number": row[1],
            "batch_date": str(row[2]),
            "status": row[3],
            "total_units": int(row[4])
        })

    return jsonify(result)


@main.route("/api/batches/<int:batch_id>", methods=["GET"])
@token_required
def get_batch(current_staff, batch_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            b.batch_id,
            b.batch_number,
            b.batch_date,
            b.status,
            p.flavour,
            p.size,
            bp.quantity_produced
        FROM batches b
        JOIN batch_products bp ON b.batch_id = bp.batch_id
        JOIN products p ON bp.product_id = p.product_id
        WHERE b.batch_id = %s
        ORDER BY p.flavour, p.size
    """, (batch_id,))
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return jsonify({"error": "Batch not found"}), 404

    batch = {
        "batch_id": rows[0][0],
        "batch_number": rows[0][1],
        "batch_date": str(rows[0][2]),
        "status": rows[0][3],
        "products": []
    }

    for row in rows:
        batch["products"].append({
            "flavour": row[4],
            "size": row[5],
            "quantity_produced": row[6]
        })

    return jsonify(batch)


@main.route("/api/batches", methods=["POST"])
@token_required
def create_batch(current_staff):
    if current_staff["role"] not in ["production", "supervisor"]:
        return jsonify({"error": "Forbidden: only production or supervisor staff can create batches"}), 403

    data = request.get_json()

    batch_number = data.get("batch_number")
    batch_date = data.get("date")
    status = data.get("status", "in_progress")
    products = data.get("products", [])

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO batches (batch_number, batch_date, status)
        VALUES (%s, %s, %s)
    """, (batch_number, batch_date, status))

    batch_id = cur.lastrowid

    for product in products:
        cur.execute("""
            INSERT INTO batch_products (batch_id, product_id, quantity_produced)
            VALUES (%s, %s, %s)
        """, (batch_id, product["product_id"], product["quantity"]))

    mysql.connection.commit()
    cur.close()

    return jsonify({
        "message": "Batch created",
        "batch_id": batch_id
    }), 201


@main.route("/api/batches/<int:batch_id>/status", methods=["PUT"])
@token_required
def update_batch_status(current_staff, batch_id):
    data = request.get_json()
    status = data.get("status")

    if status not in ["completed", "in_progress"]:
        return jsonify({"error": "Invalid status"}), 400

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE batches
        SET status = %s
        WHERE batch_id = %s
    """, (status, batch_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Batch status updated"})


@main.route("/api/inventory", methods=["GET"])
@token_required
def get_inventory(current_staff):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT material_id, material_name, current_stock, minimum_stock
        FROM raw_materials
        ORDER BY material_name
    """)
    rows = cur.fetchall()
    cur.close()

    result = []
    for row in rows:
        current_stock = float(row[2])
        minimum_stock = float(row[3])

        result.append({
            "material_id": row[0],
            "material_name": row[1],
            "current_stock": current_stock,
            "minimum_stock": minimum_stock,
            "low_stock": current_stock < minimum_stock
        })

    return jsonify(result)


@main.route("/api/inventory/<int:material_id>", methods=["PUT"])
@token_required
def update_inventory(current_staff, material_id):
    data = request.get_json()
    current_stock = data.get("current_stock")

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE raw_materials
        SET current_stock = %s
        WHERE material_id = %s
    """, (current_stock, material_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Inventory updated"})


@main.route("/api/orders", methods=["GET"])
@token_required
def get_orders(current_staff):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            o.order_id,
            c.customer_name,
            o.order_date,
            o.payment_method,
            o.payment_status,
            o.total_amount
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        ORDER BY o.order_date DESC
    """)
    rows = cur.fetchall()
    cur.close()

    result = []
    for row in rows:
        result.append({
            "order_id": row[0],
            "customer_name": row[1],
            "order_date": str(row[2]),
            "payment_method": row[3],
            "payment_status": row[4],
            "total_amount": float(row[5])
        })

    return jsonify(result)


@main.route("/api/orders", methods=["POST"])
@token_required
def create_order(current_staff):
    data = request.get_json()

    customer_id = data.get("customer_id")
    order_lines = data.get("order_lines", [])
    payment_method = data.get("payment_method", "cash")

    total_amount = 0

    cur = mysql.connection.cursor()

    for line in order_lines:
        cur.execute("""
            SELECT unit_price
            FROM products
            WHERE product_id = %s
        """, (line["product_id"],))
        product = cur.fetchone()

        if product:
            total_amount += float(product[0]) * int(line["qty"])

    cur.execute("""
        INSERT INTO orders (customer_id, order_date, payment_method, payment_status, total_amount)
        VALUES (%s, CURDATE(), %s, 'pending', %s)
    """, (customer_id, payment_method, total_amount))

    order_id = cur.lastrowid

    for line in order_lines:
        cur.execute("""
            SELECT unit_price
            FROM products
            WHERE product_id = %s
        """, (line["product_id"],))
        product = cur.fetchone()
        unit_price = float(product[0]) if product else 0
        line_total = unit_price * int(line["qty"])

        cur.execute("""
            INSERT INTO order_lines (order_id, product_id, quantity, line_total)
            VALUES (%s, %s, %s, %s)
        """, (order_id, line["product_id"], line["qty"], line_total))

    mysql.connection.commit()
    cur.close()

    return jsonify({
        "message": "Order created",
        "order_id": order_id,
        "total_amount": total_amount
    }), 201


@main.route("/api/orders/<int:order_id>/status", methods=["PUT"])
@token_required
def update_order_status(current_staff, order_id):
    data = request.get_json()
    status = data.get("status")

    if status not in ["pending", "dispatched", "delivered"]:
        return jsonify({"error": "Invalid status"}), 400

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE orders
        SET payment_status = %s
        WHERE order_id = %s
    """, (status, order_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Order status updated"})
@main.route("/api/expenditures", methods=["POST"])
@token_required
def create_expenditure(current_staff):
    data = request.get_json()

    expenditure_date = data.get("date")
    category = data.get("category")
    description = data.get("description")
    quantity = data.get("quantity")
    unit = data.get("unit")
    amount = data.get("amount")
    paid_by = data.get("paid_by")
    notes = data.get("notes")

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO expenditures
        (expenditure_date, item_name, category, amount, notes)
        VALUES (%s, %s, %s, %s, %s)
    """, (expenditure_date, description, category, amount, notes))

    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Expenditure recorded successfully"}), 201
