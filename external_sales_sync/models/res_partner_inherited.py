from odoo import models,fields


class ResPartnerInherited(models.Model):
    _inherit = 'res.partner'

    external_customer_id = fields.Char(
        string="External Customer ID",
        compute="_compute_external_customer_id",
        store=False
    )

    def _compute_external_customer_id(self):
        for customer in self:
            mapping = self.env['customer.id.mapping'].search([('partner_id', '=', customer.id)], limit=1)
            customer.external_customer_id = mapping.external_customer_id if mapping else False

