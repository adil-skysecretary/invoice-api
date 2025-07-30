from odoo import models, fields

class InvoiceIDMapping(models.Model):
    _name = 'invoice.id.mapping'
    _description = 'Map External Invoice ID to Odoo Invoice'
    _sql_constraints = [
        ('external_id_unique', 'unique(external_id)', 'External Invoice ID must be unique!')
    ]

    external_id = fields.Char(required=True, unique=True)
    invoice_id = fields.Many2one('account.move', required=True, ondelete='cascade')
