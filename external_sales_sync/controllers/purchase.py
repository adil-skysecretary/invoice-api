from odoo import http,fields
from odoo.http import request,Response
import json
import logging


_logger = logging.getLogger(__name__)

class PurchaseAPIController(http.Controller):


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

    @http.route('/api/purchase/create', type='json', auth='public', methods=['POST'], csrf=False)
    def create_purchase(self, **kwargs):
        is_auth, error_response = self._authenticate_request()
        if not is_auth:
            return error_response

        try:
            data = kwargs
            _logger.info("Received Purchase Data: %s", data)

            external_purchase_id = data.get('external_purchase_id')
            if external_purchase_id:
                existing_map = request.env['purchase.id.mapping'].sudo().search([
                    ('external_id', '=', external_purchase_id)
                ], limit=1)
                if existing_map:
                    return {
                        "status": "Purchase Already Exists",
                        "purchase_id": existing_map.purchase_id.id
                    }

            vendor_id = None
            external_vendor_id = data.get('external_vendor_id')
            if external_vendor_id:
                vendor_map = request.env['res.partner'].sudo().search([
                    ('external_vendor_id', '=', external_vendor_id)
                ], limit=1)
                if vendor_map:
                    vendor_id = vendor_map.id
                else:
                    vendor = request.env['res.partner'].sudo().create({
                        'name': data.get('vendor_name', 'Unknown Vendor'),
                        'external_vendor_id': external_vendor_id,
                        'supplier_rank': 1,
                    })
                    vendor_id = vendor.id
            else:
                return {'error': 'Missing external_vendor_id'}
            #
            order_lines = []
            for line in data.get('order_lines', []):
                product = request.env['product.product'].sudo().search([
                    ('external_product_id', '=', line.get('external_product_id'))
                ], limit=1)

                if not product:
                    product = request.env['product.product'].sudo().create({
                        'name': line.get('product_name', 'Unknown Product'),
                        'external_product_id': line.get('external_product_id'),
                        'purchase_ok': True,
                    })

                taxes = []
                external_tax_id = line.get('tax_id')
                if external_tax_id:
                    tax_map = request.env['tax.id.mapping'].sudo().search([
                        ('external_tax_id', '=', str(external_tax_id))
                    ], limit=1)
                    if tax_map:
                        taxes.append(tax_map.tax_id.id)

                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_qty': line.get('quantity', 1),
                    'price_unit': line.get('price_unit', 0),
                    'taxes_id': [(6, 0, taxes)],
                    'name': product.name,
                    'date_planned': fields.Datetime.now(),
                }))

            purchase_order = request.env['purchase.order'].sudo().create({
                'partner_id': vendor_id,
                'order_line': order_lines,
            })
            #
            # Store mapping
            request.env['purchase.id.mapping'].sudo().create({
                'external_id': external_purchase_id,
                'purchase_id': purchase_order.id
            })

            return {
                "status": "Purchase Created",
                "purchase_id": purchase_order.id
            }

        except Exception as e:
            _logger.error("Error in Purchase API: %s", str(e))
            return {'error': str(e)}
