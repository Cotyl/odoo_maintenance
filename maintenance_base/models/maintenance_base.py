'''
Created on 25 oct. 2016

@author: clement
'''

from odoo import models, fields, api
from datetime import datetime, timedelta, time
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF
from odoo.exceptions import UserError
import pytz

class sale_order_line(models.Model):
    _inherit = 'sale.order.line'
    
    @api.multi
    def unlink(self):
        if self._context.get('force',False):
            return super(sale_order_line,self).unlink()

        sale_line_intervention_sale_done = self.filtered(lambda x: x.order_id.is_maintenance_intervention and x.state in ('sale', 'done'))
        for sale_line in sale_line_intervention_sale_done:
            sale_line.state = 'draft'
        sale_line_intervention_sale_done.with_context(force=True).unlink()
        
        sale_line_others = self.filtered(lambda x: not x.order_id.is_maintenance_intervention or x.state not in ('sale', 'done'))
        sale_line_others.with_context(force=True).unlink()
        return 0

class sale_order(models.Model):
    _inherit = 'sale.order'
    
    is_maintenance_intervention = fields.Boolean('Is intervention') #flag sales linked to interventions, to avoid displaying them
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if 'is_maintenance_intervention' not in [a[0] for a in args if type(a) is list]:
            args.append(('is_maintenance_intervention','=',False))
            
        return super(sale_order, self).search(args, offset=offset, limit=limit, order=order, count=count)
    
    @api.model
    @api.returns('self', lambda value:value.id)
    def create(self, vals):
        if self._context.get('copy_intervention',False):
            # when we copy sale order from intervention copy, 
            # order lines are automatically created from intervention lines.
            if 'order_line' in vals:
                del vals['order_line'] 
        res = super(sale_order,self).create(vals)
        return res

class maintenance_installation(models.Model):
    _name = 'maintenance.installation'
    
    code = fields.Char("Reference", required=True, size=255, help="The Maintenance Installation Code",default=lambda obj: obj.env['ir.sequence'].get('maintenance.installation'))
    name = fields.Char("Identification", size=255, help="A name for your installation understandable.")
    partner_id = fields.Many2one('res.partner', string='Customer',help="The partner linked to this maintenance installation", required=True)
    address_id = fields.Many2one('res.partner', string='Address', help="The address where the installation is located")
    contact_address_id = fields.Many2one('res.partner', string='Contact', domain=[('type','=','contact')],help="The contact person for this installation")
    elements = fields.One2many('maintenance.element', 'installation_id', "Elements",help="The elements contained in this installation")
    interventions = fields.One2many('maintenance.intervention', 'installation_id', "Interventions", help="The interventions linked to this installation")
    note=fields.Text('Notes')
    state = fields.Selection([('active', 'Active'), ('inactive','Inactive')], string="State", default="active", readonly=True,help="Inactive older installations.")
    
    @api.one
    def installation_active(self):
        self.state = 'active'
        
    @api.one
    def installation_inactive(self):
        self.state = 'inactive'
        
    @api.multi
    def name_get(self):
        res = []
        for installation in self:
            name = '['+installation.code+'] '
            if installation.name:
                name = name+installation.name+' '
            name = name+installation.partner_id.name
            res.append((installation.id, name))
        return res
    
    
class maintenance_element(models.Model):
    _name = 'maintenance.element'
    
    installation_id = fields.Many2one('maintenance.installation', 'Installation', index=True, required=True)
    name = fields.Char("Name", size=255) 
    serial_number = fields.Char(string="Serial number")
    description = fields.Text("Description")
    installation_date = fields.Date("Installation date")
    warranty_date = fields.Date("Warranty date")
    location = fields.Char("Location", size=255)
    state = fields.Selection([('active', 'Active'), ('inactive','Inactive')], string="State", help="Inactive older installations.", default="active")
    
   
    
class maintenance_intervention_type(models.Model):
    _name="maintenance.intervention.type"
    _description = 'Maintenance Intervention Type'
    
    name = fields.Char("Name", size=255, translate=True, required=True)
    color = fields.Integer('Color')
    workforce_product_id = fields.Many2one('product.product', string="Workforce product", required=True,help="Default workforce product for this kind of intervention")
    workforce_product_duration = fields.Float(string="Workforce product duration", required=True,help="Unit of time for workforce product")


class maintenance_intervention(models.Model):
    _name = 'maintenance.intervention'
    
    _inherits = {'sale.order': 'sale_id'}
    
    _order = 'id desc'
    
    @api.multi
    def action_draft(self):
        self.sale_id.action_draft()
        self.state = 'draft'
    
    @api.multi
    def action_cancel(self):
        self.sale_id.action_cancel()
        
        #Cancel all linked invoices
        invoices = set()
        for sale_line in self.sale_id.order_line:
            for invoice_line in sale_line.invoice_lines:
                invoices.add(invoice_line.invoice_id) 
        for invoice in invoices:
            invoice.action_cancel()
            
        self.state = 'cancel'
    
    @api.multi
    def action_confirm(self):
        self.sale_id.action_confirm()
        self.state = 'confirmed'
        
    @api.multi
    def action_done(self):
        #create invoice if lines to invoice exists
        if self.sale_id.order_line.filtered(lambda l:l.qty_to_invoice > 0):
            self.sale_id.action_invoice_create(final=True)
        self.state = 'done'
    
    @api.multi
    def print_intervention(self):
        return self.env['report'].get_action(self, 'maintenance_base.report_maintenance_intervention')
    
    @api.onchange('installation_id')
    def sync_partner_id(self):
        self.partner_id = self.installation_id.partner_id
    
    @api.multi
    def unlink(self):
        for intervention in self:
            intervention.sale_id.unlink()
        return super(maintenance_intervention,self).unlink()
    
    @api.multi
    def sync_state(self):
        for intervention in self:
            if intervention.state in ('confirmed','planned'):
                state = 'confirmed'
                for task in intervention.intervention_tasks:
                    if task.date_start:
                        state = 'planned'
                        break
                intervention.with_context(no_sync=True).state = state
                    
    
    @api.model
    @api.returns('self', lambda value:value.id)
    def create(self, vals):
        vals['partner_id'] = self.env['maintenance.installation'].browse(vals['installation_id']).partner_id.id
        vals['is_maintenance_intervention'] = True
        return super(maintenance_intervention,self).create(vals)
        
        
    
    @api.multi
    def write(self, vals):
        res = super(maintenance_intervention, self).write(vals)
        if not self._context.get('no_sync',False): #prevent loop
            self.sync_state()
        return res
    
    @api.multi
    def name_get(self):
        res = []
        for intervention in self:
            name = '['+intervention.code+'] '+intervention.installation_id.partner_id.name
            if intervention.installation_id.name:
                name = name + '('+intervention.installation_id.name+')'
            res.append((intervention.id, name))
        return res
    
    @api.multi
    @api.returns('self', lambda value:value.id)
    def copy(self, default=None):
        if not 'code' in default:
            default['code'] = self.env['ir.sequence'].get('maintenance.intervention')
        return super(maintenance_intervention,self.with_context(copy_intervention=True)).copy(default)
    
    code = fields.Char("Reference", size=255, required=True,default=lambda obj: obj.env['ir.sequence'].get('maintenance.intervention'))
    name = fields.Text("Description", index=True)
    installation_id = fields.Many2one('maintenance.installation', string='Installation', required=True) 
    intervention_type_id = fields.Many2one('maintenance.intervention.type', string='Type', required=True)
    state = fields.Selection([('draft','Draft'), ('confirmed', 'Confirmed'),('planned', 'Planned'), ('done', 'Done'), ('cancel','Cancel')], string="Intervention State", readonly=True,default='draft')
    intervention_tasks = fields.One2many('maintenance.intervention.task','intervention_id', 'Tasks', copy=True)
    intervention_lines = fields.One2many('maintenance.intervention.line','intervention_id', 'Products', copy=True)
    date_scheduled=fields.Date('Scheduled date')
    time_planned = fields.Float('Time planned', help='Time initially planned to do intervention.')
    internal_comment = fields.Text("Internal comment")
    external_comment = fields.Text("External comment") 
    contact_address_id = fields.Many2one('res.partner', string='Contact')
    
class maintenance_intervention_line(models.Model):
    _name = 'maintenance.intervention.line' 
    
    _inherits = {'sale.order.line': 'sale_line_id'}
    
    intervention_id = fields.Many2one('maintenance.intervention', string="Maintenance intervention", ondelete='cascade',index=True)
    maintenance_element_id = fields.Many2one('maintenance.element', string="Maintenance element",index=True) 
    
    @api.model
    def create(self, vals):
        vals['order_id'] = self.env['maintenance.intervention'].browse(vals['intervention_id']).sale_id.id
        return super(maintenance_intervention_line, self).create(vals)
    
    @api.multi
    def unlink(self):
        for intervention_line in self:
            intervention_line.sale_line_id.unlink()
        return super(maintenance_intervention_line,self).unlink()
    
    
class maintenance_intervention_task(models.Model):
    _name = 'maintenance.intervention.task'
    
    _inherits = {'sale.order.line': 'sale_line_id'}
    
    intervention_id = fields.Many2one("maintenance.intervention", "Intervention", ondelete='cascade',index=True)
    name = fields.Char('Task Summary', size=128)
    user_id = fields.Many2one('res.users', 'Assigned to')
    date_start = fields.Datetime('Starting Date',index=True,default=lambda self: self._get_default_date_start())
    date_end = fields.Datetime('Ending Date',index=True,default=lambda self: self._get_default_date_end())
    duration = fields.Float('Duration (h)', compute='get_duration', readonly=1)
    duration_str = fields.Text('Duration (h)', compute='get_duration_str', readonly=1)
    
    @api.model
    def _get_default_date_start(self):
        timezone_user = pytz.timezone(self._context.get('tz') or 'UTC')
        timezone_server = pytz.UTC
        start_date = timezone_user.localize(fields.Datetime.from_string(datetime.now().strftime('%Y-%m-%d 08:00:00'))) 
        return start_date.astimezone(timezone_server).strftime('%Y-%m-%d %H:%M:%S')
    
    @api.model
    def _get_default_date_end(self):
        timezone_user = pytz.timezone(self._context.get('tz') or 'UTC')
        timezone_server = pytz.UTC
        start_date = timezone_user.localize(fields.Datetime.from_string(datetime.now().strftime('%Y-%m-%d 10:00:00'))) 
        return start_date.astimezone(timezone_server).strftime('%Y-%m-%d %H:%M:%S')

    @api.multi
    def unlink(self):
        for intervention_task in self:
            intervention_task.sale_line_id.unlink()
        return super(maintenance_intervention_task,self).unlink()
    
    @api.multi
    def write(self, vals):
        #if date_start or date_end has changed, synchronize quantity of sale_order_line
        if 'date_start' in vals or 'date_end' in vals:
            for task in self:
                if 'date_start' in vals:
                    date_start = vals['date_start']
                else:
                    date_start = task.date_start
                    
                if 'date_end' in vals:
                    date_end = vals['date_end']
                else:
                    date_end = task.date_end
                    
                workforce_product_duration = task.intervention_id.intervention_type_id.workforce_product_duration
            vals['product_uom_qty'] = self.get_quantity_from_date(date_start, date_end, workforce_product_duration)
            res = super(maintenance_intervention_task,task).write(vals)
            
        return res

    @api.model
    def create(self, vals):
        intervention = self.env['maintenance.intervention'].browse(vals['intervention_id'])
        vals['order_id'] = intervention.sale_id.id
        vals['product_id'] = intervention.intervention_type_id.workforce_product_id.id
        vals['product_uom_qty'] = self.get_quantity_from_date(vals['date_start'], vals['date_end'], intervention.intervention_type_id.workforce_product_duration) 
        return super(maintenance_intervention_task, self).create(vals)
    
    @api.multi
    def get_duration(self):
        for task in self:
            task.duration = self.get_duration_from_date(task.date_start,task.date_end)
            
    @api.multi
    def get_duration_str(self):
        for task in self:   
            task.duration_str = str(timedelta(seconds=task.duration*3600))[:-3]
    
                
    def get_duration_from_date(self, date_start, date_end):
        if not date_start or not date_end:
            return 0
        date_start = datetime.strptime(date_start, DTF)
        date_end = datetime.strptime(date_end, DTF)
        return (date_end-date_start).seconds/3600.
    
    def get_quantity_from_date(self, date_start, date_end, workforce_product_duration):
        if not workforce_product_duration:
            return 0
        return self.get_duration_from_date(date_start, date_end) / workforce_product_duration
