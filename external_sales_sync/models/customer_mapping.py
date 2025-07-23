from odoo import models, fields

class CustomerIDMapping(models.Model):
    _name = 'customer.id.mapping'
    _description = 'Map 3rd-Party Customer ID to Odoo Customer'
    _sql_constraints = [
        ('external_customer_id_unique', 'unique(external_customer_id)', 'External Customer ID must be unique.')
    ]

    external_customer_id = fields.Char(required=True, unique=True)
    partner_id = fields.Many2one('res.partner', required=True)
