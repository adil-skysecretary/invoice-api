from odoo import http
from odoo.http import request, Response
import json
import logging
_logger = logging.getLogger(__name__)

class ExternalSalesSyncController(http.Controller):

    def _authenticate_request(self):
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False, Response(json.dumps({'error': 'Missing or invalid token'}), status=401,
                                   content_type='application/json')

        token = auth_header.split('Bearer ')[1].strip()

        key_obj = request.env['skypos.api.key'].sudo().search([
            ('api_key', '=', token),
            ('active', '=', True)
        ], limit=1)

        if not key_obj:
            return False, Response(json.dumps({'error': 'Unauthorized'}), status=401, content_type='application/json')

        return True, None

    @http.route('/api/sales/create', type='json', auth='public', methods=['POST'], csrf=False)
    def create_sale(self, **kwargs):
        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response

        try:
            # 'kwargs' contains parsed JSON body from "params"
            data = kwargs
            _logger.info("Received data: %s", data)

            ext_cust_id = data.get('external_customer_id')
            customer_name = data.get('customer_name', 'New Customer')
            items = data.get('order_lines', [])
            post_invoice = data.get('invoice', False)

            cust_map = request.env['customer.id.mapping'].sudo().search([('external_customer_id', '=', ext_cust_id)],
                                                                        limit=1)
            if not cust_map:
                if not cust_map:
                    partner_vals = {
                        'name': customer_name,
                    }
                    partner = request.env['res.partner'].sudo().create(partner_vals)
                    cust_map = request.env['customer.id.mapping'].sudo().create({
                        'external_customer_id': ext_cust_id,
                        'partner_id': partner.id,
                    })
                    _logger.info("Created new partner and mapping for %s", ext_cust_id)

            order_lines = []
            for item in items:
                external_pid = item['external_product_id']
                prod_map = request.env['product.id.mapping'].sudo().search(
                    [('external_product_id', '=', external_pid)], limit=1)

                if not prod_map:
                    # Generate name if not provided
                    product_name = item.get('product_name') or f"Product {external_pid}"

                    product_vals = {
                        'name': product_name,
                        'lst_price': item.get('price_unit', 0.0),
                    }
                    product = request.env['product.product'].sudo().create(product_vals)

                    prod_map = request.env['product.id.mapping'].sudo().create({
                        'external_product_id': external_pid,
                        'product_id': product.id,
                    })
                    _logger.info("Created new product and mapping for %s", external_pid)

                order_lines.append((0, 0, {
                    'product_id': prod_map.product_id.id,
                    'product_uom_qty': item.get('quantity', 1),
                    'price_unit': item.get('price_unit', prod_map.product_id.lst_price),
                    'discount': item.get('discount', 0),
                    'tax_id': [(6, 0, [item['tax_id']])] if item.get('tax_id') else False,
                }))

            order = request.env['sale.order'].sudo().create({
                'partner_id': cust_map.partner_id.id,
                'order_line': order_lines
            })
            order.action_confirm()

            if post_invoice:
                invoice = order._create_invoices()
                invoice.action_post()
                return {"status": "Invoice Created", "invoice_id": invoice.id}

            return {"status": "Order Created", "order_id": order.id}


        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "result": {
                    "error": str(e),
                    "message": "Invalid JSON structure or server error"
                }
            }


    @http.route('/external_sales/create_customer', type='json', auth='public', methods=['POST'], csrf=False)
    def create_customer_from_skypos(self, **kwargs):
        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response

        try:
            data = kwargs
            _logger.info("Received customer creation request: %s", data)

            external_id = data.get('external_customer_id')
            name = data.get('name')
            email = data.get('email')
            phone = data.get('phone')

            # Validate input
            required_fields = ['external_customer_id', 'name', 'email', 'phone']
            missing = [f for f in required_fields if not data.get(f)]
            if missing:
                return {
                    'status': 'error',
                    'message': f'Missing fields: {", ".join(missing)}'
                }

            # Check if customer already exists by external ID
            mapping = request.env['customer.id.mapping'].sudo().search([('external_customer_id', '=', external_id)], limit=1)
            if mapping:
                return {
                    'status': 'success',
                    'message': 'Customer already exists',
                    'partner_id': mapping.partner_id.id
                }

            # Otherwise, create the customer
            partner = request.env['res.partner'].sudo().create({
                'name': name,
                'email': email,
                'phone': phone,
                'customer_rank': 1,
            })

            # Map external ID
            request.env['customer.id.mapping'].sudo().create({
                'external_customer_id': external_id,
                'partner_id': partner.id
            })

            return {
                'status': 'success',
                'message': 'Customer created',
                'partner_id': partner.id
            }

        except Exception as e:
            _logger.error("Customer creation error: %s", str(e))
            return {
                "status": "error",
                "message": str(e)
            }

    @http.route('/external_sales/create_product', type='json', auth='public', csrf=False, methods=['POST'])
    def create_product(self, **kwargs):
        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response
        try:
            data = kwargs
            _logger.info("Received product creation request: %s", data)

            external_product_id = data.get('external_product_id')
            name = data.get('name')
            list_price = data.get('list_price')
            default_code = data.get('default_code')
            tax_id = data.get('tax_id')
            discount = data.get('discount')

            if not all([external_product_id, name, list_price, default_code]):
                return {
                    'status': 'error',
                    'message': 'Missing required fields: external_product_id, name, list_price, default_code'
                }

            # Check if product already exists
            mapping = request.env['product.id.mapping'].sudo().search(
                [('external_product_id', '=', external_product_id)], limit=1)
            if mapping:
                return {
                    'status': 'exists',
                    'message': f'Product already exists with ID: {mapping.product_id.id}'
                }

            # Create product
            product_vals = {
                'name': name,
                'list_price': list_price,
                'default_code': default_code,
                'taxes_id': [(6, 0, [tax_id])] if tax_id else [],
                'description_sale': f"External Product - Discount {discount}%" if discount else ''
            }
            product = request.env['product.product'].sudo().create(product_vals)

            # Map external product ID
            request.env['product.id.mapping'].sudo().create({
                'external_product_id': external_product_id,
                'product_id': product.id
            })

            return {
                'status': 'success',
                'product_id': product.id,
                'message': 'Product created successfully'
            }

        except Exception as e:
            _logger.exception("Error creating product")
            return {
                'status': 'error',
                'message': str(e)
            }