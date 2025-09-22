import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from datetime import datetime

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
        # Combine item names into a single cell
        items_ordered = ", ".join([item['name'] for item in order['line_items']])

        # Extract shipping address
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
            "Mobile Number": order['billing'].get('phone', ''),
            "Shipping Address": shipping_address,
            "Items Ordered": items_ordered
        })

    return pd.DataFrame(data)


def generate_excel(df):
    """Generate a customized Excel file from selected orders."""
    output = BytesIO()

    # Create a DataFrame with only required columns
    export_df = df[["Order ID", "Name", "Items Ordered", "Mobile Number", "Shipping Address", "Order Value"]].copy()
    export_df.rename(columns={
        "Order ID": "Order No",
        "Order Value": "Order Total"
    }, inplace=True)

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Orders')

    output.seek(0)
    return output

# --- Streamlit UI ---
st.title("Daily Orders")

# Initialize session state
if "orders_df" not in st.session_state:
    st.session_state.orders_df = None

# Date range selection
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", datetime.today())
with col2:
    end_date = st.date_input("End Date", datetime.today())

# Fetch orders button
if st.button("Fetch Orders"):
    with st.spinner("Fetching orders..."):
        orders = fetch_orders(start_date, end_date)
        if orders:
            st.session_state.orders_df = process_orders(orders)
        else:
            st.session_state.orders_df = None

# Display orders if available
if st.session_state.orders_df is not None:
    df = st.session_state.orders_df

    # Show total orders
    st.write(f"### Total Orders Found: {len(df)}")

    # Editable table with selection
    edited_df = st.data_editor(
        df,
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(required=False)
        },
        use_container_width=True,
        key="orders_table"
    )

    # Filter only selected rows
    selected_orders = edited_df[edited_df["Select"] == True]

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
