import streamlit as st

st.set_page_config(
    page_title="DataForge",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛠️ DataForge Dashboard")
st.write(
    """
    Welcome to the DataForge multipage Streamlit dashboard scaffold.
    
    - Use the sidebar to navigate between pages.
    - This is a minimal, production-friendly structure powered by UV.
    """
)

st.success("Project scaffold is ready. Add your pages under the `pages/` folder.")

