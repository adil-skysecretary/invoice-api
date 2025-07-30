from odoo import models, fields


class TaxIDMapping(models.Model):
    _name = 'tax.id.mapping'
    _description = 'Map External Tax ID to Odoo Tax'

    external_tax_id = fields.Integer(required=True, index=True)
    tax_id = fields.Many2one('account.tax', string="Odoo Tax", required=True)
