from flask import Blueprint, jsonify, request
from app import mysql

main = Blueprint("main", __name__)

@main.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "system": "CreamJoy API",
        "version": "1.0"
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
def get_batches():
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
def get_batch(batch_id):
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
def create_batch():
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
def update_batch_status(batch_id):
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
def get_inventory():
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
def update_inventory(material_id):
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
def get_orders():
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
def create_order():
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
def update_order_status(order_id):
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
