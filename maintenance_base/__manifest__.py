# -*- coding: utf-8 -*-
# Part of Cotyl.net. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Maintenance base',
    'version' : '0.1',
    'summary': 'Manage maintenance installations, elements, and interventions',
    'sequence': 30,
    'description': """

    """,
    'category': 'Maintenance',
    'website': 'https://www.cotyl.net',
    'images' : [''],
    'depends' : ['base','sale'],
    'data': [
            'data/maintenance_base_data.xml', 
            'views/maintenance_base_view.xml', 
            'report/maintenance_base_report.xml', 
            'report/maintenance_base_report_template.xml'
    ],
    'demo': [
    ],
    'qweb': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
