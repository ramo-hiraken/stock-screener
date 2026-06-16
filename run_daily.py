"""日次バッチスクリーニング。cron / GitHub Actions から実行する。"""

import sys
from datetime import datetime
from pathlib import Path

from screener import screen_breakout, get_candidates
from disclosure import get_disclosures_for_codes, format_disclosure_summary
from settings import Output


def run():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] スクリーニング開始")

    def progress(pct, msg):
        print(f"  {msg}", end="\r")

    df = screen_breakout(progress_callback=progress)
    print(f"\n全銘柄分析完了: {len(df)}件")

    if df.empty:
        print("結果なし")
        return

    codes = df["コード"].tolist()
    print("適時開示を取得中...")
    disc_map = get_disclosures_for_codes(codes)
    for idx, row in df.iterrows():
        code = row["コード"]
        if code in disc_map:
            df.at[idx, "材料"] = format_disclosure_summary(disc_map[code])

    candidates = get_candidates(df)
    print(f"候補銘柄: {len(candidates)}件")

    out_dir = Path(Output.csv_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    filename = Output.csv_filename_format.replace("{date}", date_str)

    all_path = out_dir / filename
    df.to_csv(all_path, index=False, encoding="utf-8-sig")
    print(f"全銘柄CSV: {all_path}")

    if not candidates.empty:
        cand_path = out_dir / filename.replace("watchlist_", "candidates_")
        candidates.to_csv(cand_path, index=False, encoding="utf-8-sig")
        print(f"候補CSV: {cand_path}")

        print("\n=== 候補銘柄一覧 ===")
        for _, r in candidates.iterrows():
            mark = "⚠️" if r["だまし疑い"] else "✅"
            mat = f" [{r['材料']}]" if r["材料"] else ""
            print(
                f"  {mark} {r['コード']} {r['銘柄名']}"
                f"  現値:{r['現在値']}  高値:{r['直近高値']}  乖離:{r['高値乖離率(%)']}%"
                f"  出来高:{r['出来高倍率']}x  ROE:{r['ROE(%)']}%  Mo:{r['モメンタム']}"
                f"{mat}"
            )

    if df.iloc[0]["相場環境"] == "⚠️注意":
        print(f"\n⚠️ 相場環境注意: 日経平均 {df.iloc[0]['日経変動(%)']}%  新規エントリー非推奨")

    print(f"\n[{datetime.now():%H:%M}] 完了")


if __name__ == "__main__":
    run()
