"""
wfmap (xlhaw/wfmap, v1.0.3) 웨이퍼 heatmap 샘플.
wfmap은 정수 격자(MAP_ROW / MAP_COL) 기반 die map 라이브러리이고 3D는 미지원.
우리 공통 데이터(X, Y in mm)를 die 단위로 rounding해서 DataFrame으로 넘긴다.
실행: python sample_wfmap.py
PNG 저장: output_wfmap_num.png, output_wfmap_full.png
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_DEBUG = Path(__file__).resolve().parent.parent / "debug"
_DEBUG.mkdir(exist_ok=True)

# wfmap 1.0.3은 오래된 pandas API(positional pivot)를 써서 pandas 2+에서 실패 →
# pd.DataFrame.pivot 을 감싸서 positional→keyword 변환. 샘플 한정 임시 shim.
_orig_pivot = pd.DataFrame.pivot
def _shim_pivot(self, *args, **kwargs):
    if args:
        for i, v in enumerate(args):
            kwargs.setdefault(("index", "columns", "values")[i], v)
        args = ()
    return _orig_pivot(self, *args, **kwargs)
pd.DataFrame.pivot = _shim_pivot

import wfmap

from sample_data import make_wafer_points


def main():
    # 좀 더 조밀한 격자로 wfmap 타일 느낌을 보자
    X, Y, V = make_wafer_points(grid_side=21)

    # die 크기 10mm 가정 → 격자 인덱스 변환
    die_mm = 10.0
    df = pd.DataFrame({
        "MAP_COL": np.round(X / die_mm).astype(int),
        "MAP_ROW": np.round(Y / die_mm).astype(int),
        "THK": V,
    })
    print(f"Wafer data: N={len(df)}, "
          f"COL[{df.MAP_COL.min()}..{df.MAP_COL.max()}], "
          f"ROW[{df.MAP_ROW.min()}..{df.MAP_ROW.max()}]")

    # (1) num_heatmap — ax 기반, 기존 matplotlib figure에 삽입 가능
    fig1, ax = plt.subplots(figsize=(7, 6))
    wfmap.num_heatmap(
        df, "THK",
        cmap="jet",
        title=f"wfmap.num_heatmap — N={len(df)}",
        vsigma=3,
        ax=ax,
    )
    fig1.tight_layout()
    fig1.savefig(str(_DEBUG / "output_wfmap_num.png"), dpi=120)
    print(f"Saved → {_DEBUG}/output_wfmap_num.png")

    # (2) wafermap — 라이브러리 내장 레이아웃 (spec map 포함 느낌)
    wfmap.wafermap(
        df, "THK",
        title=f"wfmap.wafermap — N={len(df)}",
        vsigma=3,
    )
    fig2 = plt.gcf()
    fig2.savefig(str(_DEBUG / "output_wfmap_full.png"), dpi=120)
    print(f"Saved → {_DEBUG}/output_wfmap_full.png")


if __name__ == "__main__":
    main()
