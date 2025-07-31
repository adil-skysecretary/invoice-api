from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    external_invoice_id = fields.Char(
        string="External Invoice ID",
        compute="_compute_external_invoice_id",
        store=True
    )

    def _compute_external_invoice_id(self):
        for move in self:
            mapping = self.env['invoice.id.mapping'].search([
                ('invoice_id', '=', move.id)
            ], limit=1)
            move.external_invoice_id = mapping.external_id if mapping else False