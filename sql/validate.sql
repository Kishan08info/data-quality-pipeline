-- Validation gate for the cleaned tables in data/ecommerce.sqlite.
-- Run by src/pipeline.py after loading the cleaned CSVs; every check must
-- return 0 violations or the run fails. One statement per check, each
-- returning (check_name, violations).

SELECT 'customers_null_email' AS check_name,
       COUNT(*) AS violations FROM customers WHERE email IS NULL;
SELECT 'customers_duplicate_customer_id' AS check_name,
       COUNT(*) AS violations FROM (
           SELECT customer_id FROM customers
           GROUP BY customer_id HAVING COUNT(*) > 1);
SELECT 'customers_duplicate_email' AS check_name,
       COUNT(*) AS violations FROM (
           SELECT email FROM customers
           GROUP BY email HAVING COUNT(*) > 1);
SELECT 'customers_bad_age' AS check_name,
       COUNT(*) AS violations FROM customers
       WHERE age IS NULL OR age < 1 OR age > 120;
SELECT 'customers_bad_country' AS check_name,
       COUNT(*) AS violations FROM customers
       WHERE country NOT IN ('US', 'CA', 'GB', 'AU', 'DE');
SELECT 'customers_bad_signup_date' AS check_name,
       COUNT(*) AS violations FROM customers
       WHERE signup_date IS NULL OR LENGTH(signup_date) != 10;
SELECT 'products_duplicate_product_id' AS check_name,
       COUNT(*) AS violations FROM (
           SELECT product_id FROM products
           GROUP BY product_id HAVING COUNT(*) > 1);
SELECT 'products_duplicate_sku' AS check_name,
       COUNT(*) AS violations FROM (
           SELECT sku FROM products GROUP BY sku HAVING COUNT(*) > 1);
SELECT 'products_bad_price' AS check_name,
       COUNT(*) AS violations FROM products
       WHERE price IS NULL OR price <= 0;
SELECT 'products_bad_category' AS check_name,
       COUNT(*) AS violations FROM products
       WHERE category NOT IN ('Electronics', 'Home & Garden', 'Clothing',
                              'Sports', 'Books');
SELECT 'orders_duplicate_order_id' AS check_name,
       COUNT(*) AS violations FROM (
           SELECT order_id FROM orders
           GROUP BY order_id HAVING COUNT(*) > 1);
SELECT 'orders_bad_amount' AS check_name,
       COUNT(*) AS violations FROM orders
       WHERE amount IS NULL OR amount <= 0;
SELECT 'orders_bad_quantity' AS check_name,
       COUNT(*) AS violations FROM orders
       WHERE quantity IS NULL OR quantity <= 0;
SELECT 'orders_bad_status' AS check_name,
       COUNT(*) AS violations FROM orders
       WHERE status NOT IN ('shipped', 'delivered', 'cancelled',
                            'pending', 'returned');
SELECT 'orders_bad_order_date' AS check_name,
       COUNT(*) AS violations FROM orders
       WHERE order_date IS NULL OR LENGTH(order_date) != 10;
SELECT 'orders_orphan_customer' AS check_name,
       COUNT(*) AS violations FROM orders o
       WHERE NOT EXISTS (SELECT 1 FROM customers c
                         WHERE c.customer_id = o.customer_id);
SELECT 'orders_orphan_product' AS check_name,
       COUNT(*) AS violations FROM orders o
       WHERE NOT EXISTS (SELECT 1 FROM products p
                         WHERE p.product_id = o.product_id);
SELECT 'orders_before_signup' AS check_name,
       COUNT(*) AS violations FROM orders o
       JOIN customers c ON c.customer_id = o.customer_id
       WHERE o.order_date < c.signup_date;
