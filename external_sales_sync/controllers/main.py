from odoo import http,fields
from odoo.http import request, Response
import json
import logging
from datetime import datetime
# Then use datetime.now()
_logger = logging.getLogger(__name__)

class ExternalSalesSyncController(http.Controller):

    # token authentication ,this step is used to validate the token when access the api link
    def _authenticate_request(self):
        # take the authorization from the header what pass through the api
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False, Response(json.dumps({'error': 'Missing or invalid token'}), status=401,
                                   content_type='application/json')

        token = auth_header.split('Bearer ')[1].strip()

        # Check the token passes through the header and stored token in our module

        key_obj = request.env['skypos.api.key'].sudo().search([
            ('api_key', '=', token),
            ('active', '=', True)
        ], limit=1)

        if not key_obj:
            return False, Response(json.dumps({'error': 'Unauthorized'}), status=401, content_type='application/json')

        return True, None


    @http.route('/api/sales/create', type='json', auth='public', methods=['POST'], csrf=False)
    def create_sale(self, **kwargs):

        """ This function is used to create a new sale order and the passes value in api is true in the case of
        invoice then it create invoice after sale order created.and also if we pass the payment details then its mark
        paid or partial.in between it crete customer and products if it not in customer mapping and product mapping """

        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response

        try:
            # 'kwargs' contains parsed JSON body from "params"
            data = kwargs
            _logger.info("Received data: %s", data)

            external_invoice_id = data.get('external_invoice_id')
            if external_invoice_id:
                existing_map = request.env['invoice.id.mapping'].sudo().search([
                    ('external_id', '=', external_invoice_id)
                ], limit=1)
                if existing_map:
                    invoice = existing_map.invoice_id
                    return {
                        "status": "Invoice Already Exists",
                        "invoice_id": invoice.id
                    }
            ext_cust_id = data.get('external_customer_id')
            customer_name = data.get('customer_name', 'New Customer')
            items = data.get('order_lines', [])
            post_invoice = data.get('invoice', False)
            payment_info = data.get('payment', {})

            cust_map = request.env['customer.id.mapping'].sudo().search([('external_customer_id', '=', ext_cust_id)],
                                                                        limit=1)
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
                tax_ids = []
                external_tax_id = item.get('tax_id')
                if external_tax_id is not None:
                    tax_map = request.env['tax.id.mapping'].sudo().search([
                        ('external_tax_id', '=', external_tax_id)
                    ], limit=1)

                    if tax_map:
                        tax_ids = [(6, 0, [tax_map.tax_id.id])]

                order_lines.append((0, 0, {
                    'product_id': prod_map.product_id.id,
                    'product_uom_qty': item.get('quantity', 1),
                    'price_unit': item.get('price_unit', prod_map.product_id.lst_price),
                    'discount': item.get('discount', 0),
                    'tax_id': tax_ids,

                }))
            # create sale order
            order = request.env['sale.order'].sudo().create({
                'partner_id': cust_map.partner_id.id,
                'order_line': order_lines
            })
            # confirm the sale order
            order.action_confirm()

            # if invoice is true is in api pass
            if post_invoice:
                invoice = order._create_invoices()
                invoice.action_post()

                if external_invoice_id:
                    # Save to mapping model
                    request.env['invoice.id.mapping'].sudo().create({
                        'external_id': external_invoice_id,
                        'invoice_id': invoice.id
                    })

                payment_data = data.get('payment', {})
                amount = payment_data.get('amount')

                if amount and amount > 0:
                    journal_name = payment_data.get('journal_name')
                    payment_method_name = payment_data.get('payment_method_name')

                    journal = request.env['account.journal'].sudo().search([('name', '=', journal_name)], limit=1)
                    if not journal:
                        return Response(json.dumps({'error': f'Journal "{journal_name}" not found'}), status=400,
                                        content_type='application/json')

                    payment_method = request.env['account.payment.method'].sudo().search([
                        ('name', '=', payment_method_name),
                        ('payment_type', '=', 'inbound')
                    ], limit=1)
                    if not payment_method:
                        return Response(json.dumps({'error': f'Payment Method "{payment_method_name}" not found'}),
                                        status=400, content_type='application/json')

                    payment_date = payment_data.get('payment_date')
                    memo = invoice.name

                    PaymentRegister = request.env['account.payment.register'].sudo().with_context(
                        active_model='account.move', active_ids=invoice.ids)

                    payment_register = PaymentRegister.create({
                        'journal_id': journal.id,
                        'amount': amount,
                        'payment_date': payment_date,
                        'communication': memo
                    })

                    payment_result = payment_register.action_create_payments()

                    return {
                        "status": "Invoice and Payment Created and Reconciled",
                        "invoice_id": invoice.id,
                        "payment_result": payment_result  # usually returns a redirect to payment form
                    }

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
            phone = data.get('phone')

            # Validate input
            required_fields = ['external_customer_id', 'name', 'phone']
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
            standard_price = data.get('standard_price')

            if not all([external_product_id, name, list_price, default_code,standard_price]):
                return {
                    'status': 'error',
                    'message': 'Missing required fields: external_product_id, name, list_price, default_code, standard_price'
                }

            # Check if product already exists
            mapping = request.env['product.id.mapping'].sudo().search(
                [('external_product_id', '=', external_product_id)], limit=1)
            if mapping:
                return {
                    'status': 'exists',
                    'message': f'Product already exists with ID: {mapping.product_id.id}'
                }
            tax_ids = []
            external_tax_id = data.get('tax_id')
            if external_tax_id is not None:
                tax_map = request.env['tax.id.mapping'].sudo().search([
                    ('external_tax_id', '=', external_tax_id)
                ], limit=1)

                if tax_map:
                    tax_ids = [(6, 0, [tax_map.tax_id.id])]
            # Create product
            product_vals = {
                'name': name,
                'list_price': list_price,
                'default_code': default_code,
                'taxes_id': tax_ids,
                'standard_price': standard_price,
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

    @http.route('/api/payment/register', type='json', auth='public', methods=['POST'], csrf=False)
    def register_payment(self, **kwargs):
        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response

        try:
            data = kwargs
            external_invoice_id = data.get('external_invoice_id')
            amount = data.get('amount')

            if not external_invoice_id or not amount:
                return {"error": "Missing invoice ID or amount"}

            invoice = request.env['account.move'].sudo().search([
                ('external_invoice_id', '=', external_invoice_id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted')
            ], limit=1)

            if not invoice:
                return {"error": f"Invoice with external ID {external_invoice_id} not found or not posted"}

            if invoice.payment_state == 'paid':
                return {"status": "Already Paid", "invoice_id": invoice.id}

            journal_name = data.get('journal_name')
            journal = request.env['account.journal'].sudo().search([('name', '=', journal_name)], limit=1)
            if not journal:
                return {"error": f"Journal '{journal_name}' not found"}

            payment_date = data.get('payment_date') or fields.Date.today().isoformat()
            memo = invoice.name

            PaymentRegister = request.env['account.payment.register'].sudo().with_context(
                active_model='account.move', active_ids=invoice.ids)

            payment_register = PaymentRegister.create({
                'journal_id': journal.id,
                'amount': amount,
                'payment_date': payment_date,
            })

            payment_result = payment_register.action_create_payments()

            return {
                "status": "Payment Applied",
                "invoice_id": invoice.id,
                "payment_id": payment_result.get('res_id'),
                "payment_state": invoice.payment_state
            }

        except Exception as e:
            return {
                "error": str(e),
                "message": "Payment failed"
            }




