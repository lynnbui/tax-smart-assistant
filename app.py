import streamlit as st
import pandas as pd
from datetime import date, timedelta
import re
import logging

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wealthsimple Tax-Smart Assistant", 
    page_icon="🛡️",
    layout="centered"
)

# Configure logging (for audit trail in production)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- COMPLIANCE UTILITIES (Testable & Reusable) ---
def check_superficial_loss(
    history: pd.DataFrame, 
    ticker: str, 
    proposed_sale_date: date,
    window_days: int = 30
) -> tuple[bool, pd.DataFrame]:
    window_start = proposed_sale_date - timedelta(days=window_days)
    window_end = proposed_sale_date + timedelta(days=window_days)
    
    trade_dates = history['Date'].apply(lambda d: d.date() if hasattr(d, 'date') else d)
    
    # Check for exact ticker or identical properties
    tickers_to_check = [ticker]
    
    # Edge case: Identical properties (e.g. S&P 500 ETFs)
    IDENTICAL_PROPERTIES = {
        'VFV.TO': ['ZSP.TO'],
        'ZSP.TO': ['VFV.TO']
    }
    if ticker in IDENTICAL_PROPERTIES:
        tickers_to_check.extend(IDENTICAL_PROPERTIES[ticker])
        
    mask = (
        (history['Ticker'].isin(tickers_to_check)) & 
        (history['Action'] == 'BUY') &
        (trade_dates.between(window_start, window_end))
    )
    conflicts = history[mask].copy()
    return not conflicts.empty, conflicts

def calculate_safe_harvest_date(conflict_date: date) -> date:
    """Calculate first date a loss can be claimed after a conflicting buy."""
    return conflict_date + timedelta(days=31)  # CRA: 30-day blackout + 1 day

# --- APP STATE INITIALIZATION ---
if 'history' not in st.session_state:
    # Mock realistic trade history with timezone-aware dates
    st.session_state.history = pd.DataFrame({
        'Date': pd.to_datetime(['2026-02-15', '2026-02-20', '2026-03-01', '2026-02-25', '2026-02-28']),
        'Ticker': ['SHOP', 'XEQT', 'SHOP', 'VFV.TO', 'ZSP.TO'],
        'Action': ['BUY', 'BUY', 'BUY', 'BUY', 'BUY'],
        'Shares': [10, 50, 15, 100, 50],
        'Price': [105.00, 32.00, 98.50, 130.00, 75.00],
        'Account': ['Self-Directed TFSA', 'Self-Directed RRSP', 'Self-Directed TFSA', 'Self-Directed Margin', 'Self-Directed TFSA']
    })

if 'processing' not in st.session_state:
    st.session_state.processing = False

# --- UI HEADER ---
st.title("🛡️ Tax-Smart Trade Assistant")
st.write("Proactive CRA compliance for self-directed investors.")
st.caption("⚠️ Educational tool only. Consult a tax professional for personal advice.")

# --- SECTION 1: TRADE DETAILS ---
st.subheader("1. Select Your Trade")

SUPPORTED_TICKERS = ['SHOP', 'XEQT', 'AAPL', 'MSFT', 'TSLA', 'RY', 'TD', 'VFV.TO', 'ZSP.TO']
target_ticker = st.selectbox("Select Ticker:", SUPPORTED_TICKERS)

# Optional: Let user specify sale date (defaults to today)
proposed_sale_date = st.date_input(
    "Proposed trade date:", 
    value=date.today(),
    min_value=date.today() - timedelta(days=365),
    max_value=date.today() + timedelta(days=365)
)

col1, col2 = st.columns(2)
with col1:
    buy_clicked = st.button("BUY", key="btn_buy", use_container_width=True, disabled=st.session_state.processing)
with col2:
    sell_clicked = st.button("SELL", key="btn_sell", use_container_width=True, disabled=st.session_state.processing)

# --- SECTION 2: COMPLIANCE CHECK ---
if buy_clicked or sell_clicked:
    st.session_state.processing = True
    action = "BUY" if buy_clicked else "SELL"
    
    with st.spinner(f"🔍 Analyzing tax impact for `{target_ticker}`..."):
        try:
            # Log the compliance check (audit trail)
            logger.info(f"Compliance check: user={st.session_state.get('user', 'guest')}, ticker={target_ticker}, action={action}, date={proposed_sale_date}")
            
            st.info(f"**✅ Trade Selected:** {action} `{target_ticker}` on **{proposed_sale_date.strftime('%b %d, %Y')}**")
            
            # --- RESULTS SECTION ---
            st.subheader("2. Compliance Radar")
            
            if action == "BUY":
                st.success("✅ **CLEAR TO TRADE**")
                st.markdown(f"Buying `{target_ticker}` does not trigger superficial loss rules. However, it may block you from harvesting losses on `{target_ticker}` for 30 days before and after **{proposed_sale_date.strftime('%b %d, %Y')}**.")
            else:
                # Run deterministic compliance engine
                has_conflict, conflicts = check_superficial_loss(
                    st.session_state.history, 
                    target_ticker, 
                    proposed_sale_date
                )
                
                if has_conflict:
                    st.error("🚨 **SUPERFICIAL LOSS WARNING**")
                    
                    # Show conflicting trades
                    for _, trade in conflicts.iterrows():
                        trade_date = trade['Date'].date() if hasattr(trade['Date'], 'date') else trade['Date']
                        st.markdown(f"""
                        **Conflicting Trade Detected:**
                        - 📅 Date: **{trade_date.strftime('%b %d, %Y')}**
                        - 💼 Account: `{trade['Account']}`
                        - 📊 Action: **BUY** {trade['Shares']} shares @ ${trade['Price']:.2f}
                        """)
                    
                    # Calculate and display safe date
                    earliest_conflict = min(
                        c['Date'].date() if hasattr(c['Date'], 'date') else c['Date'] 
                        for _, c in conflicts.iterrows()
                    )
                    safe_date = calculate_safe_harvest_date(earliest_conflict)
                    
                    st.markdown(f"""
                    **The Impact:**  
                    Selling `{target_ticker}` at a loss on **{proposed_sale_date}** will trigger a CRA Superficial Loss denial.
                    
                    **✅ Safe to Harvest After:** **{safe_date.strftime('%b %d, %Y')}**  
                    *(30-day blackout period after the most recent conflicting buy)*
                    """)
                    
                    # --- SECTION 3: ALTERNATIVES ---
                    st.subheader("3. Smart Alternatives")
                    col1_alt, col2_alt = st.columns(2)
                    
                    with col1_alt:
                        if st.button(f"⏰ Set Reminder for {safe_date.strftime('%b %d')}", key="btn_reminder"):
                            st.success(f"🔔 Reminder set! We'll notify you when `{target_ticker}` is eligible for loss harvesting.")
                            # In production: integrate with notification service
                    
                    with col2_alt:
                        # Suggest alternative tickers with no conflicts
                        alternatives = [
                            t for t in SUPPORTED_TICKERS 
                            if t != target_ticker and not check_superficial_loss(
                                st.session_state.history, t, proposed_sale_date
                            )[0]
                        ]
                        if alternatives:
                            st.success(f"💡 Try harvesting: **{', '.join(alternatives[:2])}** (no conflicts detected)")
                        else:
                            st.info("ℹ️ All supported tickers have recent activity. Consider waiting or consulting an advisor.")
                
                else:
                    st.success("✅ **CLEAR TO TRADE**")
                    st.markdown(f"""
                    No conflicting BUY orders for `{target_ticker}` detected within the 30-day window 
                    around **{proposed_sale_date.strftime('%b %d, %Y')}**.
                    
                    **Next Steps:**
                    1. Confirm your adjusted cost base (ACB) is up to date
                    2. Execute your trade
                    3. Document the loss for your tax filing
                    """)
                    
                    if st.button("📥 Export Compliance Report", key="btn_export"):
                        # Generate simple report
                        report = f"""
                        TAX COMPLIANCE CHECK - {date.today()}
                        Ticker: {target_ticker}
                        Proposed Sale Date: {proposed_sale_date}
                        Result: CLEAR TO TRADE
                        Conflicts Found: 0
                        """
                        st.download_button(
                            label="Download TXT Report",
                            data=report,
                            file_name=f"tax_check_{target_ticker}_{proposed_sale_date}.txt",
                            mime="text/plain"
                        )
                    
        except Exception as e:
            logger.error(f"Compliance check failed: {str(e)}", exc_info=True)
            st.error(f"⚠️ Analysis interrupted: {str(e)}")
            st.info("Please try again or contact support if this persists.")
        finally:
            st.session_state.processing = False

# --- DATA TRANSPARENCY SECTION ---
with st.expander("🔍 View 30-Day Activity Log (Data Source)"):
    st.caption("This is the transaction history the compliance engine scans.")
    
    window_start = date.today() - timedelta(days=30)
    window_end = date.today() + timedelta(days=30)
    
    trade_dates = st.session_state.history['Date'].apply(
        lambda d: d.date() if hasattr(d, 'date') else d
    )
    visible_history = st.session_state.history[
        trade_dates.between(window_start, window_end)
    ].copy()
    
    if not visible_history.empty:
        # Format dates for display
        visible_history['Date'] = visible_history['Date'].apply(
            lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
        )
        st.dataframe(
            visible_history[['Date', 'Ticker', 'Action', 'Shares', 'Price', 'Account']], 
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("📭 No trades found in the ±30 day window around today.")

# --- FOOTER / DISCLAIMER ---
st.markdown("---")
st.markdown("""
<p style="font-size: 0.85em; color: grey; font-style: italic;">
<strong>Disclaimer:</strong> This tool provides educational guidance only and does not constitute tax, legal, or financial advice.
CRA superficial loss rules (Income Tax Act Section 54) are complex and fact-specific.
Always consult a qualified tax professional before executing tax-loss harvesting strategies.
Wealthsimple does not guarantee the accuracy of compliance determinations.
</p>
""", unsafe_allow_html=True)

# --- DEV MODE TOGGLE (Remove in production) ---
if st.checkbox("🔧 Dev Mode: Show Session State", key="dev_toggle"):
    with st.expander("Session State Debug"):
        st.json({
            "history_rows": len(st.session_state.history),
            "processing": st.session_state.processing,
            "proposed_sale_date": str(proposed_sale_date)
        })