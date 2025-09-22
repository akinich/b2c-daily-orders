import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="Daily Orders", layout="wide")

# === Load WooCommerce credentials ===
WC_API_URL = st.secrets.get("WC_API_URL")
WC_CONSUMER_KEY = st.secrets.get("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = st.secrets.get("WC_CONSUMER_SECRET")

if not WC_API_URL or not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
    st.error("WooCommerce API credentials are missing. Please add them to secrets.toml.")
    st.stop()

# === Fetch WooCommerce Orders ===
@st.cache_data(ttl=300)
def fetch_orders(start_date, end_date):
    """Fetch WooCommerce orders between two dates"""
    all_orders = []
    page = 1
    per_page = 100  # WooCommerce max is 100 per request

    while True:
        response = requests.get(
            f"{WC_API_URL}/orders",
            params={
                "consumer_key": WC_CONSUMER_KEY,
                "consumer_secret": WC_CONSUMER_SECRET,
                "after": start_date + "T00:00:00",
                "before": end_date + "T23:59:59",
                "per_page": per_page,
                "page": page,
            },
            timeout=30
        )
        response.raise_for_status()
        orders = response.json()

        if not orders:
            break

        all_orders.extend(orders)
        page += 1

    return all_orders

# === Transform data into table ===
def transform_orders(raw_orders):
    data = []
    for order in raw_orders:
        order_id = order.get("id")
        date_created = order.get("date_created", "")[:10]  # YYYY-MM-DD
        name = f"{order['billing'].get('first_name', '')} {order['billing'].get('last_name', '')}".strip()
        status = order.get("status", "")
        total = float(order.get("total", 0))
        items_count = sum(item.get("quantity", 0) for item in order.get("line_items", []))

        data.append({
            "Select": False,  # Default unchecked
            "Order ID": order_id,
            "Date": date_created,
            "Name": name,
            "Order Status": status,
            "Order Value": total,
            "No. of Items": items_count,
        })

    return pd.DataFrame(data)

# === UI ===
st.title("📦 Daily Orders")

# Date filters
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=datetime.today())
with col2:
    end_date = st.date_input("End Date", value=datetime.today())

if st.button("Fetch Orders"):
    with st.spinner("Fetching orders from WooCommerce..."):
        orders_raw = fetch_orders(str(start_date), str(end_date))
        if not orders_raw:
            st.warning("No orders found for the selected date range.")
        else:
            df = transform_orders(orders_raw)
            
            # Editable checkboxes for selection
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True
            )
            
            st.subheader("Selected Orders")
            selected_orders = edited_df[edited_df["Select"] == True]
            st.write(f"Total selected: {len(selected_orders)}")
            st.dataframe(selected_orders, use_container_width=True)
