import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from datetime import datetime
import xlsxwriter

# Streamlit page config
st.set_page_config(page_title="Daily Orders", layout="wide")

# WooCommerce API credentials (from Streamlit secrets)
WC_API_URL = st.secrets.get("WC_API_URL")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

# --- Helper Functions ---
def fetch_orders(start_date, end_date):
    """Fetch orders from WooCommerce between two dates."""
    all_orders = []
    page = 1

    while True:
        response = requests.get(
            f"{WC_API_URL}/wp-json/wc/v3/orders",
            params={
                "after": f"{start_date}T00:00:00",
                "before": f"{end_date}T23:59:59",
                "per_page": 100,
                "page": page,
                "status": "any",
                "order": "asc",
                "orderby": "id"
            },
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
        )

        if response.status_code != 200:
            st.error(f"Error fetching orders: {response.status_code} - {response.text}")
            return []

        orders = response.json()
        if not orders:
            break

        all_orders.extend(orders)
        page += 1

    return all_orders


def process_orders(orders):
    """Process raw WooCommerce orders into a structured DataFrame."""
    data = []
    for idx, order in enumerate(sorted(orders, key=lambda x: x['id'])):
        # Build Items Ordered with quantities
        items_ordered = ", ".join([
            f"{item['name']} x {item.get('quantity', 1)}" 
            for item in order['line_items']
        ])
        # Total items (sum of quantities)
        total_items = sum(item.get('quantity', 1) for item in order['line_items'])

        shipping = order.get("shipping", {})
        shipping_address = ", ".join(filter(None, [
            shipping.get("address_1"),
            shipping.get("address_2"),
            shipping.get("city"),
            shipping.get("state"),
            shipping.get("postcode"),
            shipping.get("country")
        ]))

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
            "Line Items": order['line_items']  # for Sheet 2
        })

    return pd.DataFrame(data)


def generate_excel(df):
    """Generate a customized Excel file with two sheets: Orders and Item Summary."""
    output = BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # --- Sheet 1: Orders ---
        sheet1_df = df[["Order ID", "Name", "Items Ordered", "Mobile Number", "Shipping Address", "Order Value", "Order Status", "Total Items"]].copy()
        sheet1_df.rename(columns={
            "Order ID": "Order No",
            "Order Value": "Order Total"
        }, inplace=True)
        sheet1_df.to_excel(writer, index=False, sheet_name='Orders')
        workbook = writer.book
        worksheet1 = writer.sheets['Orders']

        # Format headers
        header_format = workbook.add_format({'bold': True, 'font_color': 'black'})
        for col_num, value in enumerate(sheet1_df.columns.values):
            worksheet1.write(0, col_num, value, header_format)
            worksheet1.set_column(col_num, col_num, 30)

        # Row height
        for row_num in range(1, len(sheet1_df) + 1):
            worksheet1.set_row(row_num, 20)

        # --- Sheet 2: Item Summary ---
        items_list = []
        for line_items in df['Line Items']:
            for item in line_items:
                items_list.append((item['name'], item.get('quantity', 1)))

        summary_df = pd.DataFrame(items_list, columns=['Item Name', 'Quantity'])
        summary_df = summary_df.groupby('Item Name', as_index=False).sum()
        summary_df = summary_df.sort_values('Item Name')

        summary_df.to_excel(writer, index=False, sheet_name='Item Summary')
        worksheet2 = writer.sheets['Item Summary']

        # Format headers
        for col_num, value in enumerate(summary_df.columns.values):
            worksheet2.write(0, col_num, value, header_format)
            worksheet2.set_column(col_num, col_num, 25)

        # Row height
        for row_num in range(1, len(summary_df) + 1):
            worksheet2.set_row(row_num, 20)

    output.seek(0)
    return output


# --- Streamlit UI ---
st.title("Daily Orders")

# Initialize session state
if "orders_df" not in st.session_state:
    st.session_state.orders_df = None
if "orders_data" not in st.session_state:
    st.session_state.orders_data = None

# Date selection
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", datetime.today())
with col2:
    end_date = st.date_input("End Date", datetime.today())

# Fetch button
if st.button("Fetch Orders"):
    with st.spinner("Fetching orders..."):
        orders = fetch_orders(start_date, end_date)
        if orders:
            st.session_state.orders_data = orders  # full JSON
            st.session_state.orders_df = process_orders(orders)
        else:
            st.session_state.orders_data = None
            st.session_state.orders_df = None

# Display orders
if st.session_state.orders_df is not None:
    df = st.session_state.orders_df

    # Remove Line Items for display to avoid PyArrow errors
    display_df = df.drop(columns=["Line Items"]).copy()
    
    # Cast numeric columns to correct types
    display_df["Order ID"] = display_df["Order ID"].astype(int)
    display_df["No of Items"] = display_df["No of Items"].astype(int)
    display_df["Total Items"] = display_df["Total Items"].astype(int)
    display_df["Order Value"] = display_df["Order Value"].astype(float)

    st.write(f"### Total Orders Found: {len(display_df)}")

    # Editable table with persistent checkboxes
    edited_df = st.data_editor(
        display_df,
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(required=False)
        },
        width='stretch',
        key="orders_table"
    )

    # --- Sync Select column immediately back to session_state ---
    st.session_state.orders_df['Select'] = edited_df['Select']

    # --- Build selected_orders from full data safely ---
    selected_order_ids = st.session_state.orders_df.loc[
        st.session_state.orders_df['Select'] == True, 'Order ID'
    ].tolist()

    if st.session_state.orders_data is not None:
        selected_orders_list = [o for o in st.session_state.orders_data if o['id'] in selected_order_ids]
    else:
        selected_orders_list = []

    selected_orders = process_orders(selected_orders_list)  # rebuild DataFrame with Line Items

    if not selected_orders.empty:
        st.success(f"{len(selected_orders)} orders selected for download.")
        excel_data = generate_excel(selected_orders)
        st.download_button(
            label="Download Selected Orders as Excel",
            data=excel_data,
            file_name=f"daily_orders_{start_date}_to_{end_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Select at least one order to enable download.")
else:
    st.info("Fetch orders by selecting a date range and clicking 'Fetch Orders'.")
