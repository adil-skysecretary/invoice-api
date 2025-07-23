from odoo import models, fields

class ProductIDMapping(models.Model):
    _name = 'product.id.mapping'
    _description = 'Map 3rd-Party Product ID to Odoo Product'

    external_product_id = fields.Char(required=True, unique=True)
    product_id = fields.Many2one('product.product', required=True)
