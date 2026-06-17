from flask import Blueprint, jsonify

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
    return jsonify([
        {"product_id": 1, "flavour": "Millet", "size": "300ml"},
        {"product_id": 2, "flavour": "Vanilla", "size": "300ml"},
        {"product_id": 3, "flavour": "Chocolate", "size": "300ml"}
    ])
