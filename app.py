import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
import json
import xlsxwriter

# ==============================
# CONFIGURATIONS
# ==============================
WC_API_URL = st.secrets.get("WC_API_URL")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

if not WC_API_URL or not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
    st.error("WooCommerce API credentials are missing. Please add them in Streamlit Secrets.")
    st.stop()

# ==============================
# PDF FONT
# ==============================
pdfmetrics.registerFont(TTFont('Courier-Bold', 'Courier-Bold.ttf'))

# ==============================
# HELPER FUNCTIONS
# ==============================
def fetch_orders(start_date, end_date):
    url = f"{WC_API_URL}/orders"
    params = {
        "after": f"{start_date}T00:00:00",
        "before": f"{end_date}T23:59:59",
        "per_page": 100,
        "status": "any"
    }
    response = requests.get(url, params=params, auth=HTTPBasicAuth(WC_CONSUMER_KEY, WC_CONSUMER_SECRET))
    response.raise_for_status()
    return response.json()

def process_orders(orders):
    data = []
    for idx, order in enumerate(orders):
        total_items = sum(item['quantity'] for item in order['line_items'])
        shipping_address = f"{order['shipping']['address_1']}, {order['shipping']['city']}, {order['shipping']['state']} {order['shipping']['postcode']}"
        items_ordered = ", ".join([f"{item['name']} ({item['quantity']})" for item in order['line_items']])

        data.append({
            "S.No": idx + 1,
            "Select": False,
            "Order ID": order['id'],
            "Date": datetime.strptime(order['date_created'], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d"),
            "Name": order['billing'].get('first_name', '') + " " + order['billing'].get('last_name', ''),
            "Order Status": order['status'],
            "Order Value": float(order['total']),
            "No of Items": len(order['line_items']),
            "Total Items": total_items,
            "Mobile Number": order['billing'].get('phone', ''),
            "Shipping Address": shipping_address,
            "Items Ordered": items_ordered,
            "Line Items": order['line_items']  # For Sheet 2
        })
    return pd.DataFrame(data)

def generate_excel(selected_orders_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        sheet1_df = selected_orders_df.drop(columns=["Select", "Line Items"], errors='ignore')
        
        # === CHANGE REQUESTED HERE ===
        sheet1_df.rename(columns={
            "Order No": "Order #",
            "Customer Name": "Name"
        }, inplace=True)
        # ============================

        sheet1_df.to_excel(writer, sheet_name='Orders', index=False)

        # Sheet 2: Line Items
        line_items_data = []
        for _, row in selected_orders_df.iterrows():
            for item in row["Line Items"]:
                line_items_data.append({
                    "Order ID": row["Order ID"],
                    "Product Name": item["name"],
                    "Quantity": item["quantity"],
                    "Price": item["price"],
                    "Total": item["total"]
                })
        if line_items_data:
            pd.DataFrame(line_items_data).to_excel(writer, sheet_name='Line Items', index=False)

        writer.save()
    return output.getvalue()

def generate_pdf(selected_orders_df):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    for _, row in selected_orders_df.iterrows():
        c.setFont("Courier-Bold", 12)
        c.drawString(50, height - 50, f"Order ID: {row['Order ID']}")
        c.drawString(50, height - 70, f"Customer Name: {row['Name']}")
        c.drawString(50, height - 90, f"Date: {row['Date']}")
        c.drawString(50, height - 110, f"Order Total: {row['Order Value']}")
        c.line(50, height - 130, width - 50, height - 130)
        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer

# ==============================
# STREAMLIT UI
# ==============================
st.title("WooCommerce Orders Exporter")

start_date = st.date_input("Start Date", value=datetime.today())
end_date = st.date_input("End Date", value=datetime.today())

if st.button("Fetch Orders"):
    with st.spinner("Fetching orders..."):
        orders = fetch_orders(start_date, end_date)
        df = process_orders(orders)

        if df.empty:
            st.warning("No orders found for the selected date range.")
        else:
            st.session_state["orders_df"] = df
            st.success(f"Fetched {len(df)} orders.")

if "orders_df" in st.session_state:
    st.subheader("Orders Table")
    edited_df = st.data_editor(
        st.session_state["orders_df"],
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(required=True, default=False)
        }
    )

    if st.button("Generate Excel"):
        selected_orders_df = edited_df[edited_df["Select"] == True]
        if selected_orders_df.empty:
            st.warning("No orders selected.")
        else:
            excel_data = generate_excel(selected_orders_df)
            st.download_button(
                label="Download Excel",
                data=excel_data,
                file_name=f"orders_{datetime.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    if st.button("Generate PDF"):
        selected_orders_df = edited_df[edited_df["Select"] == True]
        if selected_orders_df.empty:
            st.warning("No orders selected.")
        else:
            pdf_buffer = generate_pdf(selected_orders_df)
            st.download_button(
                label="Download PDF",
                data=pdf_buffer,
                file_name=f"orders_{datetime.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
