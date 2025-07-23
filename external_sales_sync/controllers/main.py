from odoo import http
from odoo.http import request, Response
import json
import logging
_logger = logging.getLogger(__name__)

class ExternalSalesSyncController(http.Controller):

    api_token = 'Abc123'
    @http.route('/api/sales/create', type='json', auth='public', methods=['POST'], csrf=False)
    def create_sale(self, **kwargs):
        token = request.httprequest.headers.get('x-api-key')
        if token != self.api_token:
            return Response(json.dumps({'error': 'Unauthorized'}), status=401, content_type='application/json')

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


