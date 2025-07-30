{
    "name": "External Sales Sync",
    "version": "1.0",
    "summary": "Integrate external sales to Odoo with product and customer ID mapping",
    "category": "Sales",
    "author": "ChatGPT",
    "depends": ["sale", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/mapping_views.xml",
        "views/product_template_view.xml",
        "views/res_partner_view.xml",
        "views/account_move_inherited_view.xml",
        "views/tax_id_mapping_views.xml",
        "views/skypos_api_menu.xml"
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False
}
