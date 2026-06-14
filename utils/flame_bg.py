"""
像素火焰背景组件 — 田字格像素火焰
每个像素块之间有清晰的网格间隙，像马赛克/播放器声波效果
纯 CSS 动画，自包含在 iframe 内
"""

import streamlit as st
import random


def render_flame_banner():
    """
    田字格像素火焰横幅
    - 单元格 20px，像素块 16px，间隙 4px 清晰可见
    - 深色网格背景，像素块放置于格内
    - 每块独立上下浮动动画
    - 方形火花像素
    """
    st.html(_build_flame_html())


@st.cache_data(ttl=3600, show_spinner=False)
def _build_flame_html() -> str:
    """生成火焰 HTML（缓存 1 小时，纯 CSS 动画永不变化）。"""
    random.seed(42)

    CELL = 20      # 每格大小（像素 + 间隙）
    PX = 16        # 实际像素块大小
    BANNER_H = 80
    COLS = 33      # 约 660 / 20
    MAX_ROW = BANNER_H // CELL  # 4 层

    # --- 每列随机参数 ---
    columns = []
    for _ in range(COLS):
        cols = {}
        cols['rows'] = random.randint(2, MAX_ROW + 1)  # 2~5层
        cols['delay'] = round(random.uniform(0, 3.14), 2)
        cols['speed'] = round(random.uniform(0.7, 1.3), 2)
        columns.append(cols)

    # --- 像素块 HTML ---
    pixels = []
    for ci, col in enumerate(columns):
        for row in range(col['rows']):
            progress = row / MAX_ROW
            if progress < 0.3:
                r, g, b = 200, 45, 15   # 暗红
            elif progress < 0.6:
                r, g, b = 250, 95, 30   # 橙
            elif progress < 0.8:
                r, g, b = 245, 165, 40  # 黄
            else:
                r, g, b = 255, 225, 110 # 亮黄

            l = ci * CELL
            bot = row * CELL
            delay = round(col['delay'] + row * 0.18, 2)
            dur = round(0.45 * col['speed'], 2)

            pixels.append(
                f'<i class="px" style="'
                f'left:{l}px;bottom:{bot}px;'
                f'background:rgb({r},{g},{b});'
                f'animation-delay:{delay}s;'
                f'animation-duration:{dur}s;'
                f'"></i>'
            )

    # --- 方形火花 ---
    sparks = []
    for _ in range(30):
        ci = random.randint(0, COLS - 1)
        l = ci * CELL + random.randint(-3, 3)
        bot = columns[ci]['rows'] * CELL + random.randint(0, 2) * CELL
        sz = random.randint(6, 12)
        dur = round(random.uniform(2.0, 4.0), 2)
        delay = round(random.uniform(0, 3.0), 2)

        sparks.append(
            f'<i class="sp" style="'
            f'left:{l}px;bottom:{bot}px;'
            f'width:{sz}px;height:{sz}px;'
            f'animation-duration:{dur}s;'
            f'animation-delay:{delay}s;'
            f'"></i>'
        )

    # --- 自包含 HTML ---
    flame_html = f"""<style>
        body{{margin:0;padding:0;background:transparent;overflow:hidden;}}
        .banner{{
            width:100%;height:{BANNER_H}px;position:relative;overflow:hidden;
            /* 透明背景，继承页面底色 */
            background:transparent;
        }}
        .px{{
            position:absolute;
            width:{PX}px;height:{PX}px;
            /* 不加任何阴影，间隙由背景色自然露出 */
            animation:flt 0.5s infinite alternate ease-in-out;
        }}
        @keyframes flt{{
            0%{{transform:translateY(0px);opacity:.70;}}
            25%{{transform:translateY(-7px);opacity:1.0;}}
            60%{{transform:translateY(-2px);opacity:.88;}}
            100%{{transform:translateY(1px);opacity:.72;}}
        }}
        .sp{{
            position:absolute;
            background:rgba(255,210,50,.85);
            animation:rise 2.8s infinite ease-out;
        }}
        @keyframes rise{{
            0%{{transform:translateY(0) scale(1);opacity:.9;}}
            20%{{transform:translateY(-12px) scale(1.15);opacity:.7;}}
            55%{{transform:translateY(-32px) scale(.55);opacity:.22;}}
            100%{{transform:translateY(-55px) scale(.2);opacity:0;}}
        }}
    </style>
    <div class="banner">
        {''.join(pixels)}
        {''.join(sparks)}
    </div>"""

    return flame_html


def add_flame_css():
    """标题渐变"""
    css = """<style>
    h1{
        background:linear-gradient(90deg,#FF6B35,#F7C948)!important;
        -webkit-background-clip:text!important;
        -webkit-text-fill-color:transparent!important;
        background-clip:text!important;
    }
    </style>"""
    st.markdown(css, unsafe_allow_html=True)


def render_flame_sidebar():
    """侧边栏底部田字格小火焰"""

    CELL, PX = 12, 10
    COLS, ROWS, H = 18, 4, 4 * CELL

    random.seed(99)
    parts = []
    for ci in range(COLS):
        rows = random.randint(1, ROWS)
        for r in range(rows):
            progress = r / ROWS
            if progress < 0.3:   c = "200,45,15"
            elif progress < 0.6: c = "250,95,30"
            elif progress < 0.8: c = "245,165,40"
            else:                c = "255,225,110"
            delay = round(random.uniform(0, 0.6), 2)
            dur = round(random.uniform(0.45, 0.65), 2)
            parts.append(
                f'<i class="px" style="left:{ci*CELL}px;bottom:{r*CELL}px;'
                f'background:rgb({c});animation-delay:{delay}s;'
                f'animation-duration:{dur}s;"></i>'
            )

    html_str = f"""<style>
        body{{margin:0;padding:0;background:transparent;overflow:hidden;}}
        .banner{{width:100%;height:{H}px;position:relative;overflow:hidden;background:transparent;}}
        .px{{
            position:absolute;width:{PX}px;height:{PX}px;
            animation:flt 0.5s infinite alternate ease-in-out;
        }}
        @keyframes flt{{
            0%{{transform:translateY(0px);opacity:.65;}}
            100%{{transform:translateY(-3px);opacity:.95;}}
        }}
    </style><div class="banner">{''.join(parts)}</div>"""

    st.html(html_str)
