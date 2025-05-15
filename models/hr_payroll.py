# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.release import version_info
import logging
import datetime
import time
import dateutil.parser
from dateutil.relativedelta import relativedelta
from dateutil import relativedelta as rdelta
from odoo.fields import Date, Datetime
from calendar import monthrange
from odoo.addons.l10n_gt_extra import a_letras
from odoo.exceptions import ValidationError

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    porcentaje_prestamo = fields.Float(related="payslip_run_id.porcentaje_prestamo",string='Prestamo (%)',store=True)
    etiqueta_empleado_ids = fields.Many2many('hr.employee.category',string='Etiqueta empleado', related='employee_id.category_ids')
    cuenta_analitica_id = fields.Many2one('account.analytic.account','Cuenta analítica')

    # Dias trabajdas de los ultimos 12 meses hasta la fecha
    def dias_trabajados_ultimos_meses(self,empleado_id,fecha_desde,fecha_hasta):
        dias = {'days': 0}
        if empleado_id.contract_id.date_start:
            diferencia_meses = (fecha_hasta - fecha_desde)
            if empleado_id.contract_id.date_start <= fecha_hasta and empleado_id.contract_id.date_start >= fecha_desde:
                diferencia_meses = fecha_hasta - empleado_id.contract_id.date_start
        return diferencia_meses.days + 1

    def existe_entrada(self,entrada_ids,entrada_id):
        existe_entrada = False
        for entrada in entrada_ids:
            if entrada.input_type_id.id == entrada_id.id:
                existe_entrada = True
        return existe_entrada

    def compute_sheet(self):
        for nomina in self:
            mes_nomina = int(nomina.date_from.month)
            dia_nomina = int(nomina.date_to.day)
            anio_nomina = int(nomina.date_from.year)
            for entrada in nomina.input_line_ids:
                valor_entrada = 0
                for prestamo in nomina.employee_id.prestamo_ids:
                    anio_prestamo = int(prestamo.fecha_inicio.year)
                    if (prestamo.codigo == entrada.input_type_id.code) and ((prestamo.estado == 'nuevo') or (prestamo.estado == 'proceso')):
                        lista = []
                        for lineas in prestamo.prestamo_ids:
                            if mes_nomina == int(lineas.mes) and anio_nomina == int(lineas.anio):
                                lista = lineas.nomina_id.ids
                                lista.append(nomina.id)
                                lineas.nomina_id = [(6, 0, lista)]
                                valor_pago = lineas.monto
                                valor_entrada +=(valor_pago * (nomina.porcentaje_prestamo/100))
                                entrada.amount = valor_entrada
                        cantidad_pagos = prestamo.numero_descuentos
                        cantidad_pagados = 0
                        for lineas in prestamo.prestamo_ids:
                            if lineas.nomina_id:
                                cantidad_pagados +=1
                        if cantidad_pagados > 0 and cantidad_pagados < cantidad_pagos:
                            prestamo.estado = "proceso"

                        if prestamo.pendiente_pagar_prestamo == 0:
                            prestamo.estado = "pagado"
        res =  super(HrPayslip, self).compute_sheet()
        return res

    def calculo_rrhh(self,nomina):
        salario = self.salario_promedio(self.employee_id,self.date_to)
        dias = self.dias_trabajados_ultimos_meses(self.contract_id.employee_id,self.date_from,self.date_to)
        for entrada in self.input_line_ids:
            if entrada.input_type_id.code == 'SalarioPromedio':
                entrada.amount = salario
            if entrada.input_type_id.code == 'DiasTrabajados12Meses':
                entrada.amount = dias
            dias_calendario = monthrange(self.date_to.year, self.date_to.month)[1]
            if entrada.input_type_id.code == 'DiasCalendario':
                entrada.amount = dias_calendario
        return True

    # SALARIO PROMEDIO POR 12 MESES LABORADOS O MENOS
    def salario_promedio(self,empleado_id,fecha_final_nomina):
        historial_salario = []
        salario_meses = {}
        salario_total = 0
        salario_promedio_total = 0
        extra_ordinario_total = 0
        salario_completo = {}
        salario_sumatoria = 0
        if empleado_id.contract_ids[0].historial_salario_ids:
            posicion_historial = 0
            for linea in empleado_id.contract_ids[0].historial_salario_ids:
                if (posicion_historial+1) <= len(empleado_id.contract_ids[0].historial_salario_ids):
                    historial_salario.append({'salario': linea.salario, 'fecha':linea.fecha})
                    contador_mes_historial = 0

                    llave_salario = '01-'+str(linea.fecha.month)+'-'+str(linea.fecha.year)
                    llave_salario_fecha = datetime.datetime.strptime(str(llave_salario),'%d-%m-%Y').date()
                    llave_salario_fecha_str = '01-'+str(llave_salario_fecha.month)+'-'+str(llave_salario_fecha.year)
                    # index = empleado_id.contract_ids[0].historial_salario_ids.index(linea)
                    if posicion_historial+1 >= len(empleado_id.contract_ids[0].historial_salario_ids):
                        while llave_salario_fecha < fecha_final_nomina:
                            salario_completo[str(llave_salario_fecha_str)] = linea.salario
                            mes = relativedelta(months=1)
                            llave_salario_fecha = llave_salario_fecha + mes
                            llave_salario_fecha_str = '01-'+str(llave_salario_fecha.month)+'-'+str(llave_salario_fecha.year)
                            contador_mes_historial += 1

                        posicion_historial += 1
                    else:
                        while llave_salario_fecha < empleado_id.contract_ids[0].historial_salario_ids[posicion_historial+1].fecha:
                            salario_completo[str(llave_salario_fecha_str)] = linea.salario
                            mes = relativedelta(months=1)
                            llave_salario_fecha = llave_salario_fecha + mes
                            llave_salario_fecha_str = '01-'+str(llave_salario_fecha.month)+'-'+str(llave_salario_fecha.year)
                            contador_mes_historial += 1

                        posicion_historial += 1

            # historial_salario_ordenado = sorted(historial_salario, key=lambda k: k['fecha'],reverse=True)
            fecha_inicio_contrato = datetime.datetime.strptime(str(empleado_id.contract_ids[0].date_start),"%Y-%m-%d")
            fecha_final_contrato = datetime.datetime.strptime(str(fecha_final_nomina),"%Y-%m-%d")
            meses_laborados = (fecha_final_contrato.year - fecha_inicio_contrato.year) * 12 + (fecha_final_contrato.month - fecha_inicio_contrato.month)

            contador_mes = 0
            if meses_laborados >= 12:
                while contador_mes < 12:
                    mes = relativedelta(months=contador_mes)
                    resta_mes = fecha_final_contrato - mes
                    mes_letras = a_letras.mes_a_letras(resta_mes.month-1)
                    llave = '01-'+str(resta_mes.month)+'-'+str(resta_mes.year)
                    # llave_fecha = datetime.datetime.strptime(str(llave),'%Y-%m-%d')
                    salario = 0
                    if llave in salario_completo:
                        salario = salario_completo[llave]
                    salario_meses[llave] = {'nombre':mes_letras.upper(),'salario': salario,'anio':resta_mes.year,'extra':0,'total':0}
                    contador_mes += 1
                    salario_sumatoria += salario
            else:
                while contador_mes <= meses_laborados:
                    mes = relativedelta(months=contador_mes)
                    resta_mes = fecha_final_contrato - mes
                    mes_letras = a_letras.mes_a_letras(resta_mes.month-1)
                    llave = '01-'+str(resta_mes.month)+'-'+str(resta_mes.year)
                    salario = 0
                    if llave in salario_completo:
                        salario = salario_completo[llave]

                    salario_meses[llave] = {'nombre':mes_letras.upper(),'salario': salario,'anio':resta_mes.year,'extra':0,'total':0}
                    salario_sumatoria += salario
                    contador_mes += 1

            salario_promedio_total =  salario_sumatoria / len(salario_meses)
        else:
            salario_promedio_total = empleado_id.contract_ids[0].wage
        return salario_promedio_total

    def horas_sumar(self,lineas):
        horas = 0
        dias = 0
        for linea in lineas:
            tipo_id = self.env['hr.work.entry.type'].search([('id','=',linea['work_entry_type_id'])])
            if tipo_id and tipo_id.is_leave and tipo_id.descontar_nomina == False:
                horas += linea['number_of_hours']
                dias += linea['number_of_days']
        return {'dias':dias, 'horas': horas}

    def _get_worked_day_lines(self):
        res = super(HrPayslip, self)._get_worked_day_lines()
        tipos_ausencias_ids = self.env['hr.leave.type'].search([])
        datos = self.horas_sumar(res)
        ausencias_restar = []

        dias_ausentados_restar = 0
        contracts = False
        if self.employee_id.contract_id:
            contracts = self.employee_id.contract_id

        for ausencia in tipos_ausencias_ids:
            if ausencia.work_entry_type_id and ausencia.work_entry_type_id.descontar_nomina:
                ausencias_restar.append(ausencia.work_entry_type_id.id)

        trabajo_id = self.env['hr.work.entry.type'].search([('code','=','TRABAJO100')])
        for r in res:
            tipo_id = self.env['hr.work.entry.type'].search([('id','=',r['work_entry_type_id'])])
            if tipo_id and tipo_id.is_leave == False:
                r['number_of_hours'] += datos['horas']
                r['number_of_days'] += datos['dias']

            if len(ausencias_restar)>0:
                if r['work_entry_type_id'] in ausencias_restar:
                    dias_ausentados_restar += r['number_of_days']

        if contracts:
            dias_laborados = 0
            if contracts.schedule_pay == 'monthly':
                dias_laborados = 30
            if contracts.schedule_pay == 'bi-monthly':
                dias_laborados = 15


            if version_info[0] == 15 or version_info[0] == 16:
                if contracts.schedule_pay == 'monthly' or contracts.structure_type_id.default_schedule_pay == 'monthly':
                    dias_laborados = 30
                if contracts.schedule_pay == 'bi-weekly' or contracts.structure_type_id.default_schedule_pay == 'bi-weekly':
                    dias_laborados = 15

                reference_calendar = self._get_out_of_contract_calendar()
                dias_bonificacion = reference_calendar.get_work_duration_data(Datetime.from_string(self.date_from), Datetime.from_string(self.date_to), compute_leaves=False,domain = False)

                if contracts.date_start and dias_bonificacion['days'] <= 31 and self.date_from <= contracts.date_start <= self.date_to:
                    dias_laborados = dias_laborados - ((contracts.date_start - self.date_from ).days)

                    #Cuando es una planilla mensual, y el empleado entra y sale el mismo mes
                    if contracts.date_end and (self.date_from <= contracts.date_end <= self.date_to):
                        dias_laborados = ((contracts.date_end - contracts.date_start).days) +1 
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_laborados - dias_ausentados_restar})
                elif contracts.date_end and dias_bonificacion['days'] <= 31 and self.date_from <= contracts.date_end <= self.date_to:
                    dias_laborados =  ((contracts.date_end - self.date_from ).days) +1
                    #Cuando el contrato finaliza dentro del rango en el que se genera la planilla, es necesario verificar si el pago es quincenal o mensual
                    #por que necesitamos parametrizar que los dias trabajados no sea mayor que a los días dentro del rango de la planilla
                    if contracts.schedule_pay == 'bi-weekly':
                        res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': min(dias_laborados,15) - dias_ausentados_restar})
                    else:
                        res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': min(dias_laborados,30) - dias_ausentados_restar})
                elif dias_bonificacion['days'] > 150 and self.date_from >= contracts.date_start:
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_bonificacion['days']+1})
                elif dias_bonificacion['days'] > 150 and self.date_from <= contracts.date_start <= self.date_to:
                    dias_bonificacion = reference_calendar.get_work_duration_data(Datetime.from_string(contracts.date_start), Datetime.from_string(self.date_to),compute_leaves=False,domain = False)
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_bonificacion['days']+1})
                else:
                    if self.struct_id.schedule_pay == 'monthly' or contracts.structure_type_id.default_schedule_pay == 'monthly':
                        total_dias = 30 - dias_ausentados_restar
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': 0 if total_dias < 0 else total_dias})
                    if self.struct_id.schedule_pay == 'bi-weekly' or contracts.structure_type_id.default_schedule_pay == 'bi-weekly':
                        total_dias =  15 - dias_ausentados_restar
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': 0 if total_dias < 0 else total_dias})
                    # Cálculo de días para catorcena
                    if self.struct_id.schedule_pay == 'weekly' or contracts.structure_type_id.default_schedule_pay == 'weekly':
                        dias_laborados = 14
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': (dias_laborados - dias_ausentados_restar)})

                self.calculo_rrhh(self)
            else:

                dias_bonificacion = self.employee_id._get_work_days_data_batch(Datetime.from_string(self.date_from), Datetime.from_string(self.date_to), calendar=contracts.resource_calendar_id)

                if contracts.date_start and dias_bonificacion['days'] <= 31 and self.date_from <= contracts.date_start <= self.date_to:
                    dias_laborados = dias_laborados - (contracts.date_start - self.date_from).days
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_laborados - dias_ausentados_restar})
                elif dias_bonificacion['days'] > 150 and self.date_from >= contracts.date_start :
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_bonificacion['days']+1})
                elif dias_bonificacion['days'] > 150 and self.date_from <= contracts.date_start <= self.date_to:
                    dias_bonificacion = self.employee_id._get_work_days_data_batch(Datetime.from_string(contracts.date_start), Datetime.from_string(self.date_to), calendar=contracts.resource_calendar_id)
                    res.append({'work_entry_type_id': trabajo_id.id, 'sequence': 10, 'number_of_days': dias_bonificacion['days']+1})
                else:
                    if contracts.schedule_pay == 'monthly':
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': 30 - dias_ausentados_restar})
                    if contracts.schedule_pay == 'bi-monthly':
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': 15 - dias_ausentados_restar})
                    # Cálculo de días para catorcena
                    if contracts.schedule_pay == 'bi-weekly':
                        dias_laborados = 14
                        res.append({'work_entry_type_id': trabajo_id.id,'sequence': 10,'number_of_days': (dias_laborados - dias_ausentados_restar)})
        return res

    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to', 'struct_id')
    def _compute_input_line_ids(self):
        res = super(HrPayslip, self)._compute_input_line_ids()
        for slip in self:
            if slip.employee_id and slip.struct_id and slip.struct_id.input_line_type_ids:

                if slip.contract_id and slip.contract_id.analytic_account_id:
                    slip.cuenta_analitica_id = slip.contract_id.analytic_account_id.id

                input_line_vals = []
                if slip.input_line_ids:
                    slip.input_line_ids.unlink()

                for line in slip.struct_id.input_line_type_ids:
                    input_line_vals.append((0,0,{
                        'name': line.name,
                        'amount': 0,
                        'input_type_id': line.id,
                    }))
                slip.update({'input_line_ids': input_line_vals})

                mes_nomina = slip.date_from.month
                anio_nomina = slip.date_from.year
                dia_nomina = slip.date_to.day
                entradas_nomina = []
                if slip.employee_id.prestamo_ids:
                    for prestamo in slip.employee_id.prestamo_ids:
                        anio_prestamo = int(prestamo.fecha_inicio.year)
                        for entrada in slip.input_line_ids:
                            if (prestamo.codigo == entrada.input_type_id.code) and ((prestamo.estado == 'nuevo') or (prestamo.estado == 'proceso')):
                                valor_entrada = entrada.amount
                                for lineas in prestamo.prestamo_ids:
                                    if mes_nomina == int(lineas.mes) and anio_nomina == int(lineas.anio):
                                        valor_entrada += lineas.monto*(slip.porcentaje_prestamo/100)
                                entrada.amount = valor_entrada
        return res

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super(models.Model, self).fields_view_get(view_id, view_type, toolbar, submenu)
        return res

    @api.model
    def get_views(self, views, options=None):
        res = super(models.Model, self).get_views(views, options)
        return res

    def action_payslip_cancel(self):
        for nomina in self:
            pago_id = self.env['account.payment'].search([('nomina_id','=',nomina.id),('state','=', 'posted')])
            if len(pago_id) > 0:
                raise ValidationError(_("No puede cancelar por que tiene un pago asociado"))
        return super(HrPayslip, self).action_payslip_cancel()

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    porcentaje_prestamo = fields.Float('Prestamo (%)')

    def generar_pagos(self):
        pagos = self.env['account.payment'].search([('nomina_id', '!=', False)])
        nominas_pagadas = []
        for pago in pagos:
            nominas_pagadas.append(pago.nomina_id.id)
        for nomina in self.slip_ids:
            if nomina.id not in nominas_pagadas:
                total_nomina = 0
                if nomina.employee_id.diario_pago_id and nomina.employee_id.address_home_id and nomina.state in ['done','close']:
                    res = self.env['report.rrhh.recibo'].lineas(nomina)
                    total_nomina = res['totales'][0] + res['totales'][1]
                    pago = {
                        'payment_type': 'outbound',
                        'partner_type': 'supplier',
                        'payment_method_id': 2,
                        'partner_id': nomina.employee_id.address_home_id.id,
                        'amount': total_nomina,
                        'journal_id': nomina.employee_id.diario_pago_id.id,
                        'nomina_id': nomina.id
                    }
                    pago_id = self.env['account.payment'].create(pago)
        return True
