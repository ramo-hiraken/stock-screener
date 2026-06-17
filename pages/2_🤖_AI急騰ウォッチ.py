"""AI関連銘柄 急騰ウォッチダッシュボード"""

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime

from ai_stocks import AI_STOCKS, AI_CATEGORIES, get_ai_codes, get_ai_codes_by_category

st.title("🤖 AI関連銘柄 急騰ウォッチ")
st.caption("AI関連（半導体・DC・電力インフラ・ソフトウェア）× 前日比+5%以上")

# --- Sidebar ---
with st.sidebar:
    st.header("フィルタ設定")
    threshold = st.slider("前日比しきい値(%)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)
    selected_categories = st.multiselect("カテゴリ", AI_CATEGORIES, default=AI_CATEGORIES)
    show_all = st.checkbox("しきい値以下も表示", value=True)

# --- Data Fetch ---
@st.cache_data(ttl=300)
def fetch_all_ai_data(codes: list[str]) -> pd.DataFrame:
    rows = []
    tickers_str = " ".join(f"{c}.T" for c in codes)
    try:
        data = yf.download(tickers_str, period="5d", group_by="ticker", progress=False, threads=True)
    except Exception:
        data = pd.DataFrame()

    for code in codes:
        info = AI_STOCKS[code]
        try:
            if len(codes) == 1:
                ticker_data = data
            else:
                ticker_data = data[f"{code}.T"]

            if ticker_data.empty or len(ticker_data) < 2:
                continue

            prev_close = float(ticker_data["Close"].iloc[-2])
            last_close = float(ticker_data["Close"].iloc[-1])
            last_open = float(ticker_data["Open"].iloc[-1])
            last_high = float(ticker_data["High"].iloc[-1])
            last_low = float(ticker_data["Low"].iloc[-1])
            last_vol = int(ticker_data["Volume"].iloc[-1])

            change_pct = ((last_close / prev_close) - 1) * 100 if prev_close > 0 else 0

            rows.append({
                "コード": code,
                "銘柄名": info["name"],
                "カテゴリ": info["category"],
                "テーマ": info["theme"],
                "前日終値": round(prev_close, 1),
                "始値": round(last_open, 1),
                "高値": round(last_high, 1),
                "安値": round(last_low, 1),
                "終値": round(last_close, 1),
                "前日比(%)": round(change_pct, 2),
                "出来高": last_vol,
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("前日比(%)", ascending=False)
    return df


codes = []
for cat in selected_categories:
    codes.extend(get_ai_codes_by_category(cat))
codes = sorted(set(codes))

if not codes:
    st.warning("カテゴリを選択してください")
    st.stop()

with st.spinner(f"AI関連{len(codes)}銘柄のデータ取得中..."):
    df = fetch_all_ai_data(codes)

if df.empty:
    st.error("データ取得に失敗しました")
    st.stop()

# --- Metrics ---
surging = df[df["前日比(%)"] >= threshold]
declining = df[df["前日比(%)"] <= -threshold]
avg_change = df["前日比(%)"].mean()

col1, col2, col3, col4 = st.columns(4)
col1.metric("監視銘柄数", f"{len(df)}")
col2.metric(f"+{threshold}%以上", f"{len(surging)}銘柄", delta=f"{len(surging)}")
col3.metric(f"-{threshold}%以下", f"{len(declining)}銘柄")
col4.metric("AI銘柄平均", f"{avg_change:+.2f}%")

st.divider()

# --- Surge Alert ---
if not surging.empty:
    st.subheader(f"🔥 急騰銘柄（前日比+{threshold}%以上）")
    for _, row in surging.iterrows():
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 2])
            c1.markdown(f"**{row['コード']} {row['銘柄名']}**")
            c2.metric("前日比", f"+{row['前日比(%)']:.2f}%")
            c3.metric("終値", f"¥{row['終値']:,.0f}")
            c4.metric("出来高", f"{row['出来高']:,}")
            c5.markdown(f"🏷️ {row['カテゴリ']} / {row['テーマ']}")
    st.divider()
else:
    st.info(f"現在 +{threshold}% 以上の急騰銘柄はありません")

# --- Heatmap ---
st.subheader("📊 AI銘柄ヒートマップ")

fig = go.Figure(go.Treemap(
    labels=[f"{r['コード']}<br>{r['銘柄名']}<br>{r['前日比(%)']:+.1f}%" for _, r in df.iterrows()],
    parents=["" for _ in range(len(df))],
    values=[abs(r["出来高"]) for _, r in df.iterrows()],
    marker=dict(
        colors=df["前日比(%)"].tolist(),
        colorscale=[[0, "#d32f2f"], [0.4, "#ffcdd2"], [0.5, "#f5f5f5"], [0.6, "#c8e6c9"], [1, "#2e7d32"]],
        cmid=0,
        colorbar=dict(title="前日比(%)"),
    ),
    textinfo="label",
    textfont=dict(size=14),
))
fig.update_layout(height=500, margin=dict(t=10, l=10, r=10, b=10))
st.plotly_chart(fig, use_container_width=True)

# --- Full Table ---
st.subheader("📋 全銘柄一覧")

display_df = df if show_all else surging
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "前日比(%)": st.column_config.NumberColumn(format="%+.2f%%"),
        "出来高": st.column_config.NumberColumn(format="%d"),
    },
)

csv = display_df.to_csv(index=False).encode("utf-8-sig")
st.download_button("📥 CSV ダウンロード", csv, f"ai_watch_{datetime.now():%Y%m%d}.csv", "text/csv")

# --- Category Breakdown ---
st.subheader("📈 カテゴリ別パフォーマンス")
cat_perf = df.groupby("カテゴリ")["前日比(%)"].agg(["mean", "count", "max"]).round(2)
cat_perf.columns = ["平均変動(%)", "銘柄数", "最大変動(%)"]
cat_perf = cat_perf.sort_values("平均変動(%)", ascending=False)

fig_cat = go.Figure(go.Bar(
    x=cat_perf.index,
    y=cat_perf["平均変動(%)"],
    marker_color=["#2e7d32" if v >= 0 else "#d32f2f" for v in cat_perf["平均変動(%)"]],
    text=[f"{v:+.2f}%" for v in cat_perf["平均変動(%)"]],
    textposition="outside",
))
fig_cat.update_layout(height=350, yaxis_title="平均前日比(%)", xaxis_title="")
st.plotly_chart(fig_cat, use_container_width=True)

# --- Individual Chart ---
st.subheader("📉 個別チャート")
selected = st.selectbox(
    "銘柄を選択",
    options=df["コード"].tolist(),
    format_func=lambda c: f"{c} {AI_STOCKS.get(c, {}).get('name', '')}",
)

if selected:
    ticker = yf.Ticker(f"{selected}.T")
    hist = ticker.history(period="3mo")
    if not hist.empty:
        fig_stock = go.Figure()
        fig_stock.add_trace(go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"],
            low=hist["Low"], close=hist["Close"], name="株価",
        ))
        ma5 = hist["Close"].rolling(5).mean()
        ma25 = hist["Close"].rolling(25).mean()
        fig_stock.add_trace(go.Scatter(x=hist.index, y=ma5, name="MA5", line=dict(width=1)))
        fig_stock.add_trace(go.Scatter(x=hist.index, y=ma25, name="MA25", line=dict(width=1)))
        fig_stock.update_layout(
            title=f"{AI_STOCKS[selected]['name']} ({selected}) — {AI_STOCKS[selected]['theme']}",
            xaxis_rangeslider_visible=False, height=450,
        )
        st.plotly_chart(fig_stock, use_container_width=True)

st.caption("※ 本ダッシュボードは投資助言ではありません。データは yfinance 経由で取得しています。")
