import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from screener import (
    screen_breakout, get_candidates, fetch_stock_data,
    detect_new_high, check_roe, analyze_momentum,
    check_continuation, check_false_breakout, check_volume_spike,
    check_market_environment,
)
from disclosure import get_disclosures_for_codes, format_disclosure_summary
from portfolio import load_portfolio, add_position, remove_position, get_portfolio_status
from settings import Screening, MarketFilter
from config import SCREEN_CODES

try:
    from jpx_list import get_codes_by_market
    _JPX_AVAILABLE = True
except ImportError:
    _JPX_AVAILABLE = False

st.title("📈 新高値ブレイク スクリーナー v2")
st.caption("新高値更新 × 初動継続 × だまし除外 × 出来高急増 × 材料突合")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 スクリーニング", "📊 個別分析", "💼 ポートフォリオ", "📖 投資ルール"])

# --- Tab 1: Screening ---
with tab1:
    market = check_market_environment()
    if market.get("market_caution"):
        st.error(f"⚠️ 相場環境注意: 日経平均 {market['nikkei_change_pct']}% — 新規エントリー非推奨日")
    else:
        st.info(f"日経平均 前日比: {market.get('nikkei_change_pct', 'N/A')}%")

    st.subheader("銘柄スクリーニング")

    with st.expander("フィルタ設定", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            market_options = ["スタンダード+グロース", "グロース", "スタンダード", "プライム"]
            selected_market = st.selectbox("対象市場", market_options, index=0)
            custom_codes = st.text_area(
                "銘柄コード（カンマ区切り、空欄で上記市場全銘柄）",
                placeholder="3923, 4478, 7342",
            )
        with fc2:
            st.number_input("高値判定期間(日)", value=Screening.high_lookback_days, key="lookback", disabled=True)
            st.number_input("初動継続日数", value=Screening.continuation_days, key="cont_days", disabled=True)
        with fc3:
            st.number_input("初動乖離上限(%)", value=Screening.continuation_max_drop_pct, key="cont_pct", disabled=True)
            st.number_input("だまし閾値(%)", value=Screening.false_breakout_drop_pct, key="fb_pct", disabled=True)
        with fc4:
            st.number_input("出来高倍率", value=Screening.volume_spike_ratio, key="vol_ratio", disabled=True)
            st.number_input("ROE下限(%)", value=Screening.roe_min_pct, key="roe_min", disabled=True)
        st.caption("※ パラメータは config.yaml で変更できます")

    if st.button("スクリーニング実行", type="primary", use_container_width=True):
        codes = None
        if custom_codes.strip():
            codes = [c.strip() for c in custom_codes.split(",") if c.strip()]
        elif _JPX_AVAILABLE:
            if "+" in selected_market:
                codes = []
                for m in selected_market.split("+"):
                    codes.extend(get_codes_by_market(m.strip()))
                codes = sorted(set(codes))
            else:
                codes = get_codes_by_market(selected_market)

        progress = st.progress(0, text="スクリーニング開始...")
        df = screen_breakout(codes, progress_callback=lambda p, t: progress.progress(p, text=t))
        progress.progress(1.0, text="適時開示を取得中...")

        if not df.empty:
            all_codes = df["コード"].tolist()
            disc_map = get_disclosures_for_codes(all_codes)
            for idx, row in df.iterrows():
                code = row["コード"]
                if code in disc_map:
                    df.at[idx, "材料"] = format_disclosure_summary(disc_map[code])

        progress.empty()
        st.session_state["screen_results"] = df

    if "screen_results" in st.session_state:
        df = st.session_state["screen_results"]

        candidates = get_candidates(df)
        if not candidates.empty:
            st.success(f"🎯 候補銘柄: {len(candidates)}件（新高値 + 初動継続 + だまし除外済）")

            display_cols = [
                "コード", "銘柄名", "現在値", "直近高値", "高値乖離率(%)",
                "出来高倍率", "ROE(%)", "モメンタム", "トレンド", "材料",
                "損切ライン", "時価総額(億)",
            ]
            st.dataframe(
                candidates[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "モメンタム": st.column_config.ProgressColumn(min_value=0, max_value=6, format="%d"),
                    "出来高倍率": st.column_config.NumberColumn(format="%.2fx"),
                    "高値乖離率(%)": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
        else:
            st.info("候補銘柄なし（条件: 新高値 + 初動継続 + だまし除外）")

        with st.expander("全銘柄一覧", expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV ダウンロード", csv, "watchlist.csv", "text/csv")

# --- Tab 2: Individual Analysis ---
with tab2:
    st.subheader("個別銘柄分析")

    code_input = st.text_input("銘柄コード", placeholder="7203")

    if code_input.strip():
        code = code_input.strip()
        with st.spinner(f"{code} を分析中..."):
            data = fetch_stock_data(code, period="1y")

        if data is None:
            st.error("銘柄データを取得できませんでした")
        else:
            info = data["info"]
            hist = data["history"]
            high_info = detect_new_high(hist)
            roe_info = check_roe(info)
            momentum = analyze_momentum(hist)
            cont = check_continuation(hist, high_info)
            false_bk = check_false_breakout(hist, high_info)
            vol = check_volume_spike(hist)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("現在値", f"¥{high_info.get('current_price', 0):,.1f}")
            col2.metric("ROE", f"{roe_info['roe']}%" if roe_info["roe"] else "N/A")
            col3.metric("トレンド", momentum.get("trend", ""))
            col4.metric("出来高倍率", f"{vol.get('volume_ratio', 0):.2f}x")

            status_cols = st.columns(5)
            with status_cols[0]:
                if high_info.get("is_new_high"):
                    st.success("✅ 新高値")
                else:
                    st.warning("高値未更新")
            with status_cols[1]:
                if cont.get("continuation"):
                    st.success(f"✅ 初動継続 (-{cont['drop_from_high_pct']}%)")
                else:
                    drop = cont.get("drop_from_high_pct", "N/A")
                    st.warning(f"失速 (-{drop}%)")
            with status_cols[2]:
                if false_bk.get("false_breakout"):
                    st.error(f"❌ だまし疑い (DD:{false_bk['max_drawdown_pct']}%)")
                else:
                    st.success("✅ だまし無し")
            with status_cols[3]:
                if vol.get("volume_spike"):
                    st.success(f"✅ 出来高急増 ({vol['volume_ratio']}x)")
                else:
                    st.info(f"出来高通常 ({vol.get('volume_ratio', 0)}x)")
            with status_cols[4]:
                if roe_info["passes_roe"]:
                    st.success(f"✅ ROE {Screening.roe_min_pct}%以上")
                else:
                    st.warning(f"ROE {Screening.roe_min_pct}%未満")

            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=hist.index, open=hist["Open"], high=hist["High"],
                low=hist["Low"], close=hist["Close"], name="株価",
            ))

            ma5 = hist["Close"].rolling(5).mean()
            ma25 = hist["Close"].rolling(25).mean()
            ma50 = hist["Close"].rolling(50).mean()
            fig.add_trace(go.Scatter(x=hist.index, y=ma5, name="MA5", line=dict(width=1)))
            fig.add_trace(go.Scatter(x=hist.index, y=ma25, name="MA25", line=dict(width=1)))
            fig.add_trace(go.Scatter(x=hist.index, y=ma50, name="MA50", line=dict(width=1)))

            fig.update_layout(
                title=f"{data['name']} ({code})",
                xaxis_rangeslider_visible=False, height=500,
            )
            st.plotly_chart(fig, use_container_width=True)

            fig_vol = go.Figure()
            colors = ["red" if c < o else "green" for c, o in zip(hist["Close"], hist["Open"])]
            fig_vol.add_trace(go.Bar(x=hist.index, y=hist["Volume"], marker_color=colors, name="出来高"))
            fig_vol.update_layout(title="出来高", height=200, showlegend=False)
            st.plotly_chart(fig_vol, use_container_width=True)

            with st.expander("適時開示"):
                disc_map = get_disclosures_for_codes([code])
                if code in disc_map:
                    for d in disc_map[code]:
                        kw_tag = f" 🏷️{d['keyword']}" if d.get("keyword") else ""
                        link = f" [PDF]({d['link']})" if d.get("link") else ""
                        st.markdown(f"- {d['date']} {d['time']} {d['title']}{kw_tag}{link}")
                else:
                    st.info("直近の適時開示なし")

# --- Tab 3: Portfolio ---
with tab3:
    st.subheader("ポートフォリオ管理")

    with st.expander("新規ポジション追加", expanded=False):
        pcol1, pcol2, pcol3, pcol4 = st.columns(4)
        with pcol1:
            p_code = st.text_input("コード", key="p_code", placeholder="7203")
        with pcol2:
            p_shares = st.number_input("株数", min_value=1, value=100, key="p_shares")
        with pcol3:
            p_price = st.number_input("取得価格", min_value=0.0, value=0.0, key="p_price", format="%.1f")
        with pcol4:
            p_note = st.text_input("メモ", key="p_note")

        if st.button("追加"):
            if p_code and p_price > 0:
                add_position(p_code, p_shares, p_price, p_note)
                st.success(f"{p_code} を追加しました")
                st.rerun()
            else:
                st.error("コードと取得価格を入力してください")

    portfolio = load_portfolio()
    if portfolio:
        with st.spinner("ポートフォリオ更新中..."):
            status_df = get_portfolio_status()

        if not status_df.empty:
            stop_loss = status_df[status_df["要損切"] == "⚠️"]
            if not stop_loss.empty:
                st.error(f"⚠️ 損切りライン到達: {len(stop_loss)}銘柄")

            total_pnl = status_df["損益"].sum()
            total_cost = (status_df["取得価格"] * status_df["株数"]).sum()
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("保有銘柄数", len(portfolio))
            mcol2.metric("総損益", f"¥{total_pnl:,.0f}")
            mcol3.metric("総損益率", f"{total_pnl_pct:.2f}%")

            st.dataframe(status_df, use_container_width=True, hide_index=True)

            del_idx = st.number_input("削除するNo", min_value=0, max_value=len(portfolio) - 1, key="del_idx")
            if st.button("ポジション削除"):
                if remove_position(del_idx):
                    st.success("削除しました")
                    st.rerun()
    else:
        st.info("ポートフォリオにポジションがありません")

# --- Tab 4: Rules ---
with tab4:
    st.subheader("投資ルール（新高値ブレイク投資法 v2）")

    st.markdown(f"""
    ### スクリーニング手順（自動化済み）

    | ステップ | フィルタ | パラメータ |
    |---------|---------|-----------|
    | 1 | **新高値判定** | 過去{Screening.high_lookback_days}日の最高値更新 |
    | 2 | **初動継続** | 直近{Screening.continuation_days}営業日以内に高値、現値は高値から{Screening.continuation_max_drop_pct}%以内 |
    | 3 | **だまし除外** | ブレイク後{Screening.false_breakout_check_days}日以内に{Screening.false_breakout_drop_pct}%超下落→除外 |
    | 4 | **出来高急増** | 直近出来高が{Screening.volume_avg_days}日平均の{Screening.volume_spike_ratio}倍以上 |
    | 5 | **ROEチェック** | ROE {Screening.roe_min_pct}%以上 |
    | 6 | **相場環境** | 日経平均{MarketFilter.nikkei_drop_threshold_pct}%以下の日は非推奨フラグ |
    | 7 | **材料突合** | TDnet適時開示から上方修正・増配等を紐付け |

    ---

    ### 売買ルール

    | ルール | 内容 |
    |--------|------|
    | **エントリー** | 候補銘柄（全フィルタ通過）＋材料ありを優先 |
    | **損切り** | 買値から **{Screening.stop_loss_pct}%下落** で即座に売却 |
    | **ホールド** | 初動継続中は保有。だましフラグが立ったら要確認 |

    ---

    ### 設定変更
    `config.yaml` でパラメータを一元管理しています。変更後にアプリを再起動してください。
    """)
