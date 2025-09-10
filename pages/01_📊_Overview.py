import streamlit as st

st.title("📊 Overview")
st.write("High-level KPIs, charts, and summaries go here.")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Users", 1234, "+12")
with col2:
    st.metric("Sessions", 5678, "+34")
with col3:
    st.metric("Conversion %", "2.3%", "-0.1%")

st.divider()
st.area_chart({"Series A": [3, 4, 3, 5, 4, 6]})

