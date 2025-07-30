from odoo import models, fields, api

class ProductProduct(models.Model):
    _inherit = 'product.template'

    external_product_id = fields.Char(
        string="SkyPOS External ID",
        compute="_compute_external_product_id",
        store=False
    )

    def _compute_external_product_id(self):
        for product in self:
            mapping = self.env['product.id.mapping'].search([('product_id', '=', product.id)], limit=1)
            product.external_product_id = mapping.external_product_id if mapping else False
