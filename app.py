import csv
import io
import pandas as pd
from flask import Flask, jsonify, request, render_template, Response
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "inventory_db")
    )

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/products")
def products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products")
    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

@app.route("/low-stock")
def low_stock():
    """Return products whose calculated current stock is at/below reorder level."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.product_id, p.sku, p.product_name,
                   p.opening_stock + COALESCE(SUM(
                       CASE
                           WHEN t.transaction_type = 'IN' THEN t.quantity
                           WHEN t.transaction_type = 'OUT' THEN -t.quantity
                           WHEN t.transaction_type = 'ADJUSTMENT' THEN t.quantity
                           ELSE 0
                       END
                   ), 0) AS current_stock,
                   p.reorder_level
            FROM products p
            LEFT JOIN stock_transactions t ON t.product_id = p.product_id
            GROUP BY p.product_id, p.sku, p.product_name,
                     p.opening_stock, p.reorder_level
            HAVING current_stock <= p.reorder_level
            ORDER BY current_stock ASC, p.product_name
        """)
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()

from flask import request

@app.route("/stock-in", methods=["POST"])
def stock_in():
    data = request.get_json(silent=True) or {}

    try:
        product_id = int(data.get("product_id", 0))
        quantity = int(data.get("quantity", 0))
        supplier_id = data.get("supplier_id")

        if product_id <= 0 or quantity <= 0:
            return jsonify({
                "error": "Product ID and quantity must be positive numbers."
            }), 400

        if supplier_id in ("", None):
            supplier_id = None
        else:
            supplier_id = int(supplier_id)

    except (ValueError, TypeError):
        return jsonify({"error": "Invalid input values."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check whether this product exists in the connected database
        cursor.execute(
            "SELECT product_id FROM products WHERE product_id = %s",
            (product_id,)
        )

        if cursor.fetchone() is None:
            return jsonify({
                "error": f"Product ID {product_id} does not exist in inventory_db."
            }), 404

        # Check whether the selected supplier exists
        if supplier_id is not None:
            cursor.execute(
                "SELECT supplier_id FROM suppliers WHERE supplier_id = %s",
                (supplier_id,)
            )

            if cursor.fetchone() is None:
                return jsonify({
                    "error": f"Supplier ID {supplier_id} does not exist."
                }), 404

        cursor.execute("""
            INSERT INTO stock_transactions
                (product_id, transaction_type, quantity, supplier_id)
            VALUES (%s, 'IN', %s, %s)
        """, (product_id, quantity, supplier_id))

        conn.commit()

        return jsonify({
            "message": "Stock received successfully!",
            "product_id": product_id,
            "quantity": quantity
        }), 201

    except Exception as e:
        conn.rollback()
        app.logger.exception("Stock-in failed")
        return jsonify({"error": str(e)}), 400

    finally:
        cursor.close()
        conn.close()


@app.route("/stock-out", methods=["POST"])
def stock_out():
    data = request.get_json(silent=True) or {}

    product_id = data.get("product_id")
    quantity = data.get("quantity")

    if type(product_id) is not int or product_id <= 0:
        return jsonify({"error": "Valid product_id is required"}), 400

    if type(quantity) is not int or quantity <= 0:
        return jsonify({"error": "Quantity must be a positive integer"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Lock the product row to prevent concurrent stock-outs
        cursor.execute(
            "SELECT opening_stock FROM products WHERE product_id = %s FOR UPDATE",
            (product_id,)
        )
        product = cursor.fetchone()

        if product is None:
            conn.rollback()
            return jsonify({"error": "Product not found"}), 404

        opening_stock = product[0]

        cursor.execute("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN transaction_type = 'IN' THEN quantity
                    WHEN transaction_type = 'OUT' THEN -quantity
                    WHEN transaction_type = 'ADJUSTMENT' THEN quantity
                    ELSE 0
                END
            ), 0)
            FROM stock_transactions
            WHERE product_id = %s
        """, (product_id,))

        movement = cursor.fetchone()[0]
        current_stock = opening_stock + movement

        if quantity > current_stock:
            conn.rollback()
            return jsonify({
                "error": "Insufficient stock",
                "current_stock": current_stock
            }), 400

        cursor.execute("""
            INSERT INTO stock_transactions
                (product_id, transaction_type, quantity)
            VALUES (%s, 'OUT', %s)
        """, (product_id, quantity))

        conn.commit()

        return jsonify({
            "message": "Stock-out recorded successfully",
            "product_id": product_id,
            "quantity_sold": quantity,
            "remaining_stock": current_stock - quantity
        }), 201

    except Exception:
        conn.rollback()
        app.logger.exception("Stock-out failed")
        return jsonify({"error": "Unable to record stock-out"}), 500

    finally:
        cursor.close()
        conn.close()


@app.route("/stock-report")
def stock_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                p.product_id,
                p.sku,
                p.product_name,
                p.opening_stock,
                COALESCE(SUM(
                    CASE
                        WHEN t.transaction_type = 'IN'
                            THEN t.quantity
                        WHEN t.transaction_type = 'OUT'
                            THEN -t.quantity
                        WHEN t.transaction_type = 'ADJUSTMENT'
                            THEN t.quantity
                        ELSE 0
                    END
                ), 0) AS net_movement,
                p.opening_stock + COALESCE(SUM(
                    CASE
                        WHEN t.transaction_type = 'IN'
                            THEN t.quantity
                        WHEN t.transaction_type = 'OUT'
                            THEN -t.quantity
                        WHEN t.transaction_type = 'ADJUSTMENT'
                            THEN t.quantity
                        ELSE 0
                    END
                ), 0) AS current_stock,
                p.reorder_level,
                p.unit_cost,
                (p.opening_stock + COALESCE(SUM(
                    CASE
                        WHEN t.transaction_type = 'IN'
                            THEN t.quantity
                        WHEN t.transaction_type = 'OUT'
                            THEN -t.quantity
                        WHEN t.transaction_type = 'ADJUSTMENT'
                            THEN t.quantity
                        ELSE 0
                    END
                ), 0)) * p.unit_cost AS stock_value
            FROM products p
            LEFT JOIN stock_transactions t
                ON p.product_id = t.product_id
            GROUP BY
                p.product_id, p.sku, p.product_name,
                p.opening_stock, p.reorder_level, p.unit_cost
            ORDER BY p.product_name
        """)

        return jsonify(cursor.fetchall())

    finally:
        cursor.close()
        conn.close()


@app.route("/analysis")
def analysis():
    conn = get_db_connection()

    try:
        df = pd.read_sql("""
            SELECT
                p.product_name,
                p.opening_stock
                    + COALESCE(SUM(
                        CASE
                            WHEN t.transaction_type = 'IN'
                                THEN t.quantity
                            WHEN t.transaction_type = 'OUT'
                                THEN -t.quantity
                            WHEN t.transaction_type = 'ADJUSTMENT'
                                THEN t.quantity
                            ELSE 0
                        END
                    ), 0) AS current_stock,
                p.reorder_level,
                p.unit_cost
            FROM products p
            LEFT JOIN stock_transactions t
                ON p.product_id = t.product_id
            GROUP BY
                p.product_id, p.product_name,
                p.opening_stock, p.reorder_level, p.unit_cost
        """, conn)

        return jsonify({
            "total_products": int(len(df)),
            "total_stock_units": int(df["current_stock"].sum()),
            "total_inventory_value": round(
                float((df["current_stock"] * df["unit_cost"]).sum()), 2
            ),
            "low_stock_products": df[
                df["current_stock"] <= df["reorder_level"]
            ]["product_name"].tolist()
        })

    finally:
        conn.close()

@app.route("/stock-history")
def stock_history():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                t.transaction_id,
                t.transaction_date,
                p.product_name,
                p.sku,
                t.transaction_type,
                t.quantity,
                t.supplier_id
            FROM stock_transactions t
            JOIN products p
                ON t.product_id = p.product_id
            ORDER BY t.transaction_date DESC,
                     t.transaction_id DESC
        """)

        return jsonify(cursor.fetchall())

    finally:
        cursor.close()
        conn.close()


@app.route("/add-product", methods=["POST"])
def add_product():
    data = request.get_json(silent=True) or {}

    sku = str(data.get("sku", "")).strip()
    product_name = str(data.get("product_name", "")).strip()
    category = str(data.get("category", "")).strip()

    try:
        opening_stock = int(data.get("opening_stock", 0))
        reorder_level = int(data.get("reorder_level", 10))
        unit_cost = float(data.get("unit_cost", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Enter valid numeric values."}), 400

    if not sku or not product_name:
        return jsonify({"error": "SKU and product name are required."}), 400

    if opening_stock < 0 or reorder_level < 0 or unit_cost < 0:
        return jsonify({"error": "Stock, reorder level, and cost cannot be negative."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO products
                (sku, product_name, category, opening_stock,
                 reorder_level, unit_cost)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            sku, product_name, category or None,
            opening_stock, reorder_level, unit_cost
        ))

        conn.commit()

        return jsonify({
            "message": "Product added successfully!",
            "product_id": cursor.lastrowid
        }), 201

    except mysql.connector.IntegrityError:
        conn.rollback()
        return jsonify({
            "error": "This SKU already exists. Use a unique SKU."
        }), 409

    except mysql.connector.Error:
        conn.rollback()
        return jsonify({"error": "Database error while adding product."}), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/update-product/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    data = request.get_json(silent=True) or {}
    sku = str(data.get("sku", "")).strip()
    product_name = str(data.get("product_name", "")).strip()
    category = str(data.get("category", "")).strip()
    try:
        reorder_level = int(data.get("reorder_level"))
        unit_cost = float(data.get("unit_cost"))
    except (TypeError, ValueError):
        return jsonify({"error": "Reorder level must be a whole number and unit cost must be numeric."}), 400
    if not sku or not product_name:
        return jsonify({"error": "SKU and product name are required."}), 400
    if reorder_level < 0 or unit_cost < 0:
        return jsonify({"error": "Reorder level and unit cost cannot be negative."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT product_id FROM products WHERE product_id = %s", (product_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Product not found."}), 404
        cursor.execute("UPDATE products SET sku=%s, product_name=%s, category=%s, reorder_level=%s, unit_cost=%s WHERE product_id=%s",
                       (sku, product_name, category or None, reorder_level, unit_cost, product_id))
        conn.commit()
        return jsonify({"message": "Product updated successfully!"})
    except mysql.connector.IntegrityError:
        conn.rollback()
        return jsonify({"error": "That SKU is already used by another product."}), 409
    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Product update failed")
        return jsonify({"error": "Could not update product. Check the Flask terminal."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/delete-product/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT product_id FROM products WHERE product_id = %s", (product_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Product not found."}), 404
        cursor.execute("SELECT COUNT(*) FROM stock_transactions WHERE product_id = %s", (product_id,))
        if cursor.fetchone()[0] > 0:
            return jsonify({"error": "This product has transaction history and cannot be deleted. Keep it for accurate reports."}), 409
        cursor.execute("DELETE FROM products WHERE product_id = %s", (product_id,))
        conn.commit()
        return jsonify({"message": "Product deleted successfully."})
    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Product deletion failed")
        return jsonify({"error": "Could not delete product. Check the Flask terminal."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/delete-supplier/<int:supplier_id>", methods=["DELETE"])
def delete_supplier(supplier_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT supplier_id FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Supplier not found."}), 404
        cursor.execute("SELECT COUNT(*) FROM stock_transactions WHERE supplier_id = %s", (supplier_id,))
        if cursor.fetchone()[0] > 0:
            return jsonify({"error": "This supplier is linked to stock transaction history and cannot be deleted."}), 409
        cursor.execute("DELETE FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        conn.commit()
        return jsonify({"message": "Supplier deleted successfully."})
    except mysql.connector.Error:
        conn.rollback()
        app.logger.exception("Supplier deletion failed")
        return jsonify({"error": "Could not delete supplier. Check the Flask terminal."}), 500
    finally:
        cursor.close()
        conn.close()


def csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/export/products.csv")
def export_products_csv():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.product_id, p.sku, p.product_name, p.category,
                   p.opening_stock + COALESCE(SUM(CASE
                       WHEN t.transaction_type='IN' THEN t.quantity
                       WHEN t.transaction_type='OUT' THEN -t.quantity
                       WHEN t.transaction_type='ADJUSTMENT' THEN t.quantity
                       ELSE 0 END), 0) AS current_stock,
                   p.reorder_level, p.unit_cost,
                   (p.opening_stock + COALESCE(SUM(CASE
                       WHEN t.transaction_type='IN' THEN t.quantity
                       WHEN t.transaction_type='OUT' THEN -t.quantity
                       WHEN t.transaction_type='ADJUSTMENT' THEN t.quantity
                       ELSE 0 END), 0)) * p.unit_cost AS stock_value
            FROM products p LEFT JOIN stock_transactions t ON t.product_id=p.product_id
            GROUP BY p.product_id, p.sku, p.product_name, p.category,
                     p.opening_stock, p.reorder_level, p.unit_cost
            ORDER BY p.product_name
        """)
        rows = cursor.fetchall()
        headers = ["Product ID", "SKU", "Product Name", "Category", "Current Stock", "Reorder Level", "Unit Cost", "Stock Value"]
        return csv_response("inventory_report.csv", headers, [[r.get(k) for k in ("product_id", "sku", "product_name", "category", "current_stock", "reorder_level", "unit_cost", "stock_value")] for r in rows])
    finally:
        cursor.close()
        conn.close()


@app.route("/export/transactions.csv")
def export_transactions_csv():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT t.transaction_id, t.transaction_date, p.product_name, p.sku,
                   t.transaction_type, t.quantity, t.supplier_id
            FROM stock_transactions t JOIN products p ON p.product_id=t.product_id
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
        """)
        rows = cursor.fetchall()
        headers = ["Transaction ID", "Date", "Product Name", "SKU", "Transaction Type", "Quantity", "Supplier ID"]
        keys = ("transaction_id", "transaction_date", "product_name", "sku", "transaction_type", "quantity", "supplier_id")
        return csv_response("transaction_report.csv", headers, [[r.get(k) for k in keys] for r in rows])
    finally:
        cursor.close()
        conn.close()


@app.route("/suppliers", methods=["GET"])
def get_suppliers():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT supplier_id, supplier_name, contact_number, email
            FROM suppliers
            ORDER BY supplier_id DESC
        """)

        return jsonify(cursor.fetchall())

    finally:
        cursor.close()
        conn.close()


@app.route("/add-supplier", methods=["POST"])
def add_supplier():
    data = request.get_json(silent=True) or {}

    supplier_name = str(data.get("supplier_name", "")).strip()
    contact_number = str(data.get("contact_number", "")).strip()
    email = str(data.get("email", "")).strip()

    if not supplier_name:
        return jsonify({"error": "Supplier name is required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO suppliers
                (supplier_name, contact_number, email)
            VALUES (%s, %s, %s)
        """, (
            supplier_name,
            contact_number or None,
            email or None
        ))

        conn.commit()

        return jsonify({
            "message": "Supplier added successfully!",
            "supplier_id": cursor.lastrowid
        }), 201

    except mysql.connector.Error as e:
        conn.rollback()
        print("Supplier database error:", e)
        return jsonify({
            "error": "Could not add supplier. Check the Flask terminal."
        }), 500

    finally:
        cursor.close()
        conn.close()


@app.route("/update-supplier/<int:supplier_id>", methods=["PUT"])
def update_supplier(supplier_id):
    data = request.get_json(silent=True) or {}
    supplier_name = str(data.get("supplier_name", "")).strip()
    contact_number = str(data.get("contact_number", "")).strip()
    email = str(data.get("email", "")).strip()

    if not supplier_name:
        return jsonify({"error": "Supplier name is required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT supplier_id FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Supplier not found."}), 404

        cursor.execute(
            "UPDATE suppliers SET supplier_name = %s, contact_number = %s, email = %s WHERE supplier_id = %s",
            (supplier_name, contact_number or None, email or None, supplier_id)
        )
        conn.commit()
        return jsonify({"message": "Supplier updated successfully!"})
    except mysql.connector.Error as e:
        conn.rollback()
        print("Supplier update database error:", e)
        return jsonify({"error": "Could not update supplier. Check the Flask terminal."}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    app.run(debug=True)


