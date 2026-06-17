import streamlit as st
import pandas as pd

from fundamental import screen_fundamentals

try:
    from jpx_list import get_codes_by_market
    _JPX_AVAILABLE = True
except ImportError:
    _JPX_AVAILABLE = False

st.title("📊 決算スクリーニング")
st.caption("ROE × 売上成長 × 利益成長 × 1単元価格フィルタ")

with st.expander("フィルタ設定", expanded=True):
    col1, col2 = st.columns(2)

    with col1:
        market_options = ["スタンダード+グロース", "グロース", "スタンダード", "プライム"]
        selected_market = st.selectbox("対象市場", market_options, index=0)

        roe_min = st.number_input("ROE下限(%)", value=10.0, min_value=0.0, step=1.0)
        rev_growth_min = st.number_input("売上高成長率 下限(%)", value=10.0, min_value=0.0, step=1.0)

    with col2:
        earnings_growth_min = st.number_input("利益成長率 下限(%)", value=20.0, min_value=0.0, step=1.0)
        max_unit_options = {"50万円": 500_000, "100万円": 1_000_000, "200万円": 2_000_000}
        max_unit_label = st.selectbox("1単元 上限", list(max_unit_options.keys()), index=1)
        max_unit_price = max_unit_options[max_unit_label]

        custom_codes = st.text_area(
            "銘柄コード（カンマ区切り、空欄で上記市場全銘柄）",
            placeholder="3046, 6058, 3922",
        )

if st.button("決算スクリーニング実行", type="primary", use_container_width=True):
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

    if not codes:
        st.error("対象銘柄が見つかりません")
    else:
        progress = st.progress(0, text="スクリーニング開始...")
        df = screen_fundamentals(
            codes,
            roe_min=roe_min,
            rev_growth_min=rev_growth_min,
            earnings_growth_min=earnings_growth_min,
            max_unit_price=max_unit_price,
            progress_callback=lambda p, t: progress.progress(p, text=t),
        )
        progress.empty()
        st.session_state["fundamental_results"] = df

if "fundamental_results" in st.session_state:
    df = st.session_state["fundamental_results"]

    candidates = df[df["候補"]] if not df.empty else pd.DataFrame()

    if not candidates.empty:
        st.success(f"🎯 全条件クリア: {len(candidates)}銘柄")

        display_cols = [
            "コード", "銘柄名", "株価", "1単元(円)", "ROE(%)",
            "売上成長率(%)", "利益成長率(%)", "利益率(%)", "営業利益率(%)",
            "PER(予想)", "時価総額(億)", "価格帯",
        ]
        st.dataframe(
            candidates[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "1単元(円)": st.column_config.NumberColumn(format="%d"),
                "ROE(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "売上成長率(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "利益成長率(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "利益率(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "営業利益率(%)": st.column_config.NumberColumn(format="%.1f%%"),
                "PER(予想)": st.column_config.NumberColumn(format="%.1f"),
            },
        )
    else:
        st.warning("全条件を満たす銘柄なし。フィルタを緩めてみてください。")

    # 条件部分一致の銘柄
    if not df.empty:
        partial = df[~df["候補"]].copy()
        partial["一致数"] = partial[["ROE✓", "売上✓", "利益✓"]].sum(axis=1).astype(int)
        partial = partial[partial["一致数"] >= 2].sort_values(
            ["一致数", "ROE(%)"], ascending=[False, False]
        )

        if not partial.empty:
            with st.expander(f"惜しい銘柄（2条件一致: {len(partial)}件）", expanded=False):
                partial_cols = [
                    "コード", "銘柄名", "株価", "1単元(円)", "ROE(%)",
                    "売上成長率(%)", "利益成長率(%)", "ROE✓", "売上✓", "利益✓", "価格帯",
                ]
                st.dataframe(
                    partial[partial_cols],
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander("全銘柄一覧", expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV ダウンロード", csv, "fundamental_screening.csv", "text/csv")
