import locale
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from DTE.DTE import DTE
import pandas as pd
from datetime import datetime
from num2words import num2words
from pdf417 import encode, render_image, render_svg
import numpy as np

locale.setlocale(locale.LC_ALL, '')

env = Environment(loader=FileSystemLoader('.'))
template = env.get_template("./templates/invoice.html")


# Función que obtiene el código de barras a partir del texto del timbre
def xml_to_svg(xml_text):
    codes = encode(xml_text, columns=11)
    svg = render_svg(codes)
    svg.write('./templates/barcode.svg')


# Función que convierte documento del SII de XML a PDF
def sii_doc_XMLtoPDF(path):
    dte_parsed = DTE(path)

    # Genera código de barras
    xml_to_svg(dte_parsed.timbre)

    # TABLA ITEMS
    df = pd.json_normalize(dte_parsed.items)
    df["Item"] = range(1, len(df) + 1)
    # df["Codigo"] = 0
    df["Cant"] = df["Cant"].astype(float)
    df["P. Unitario"] = df["rate"].astype(float).astype(int).map('{:,}'.format).str.replace(
        ",",
        ".")
    df["Total"] = (df["Cant"].astype(float) * df["rate"].astype(float)).astype(int).map('{:,}'.format).str.replace(
        ",",
        ".")
    df["Dscto"] = 0
    df = df[["Item", "Codigo", "Descripcion",  "Cant", "P. Unitario", "Dscto", "Total"]]
    required_rows = 20  # Change this if needed based on table height
    if len(df) < required_rows:
        empty_rows = required_rows - len(df)
        empty_data = pd.DataFrame([["", "", "", "", "", "", ""]] * empty_rows, columns=df.columns)
        df = pd.concat([df, empty_data], ignore_index=True)
    # df.style.format("{:.2%}")

    # TABLA REFERENCIAS
    df_referencias = pd.json_normalize(dte_parsed.referencias)

    # Convert references into an actual HTML table
    if df_referencias.empty:
        referencias_html = "<tr><td colspan='4'>No hay referencias</td></tr>"
    else:
        referencias_html = df_referencias.to_html(
            index=False,
            header=False,
            border=0,
            columns=["tipo_doc_referencia_palabras", "folio_referencia","fecha_referencia", "razon_referencia"]
        )

        referencias_html = referencias_html.replace("\n", "").replace("  ", " ")
        referencias_html = referencias_html.replace('<table border="0" class="dataframe">', '').replace('</table>', '')

    # TAX TABLE (IMPUESTOS)
    df_impuestos = pd.json_normalize(dte_parsed.impuestos)
    monto_impuesto_y_retenciones = df_impuestos["monto"].astype(int).sum() if not df_impuestos.empty else 0
    impuestos_html = "" if df_impuestos.empty else df_impuestos.to_html(index=False)

    # TRASPASA VARIABLES AL TEMPLATE
    template_vars = {
        "rut": dte_parsed.rut_proveedor,
        "supplier_name": dte_parsed.razon_social,
        "supplier_activity": dte_parsed.giro_proveedor,
        "bill_no": dte_parsed.numero_factura,
        "purchase_invoice_items": df.to_html(index=False, classes="items_factura"),
        "tipo_documento": dte_parsed.tipo_dte_palabras,
        "fecha_emision": datetime.strftime(datetime.strptime(dte_parsed.fecha_emision, "%Y-%m-%d"), "%d-%m-%Y"),
        "supplier_address_detail": dte_parsed.direccion_proveedor,
        "supplier_address_comuna": dte_parsed.comuna_proveedor,
        "supplier_address_city": dte_parsed.ciudad_proveedor,
        # Dator receptor
        "receptor_razon_social": dte_parsed.receptor_razon_social,
        "receptor_giro": dte_parsed.receptor_giro,
        "receptor_contacto": dte_parsed.receptor_contacto,
        "receptor_rut": dte_parsed.receptor_rut,
        "receptor_direccion": dte_parsed.receptor_direccion,
        "receptor_ciudad": dte_parsed.receptor_ciudad,
        "receptor_comuna": dte_parsed.receptor_comuna,
        "forma_pago_palabras": dte_parsed.forma_pago_palabras,
        "fecha_vencimiento": datetime.strftime(datetime.strptime(dte_parsed.fecha_vencimiento, "%Y-%m-%d"), "%d-%m-%Y"),
        # Referencias
        "referencias_table": referencias_html,
        "impuestos_table": impuestos_html,
        "tipo_doc": dte_parsed.tipo_doc_referencia,
        "folio_referencial": dte_parsed.folio_referencia,
        "fecha_referencial": dte_parsed.fecha_referencia,
        # Totales
        "monto_total_palabras": num2words(dte_parsed.monto_total, lang="es").upper(),
        "monto_total": f"{int(dte_parsed.monto_total):n}",
        "monto_iva": f"{int(dte_parsed.monto_iva):n}",
        "monto_exento": f"{int(dte_parsed.monto_exento):n}",
        "monto_neto": f"{int(dte_parsed.monto_neto):n}",
        "monto_impuesto_y_retenciones": f"{int(monto_impuesto_y_retenciones):n}",
        "src_timbre": """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <path d="M30,1h40l29,29v40l-29,29h-40l-29-29v-40z" stroke="#000" fill="none"/> 
      <path d="M31,3h38l28,28v38l-28,28h-38l-28-28v-38z" fill="#a23"/> 
      <text x="50" y="68" font-size="48" fill="#FFF" text-anchor="middle"><![CDATA[410]]></text>
    </svg>"""
    }

    invoice_html = template.render(template_vars)

    file_name_output = f"./output/pdf/{dte_parsed.fecha_emision.replace('-', '')} {dte_parsed.tipo_dte_abreviatura} {dte_parsed.razon_social.title().replace('.', '')} {dte_parsed.numero_factura}.pdf"

    HTML(string=invoice_html).write_pdf(file_name_output, stylesheets=["./templates/invoice.css"])


# Función que filtra las OC dentro de las referencias del XML
def obtieneRefOc(referencias):
    for referencia in referencias:
        if referencia["tipo_doc_referencia"] != "801":
            continue
        return referencia["folio_referencia"]


# Función que añade el detalle de un xml a un pandas dataframe como fila
def append_xml_to_df(df, xml_file):
    dte_parsed = DTE(xml_file)
    df = df.append({
        "rut": dte_parsed.rut_proveedor,
        "fecha": dte_parsed.fecha_emision,
        "folio": dte_parsed.numero_factura,
        "montoNeto": dte_parsed.monto_neto,
        "referencias_oc": obtieneRefOc(dte_parsed.referencias),
        "tipoDoc": dte_parsed.tipo_dte,
        "items": dte_parsed.items,
        "comuna": dte_parsed.comuna_proveedor
    },
        ignore_index=True, )
    return df
