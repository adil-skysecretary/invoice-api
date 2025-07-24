from odoo import models, fields, api
import secrets

class SkyPosAPIKey(models.Model):
    _name = 'skypos.api.key'
    _description = 'API Key for SkyPOS Integration'

    name = fields.Char('Key Name', required=True)
    api_key = fields.Char('API Key', required=True, readonly=True, copy=False, default=lambda self: self._generate_api_key())
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Linked Customer', help="Who this key belongs to")

    def _generate_api_key(self):
        return 'skypos_' + secrets.token_urlsafe(32)