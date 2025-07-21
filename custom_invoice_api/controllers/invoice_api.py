from odoo import http
from odoo.http import request
import json
import logging
import traceback

_logger = logging.getLogger(__name__)

class InvoiceAPIController(http.Controller):

    @http.route('/api/create_invoice', type='json', auth='public', methods=['POST'], csrf=False)
    def create_invoice(self, **data):
        try:
            _logger.info("Received invoice data: %s", data)

            required_fields = ['partner_phone', 'partner_name', 'product_name', 'price_unit', 'quantity']
            missing = [f for f in required_fields if not data.get(f)]
            if missing:
                return {
                    'status': 'error',
                    'message': f"Missing fields: {', '.join(missing)}"
                }

            # 1. Lookup or create partner
            Partner = request.env['res.partner'].sudo()
            partner = Partner.search([('phone', '=', data['partner_phone'])], limit=1)
            if not partner:
                partner = Partner.create({
                    'name': data['partner_name'],
                    'phone': data['partner_phone'],
                })

            # 2. Lookup or create product
            Product = request.env['product.product'].sudo()
            product = Product.search([('name', '=', data['product_name'])], limit=1)
            if not product:
                product = Product.create({
                    'name': data['product_name'],
                    'type': 'consu',  # 'consu' = consumable
                    'list_price': float(data['price_unit']),  # optional
                })

            # 3. Create invoice
            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': product.id,
                        'quantity': float(data['quantity']),
                        'price_unit': float(data['price_unit']),
                        'name': data.get('description', product.name),
                    })
                ]
            }

            invoice = request.env['account.move'].sudo().create(invoice_vals)
            invoice.action_post()

            return {
                'status': 'success',
                'invoice_id': invoice.id,
                'invoice_number': invoice.name
            }

        except Exception as e:
            tb = traceback.format_exc()
            _logger.error("Invoice creation error: %s\n%s", str(e), tb)
            return {
                'status': 'error',
                'message': str(e),
                'trace': tb
            }
