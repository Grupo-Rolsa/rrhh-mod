# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
import time
import base64
from ..lib import xlsxwriter
import io
import logging

class rrhh_planilla_wizard(models.TransientModel):
    _name = 'rrhh.planilla.wizard'
    _description = 'Wizard de planilla'

    nomina_id = fields.Many2one('hr.payslip.run', 'Nomina', default=lambda self: self.env['hr.payslip.run'].browse(self._context.get('active_id')), required=True)
    planilla_id = fields.Many2one('rrhh.planilla', 'Planilla', required=True)
    archivo = fields.Binary('Archivo')
    name =  fields.Char('File Name', default='planilla.xlsx', size=32)
    agrupado  = fields.Boolean('Agrupado por cuenta analítica')

    def print_report(self):
        datas = {'ids': self.env.context.get('active_ids', [])}
        res = self.read([])
        res = res and res[0] or {}
        datas['form'] = res
        return self.env.ref('rrhh.action_planilla_pdf').with_context(landscape=True).report_action([], data=datas)

    def buscar_partida_nominas(self, slip_ids):
        cantidad_nominas_partida = 0
        partidas = {}
        for slip in slip_ids:
            if slip.move_id:
                if slip.id not in partidas:
                    partidas[slip.move_id.id] = 0
        return partidas

    def generar(self):
        for w in self:
            f = io.BytesIO()
            libro = xlsxwriter.Workbook(f)
            header_format = libro.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 8, 'border': 1})
            header_format.set_text_wrap()
            default_format = libro.add_format({'font_size': 8, 'border': 1})
            info_format = libro.add_format({'font_size': 8})
            number_format = libro.add_format({'num_format': '#,##0.00', 'font_size': 8, 'border': 1})
            formato_fecha = libro.add_format({'num_format': 'dd/mm/yy', 'font_size': 8, 'border': 1})
            if w.agrupado:
                # partidas_iguales, contiene un diccionario de todas las partidas de la nomina, en el caso de que unifiquen todas las nóminas
                # en una partida o en el caso que no, asi mas adelante podemos clasificar por cuenta analítica de la partida o por la cuenta analítica de la nómina
                partidas_iguales = self.buscar_partida_nominas(w.nomina_id.slip_ids)
                cuentas_analiticas = set([])
                for l in w.nomina_id.slip_ids:
                    if l.cuenta_analitica_id:
                        cuentas_analiticas.add(l.cuenta_analitica_id.name)
                    else:
                        if len(partidas_iguales) > 1:
                            if l.move_id and len(l.move_id.line_ids) > 0 and l.move_id.line_ids[0].analytic_account_id:
                                cuentas_analiticas.add(l.move_id.line_ids[0].analytic_account_id.name)
                            else:
                                cuentas_analiticas.add('Indefinido')
                        else:
                            cuentas_analiticas.add('Indefinido')
                for i in cuentas_analiticas:
                    hoja = libro.add_worksheet(i)

                    hoja.write(0, 0, 'Planilla')
                    hoja.write(0, 1, w.nomina_id.name)
                    hoja.write(0, 2, 'Periodo')
                    hoja.write(0, 3, w.nomina_id.date_start, formato_fecha)
                    hoja.write(0, 4, w.nomina_id.date_end, formato_fecha)

                    linea = 2
                    num = 1

                    hoja.write(linea, 0, 'No')
                    hoja.write(linea, 1, 'Cod. de empleado')
                    hoja.write(linea, 2, 'Nombre de empleado')
                    hoja.write(linea, 3, 'Fecha de ingreso')
                    hoja.write(linea, 4, 'Puesto')
                    hoja.write(linea, 5, 'Dias')

                    totales = []
                    columna = 6
                    for c in w.planilla_id.columna_id:
                        hoja.write(linea, columna, c.name)
                        columna += 1
                        totales.append(0)
                    totales.append(0)

                    hoja.write(linea, columna, 'Liquido a recibir')
                    hoja.write(linea, columna+1, 'Banco a depositar')
                    hoja.write(linea, columna+2, 'Cuenta a depositar')
                    hoja.write(linea, columna+3, 'Observaciones')
                    hoja.write(linea, columna+4, 'Cuenta analítica')
                    for l in w.nomina_id.slip_ids:
                        cuenta_analitica = False
                        if l.cuenta_analitica_id:
                            cuenta_analitica = l.cuenta_analitica_id.name
                        else:
                            if len(partidas_iguales) > 1:
                                if l.move_id and len(l.move_id.line_ids) > 0 and l.move_id.line_ids[0].analytic_account_id:
                                    cuenta_analitica = l.move_id.line_ids[0].analytic_account_id.name
                        if cuenta_analitica:
                            if cuenta_analitica == i:
                                linea += 1
                                dias = 0
                                total_salario = 0

                                hoja.write(linea, 0, num)
                                hoja.write(linea, 1, l.employee_id.codigo_empleado)
                                hoja.write(linea, 2, l.employee_id.name)
                                hoja.write(linea, 3, l.contract_id.date_start,formato_fecha)
                                hoja.write(linea, 4, l.employee_id.job_id.name)
                                work = -1
                                trabajo = -1
                                for d in l.worked_days_line_ids:
                                    if d.code == 'TRABAJO100':
                                        trabajo = d.number_of_days
                                    elif d.code == 'WORK100':
                                        work = d.number_of_days
                                if trabajo >= 0:
                                    dias += trabajo
                                else:
                                    dias += work
                                hoja.write(linea, 5, dias)

                                columna = 6
                                for c in w.planilla_id.columna_id:
                                    reglas = [x.id for x in c.regla_id]
                                    entradas = [x.name for x in c.entrada_id]
                                    total_columna = 0
                                    for r in l.line_ids:
                                        if r.salary_rule_id.id in reglas:
                                            total_columna += r.total
                                    for r in l.input_line_ids:
                                        if r.name in entradas:
                                            total_columna += r.amount
                                    if c.sumar:
                                        total_salario += total_columna
                                    totales[columna-6] += total_columna

                                    hoja.write(linea, columna, total_columna)
                                    columna += 1

                                totales[columna-6] += total_salario
                                hoja.write(linea, columna, total_salario)
                                hoja.write(linea, columna+1, l.employee_id.bank_account_id.bank_id.name)
                                hoja.write(linea, columna+2, l.employee_id.bank_account_id.acc_number)
                                hoja.write(linea, columna+3, l.note)
                                hoja.write(linea, columna+4, l.cuenta_analitica_id.name)

                                num += 1
                        else:
                            if cuenta_analitica == False and i == 'Indefinido':
                                linea += 1
                                dias = 0
                                total_salario = 0

                                hoja.write(linea, 0, num)
                                hoja.write(linea, 1, l.employee_id.codigo_empleado)
                                hoja.write(linea, 2, l.employee_id.name)
                                hoja.write(linea, 3, l.contract_id.date_start,formato_fecha)
                                hoja.write(linea, 4, l.employee_id.job_id.name)
                                work = -1
                                trabajo = -1
                                for d in l.worked_days_line_ids:
                                    if d.code == 'TRABAJO100':
                                        trabajo = d.number_of_days
                                    elif d.code == 'WORK100':
                                        work = d.number_of_days
                                if trabajo >= 0:
                                    dias += trabajo
                                else:
                                    dias += work
                                hoja.write(linea, 5, dias)

                                columna = 6
                                for c in w.planilla_id.columna_id:
                                    reglas = [x.id for x in c.regla_id]
                                    entradas = [x.name for x in c.entrada_id]
                                    total_columna = 0
                                    for r in l.line_ids:
                                        if r.salary_rule_id.id in reglas:
                                            total_columna += r.total
                                    for r in l.input_line_ids:
                                        if r.name in entradas:
                                            total_columna += r.amount
                                    if c.sumar:
                                        total_salario += total_columna
                                    totales[columna-6] += total_columna

                                    hoja.write(linea, columna, total_columna)
                                    columna += 1

                                totales[columna-6] += total_salario
                                hoja.write(linea, columna, total_salario)
                                hoja.write(linea, columna+1, l.employee_id.bank_account_id.bank_id.name)
                                hoja.write(linea, columna+2, l.employee_id.bank_account_id.acc_number)
                                hoja.write(linea, columna+3, l.note)
                                hoja.write(linea, columna+4, 'indefinido')

                                num += 1
                            if l.cuenta_analitica_id and l.cuenta_analitica_id.name == i:
                                linea += 1
                                dias = 0
                                total_salario = 0

                                hoja.write(linea, 0, num)
                                hoja.write(linea, 1, l.employee_id.codigo_empleado)
                                hoja.write(linea, 2, l.employee_id.name)
                                hoja.write(linea, 3, l.contract_id.date_start,formato_fecha)
                                hoja.write(linea, 4, l.employee_id.job_id.name)
                                work = -1
                                trabajo = -1
                                for d in l.worked_days_line_ids:
                                    if d.code == 'TRABAJO100':
                                        trabajo = d.number_of_days
                                    elif d.code == 'WORK100':
                                        work = d.number_of_days
                                if trabajo >= 0:
                                    dias += trabajo
                                else:
                                    dias += work
                                hoja.write(linea, 5, dias)

                                columna = 6
                                for c in w.planilla_id.columna_id:
                                    reglas = [x.id for x in c.regla_id]
                                    entradas = [x.name for x in c.entrada_id]
                                    total_columna = 0
                                    for r in l.line_ids:
                                        if r.salary_rule_id.id in reglas:
                                            total_columna += r.total
                                    for r in l.input_line_ids:
                                        if r.name in entradas:
                                            total_columna += r.amount
                                    if c.sumar:
                                        total_salario += total_columna
                                    totales[columna-6] += total_columna

                                    hoja.write(linea, columna, total_columna)
                                    columna += 1

                                totales[columna-6] += total_salario
                                hoja.write(linea, columna, total_salario)
                                hoja.write(linea, columna+1, l.employee_id.bank_account_id.bank_id.name)
                                hoja.write(linea, columna+2, l.employee_id.bank_account_id.acc_number)
                                hoja.write(linea, columna+3, l.note)
                                hoja.write(linea, columna+4, l.cuenta_analitica_id.name)

                                num += 1
                    columna = 6
                    for t in totales:
                        hoja.write(linea+1, columna, totales[columna-6])
                        columna += 1
            else:
                hoja = libro.add_worksheet('reporte')

                hoja.write(0, 0, 'Planilla', info_format)
                hoja.write(0, 1, w.nomina_id.name, info_format)
                hoja.write(0, 2, 'Periodo', info_format)
                hoja.write(0, 3, w.nomina_id.date_start, info_format)
                hoja.write(0, 4, w.nomina_id.date_end, info_format)

                linea = 3
                num = 1

                hoja.write(linea, 0, 'No', header_format)
                hoja.write(linea, 1, 'Celular', header_format)
                hoja.write(linea, 2, 'Cod. de empleado', header_format)
                hoja.write(linea, 3, 'Nombre de empleado', header_format)
                hoja.write(linea, 4, 'NSS', header_format)
                hoja.write(linea, 5, 'Puesto', header_format)
                hoja.write(linea, 6, 'Fecha alta', header_format)
                hoja.write(linea, 7, 'Fecha baja', header_format)
                hoja.write(linea, 8, 'Dias', header_format)

                totales = []
                columna_pd = 9
                columna = columna_pd

                columnas_percepcion = w.planilla_id.columna_id.filtered(lambda x: x.es_descuento == False)
                columnas_descuento = w.planilla_id.columna_id.filtered(lambda x: x.es_descuento == True)

                # Percepciones
                if len(columnas_percepcion) > 0:
                    perc_range = (columna, columna + len(columnas_percepcion) - 1)
                    hoja.merge_range(
                        2, perc_range[0], 2, perc_range[1],
                        'Percepciones', 
                        header_format
                    )
                    for c in columnas_percepcion:
                        hoja.write(linea, columna, c.name, header_format)
                        columna += 1
                        totales.append(0)
                    # totales.append(0)

                # Descuentos
                if len(columnas_descuento) > 0:
                    desc_range = (columna, columna + len(columnas_descuento) - 1)
                    hoja.merge_range(
                        2, desc_range[0], 2, desc_range[1],
                        'Descuentos', 
                        header_format
                    )
                    for c in columnas_descuento:
                        hoja.write(linea, columna, c.name, header_format)
                        columna += 1
                        totales.append(0)
                    totales.append(0)

                hoja.write(linea, columna, 'Liquido', header_format)
                hoja.write(linea, columna+1, 'Cédula', header_format)
                hoja.write(linea, columna+2, 'CECO', header_format)
                hoja.set_column(columna+1, columna+2, 10)

                linea += 1
                for l in w.nomina_id.slip_ids:
                    dias = 0
                    total_salario = 0

                    hoja.write(linea, 0, num, default_format)
                    hoja.write(linea, 1, l.employee_id.mobile_phone, default_format)
                    hoja.write(linea, 2, l.employee_id.codigo_empleado, default_format)
                    hoja.write(linea, 3, l.employee_id.name, default_format)
                    hoja.write(linea, 4, l.employee_id.igss, default_format)
                    hoja.write(linea, 5, l.employee_id.job_id.name, default_format)
                    hoja.write(linea, 6, l.contract_id.date_start,formato_fecha)
                    hoja.write(linea, 7, l.contract_id.date_end,formato_fecha)
                    work = -1
                    trabajo = -1
                    for d in l.worked_days_line_ids:
                        if d.code == 'TRABAJO100':
                            trabajo = d.number_of_days
                        elif d.code == 'WORK100':
                            work = d.number_of_days
                    if trabajo >= 0:
                        dias += trabajo
                    else:
                        dias += work
                    hoja.write(linea, 8, dias, default_format)

                    columna = columna_pd

                    if len(columnas_percepcion) > 0:
                        for c in columnas_percepcion:
                            reglas = [x.id for x in c.regla_id]
                            entradas = [x.name for x in c.entrada_id]
                            total_columna = 0
                            for r in l.line_ids:
                                if r.salary_rule_id.id in reglas:
                                    total_columna += r.total
                            for r in l.input_line_ids:
                                if r.name in entradas:
                                    total_columna += r.amount
                            if c.sumar:
                                total_salario += total_columna
                            totales[columna-columna_pd] += total_columna

                            hoja.write(linea, columna, total_columna, number_format)
                            columna += 1
                    
                    if len(columnas_descuento) > 0:
                        for c in columnas_descuento:
                            reglas = [x.id for x in c.regla_id]
                            entradas = [x.name for x in c.entrada_id]
                            total_columna = 0
                            for r in l.line_ids:
                                if r.salary_rule_id.id in reglas:
                                    total_columna += r.total
                            for r in l.input_line_ids:
                                if r.name in entradas:
                                    total_columna += r.amount
                            if c.sumar:
                                total_salario += total_columna
                            totales[columna-columna_pd] += total_columna

                            hoja.write(linea, columna, total_columna, number_format)
                            columna += 1

                    totales[columna-columna_pd] += total_salario
                    hoja.write(linea, columna, total_salario, number_format)
                    hoja.write(linea, columna+1, l.employee_id.identification_id , default_format)
                    if l.cuenta_analitica_id:
                        hoja.write(linea, columna+2, l.cuenta_analitica_id.name, default_format)
                    else:
                        hoja.write(linea, columna+2, 'indefinido', default_format)
                    linea += 1
                    num += 1

                columna = columna_pd
                for t in totales:
                    hoja.write(linea, columna, totales[columna-columna_pd], number_format)
                    columna += 1

            hoja.set_column(0,0,4)
            hoja.set_column(1,2,12)
            hoja.set_column(3,3,25)
            hoja.set_row(3, 20)
            libro.close()
            datos = base64.b64encode(f.getvalue())
            self.write({'archivo': datos})
            return {
                'context': self.env.context,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'rrhh.planilla.wizard',
                'res_id': self.id,
                'view_id': False,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
