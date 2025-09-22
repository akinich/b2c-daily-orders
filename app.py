import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Daily Orders", layout="wide")

# === WooCommerce Credentials ===
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
    per_page = 100  # WooCommerce API max

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

# === Transform Data ===
def transform_orders(raw_orders):
    """Convert WooCommerce JSON into a clean DataFrame"""
    data = []
    for order in raw_orders:
        order_id = order.get("id")
        date_created = order.get("date_created", "")[:10]  # YYYY-MM-DD
        name = f"{order['billing'].get('first_name', '')} {order['billing'].get('last_name', '')}".strip()
        status = order.get("status", "")
        total = float(order.get("total", 0))
        items_count = sum(item.get("quantity", 0) for item in order.get("line_items", []))

        data.append({
            "Select": False,
            "Order ID": order_id,
            "Date": date_created,
            "Name": name,
            "Order Status": status,
            "Order Value": total,
            "No. of Items": items_count,
        })

    # Sort by date, newest first
    df = pd.DataFrame(data)
    df = df.sort_values(by="Date", ascending=False).reset_index(drop=True)
    return df

# === Helper to create Excel file ===
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Orders')
    processed_data = output.getvalue()
    return processed_data

# === UI ===
st.title("📦 Daily Orders")

# Date filters
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=datetime.today())
with col2:
    end_date = st.date_input("End Date", value=datetime.today())

# Fetch orders button
if st.button("Fetch Orders"):
    with st.spinner("Fetching orders from WooCommerce..."):
        orders_raw = fetch_orders(str(start_date), str(end_date))

        if not orders_raw:
            st.warning("No orders found for the selected date range.")
        else:
            df = transform_orders(orders_raw)

            st.success(f"Fetched {len(df)} orders")

            # Select how many orders to display
            max_orders = st.number_input(
                "Number of orders to display",
                min_value=1,
                max_value=len(df),
                value=min(10, len(df)),
                step=1
            )
            df_limited = df.head(max_orders)

            # Editable table with checkboxes
            st.subheader("Orders Table")
            edited_df = st.data_editor(
                df_limited,
                num_rows="dynamic",
                hide_index=True,
                use_container_width=True
            )

            # Filter only selected rows
            selected_orders = edited_df[edited_df["Select"] == True]

            st.subheader("Selected Orders")
            st.write(f"Total selected: {len(selected_orders)}")
            st.dataframe(selected_orders, use_container_width=True)

            # === Download Excel ===
            if not selected_orders.empty:
                excel_data = to_excel(selected_orders)
                st.download_button(
                    label="📥 Download Selected Orders as Excel",
                    data=excel_data,
                    file_name=f"selected_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
