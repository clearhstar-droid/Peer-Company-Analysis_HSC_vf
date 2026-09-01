"""글로벌 철강 동종사 재무 대시보드 — Streamlit 버전.

현대제철 회계팀 내부용. 국내 3사(DART)·미국 3사(SEC EDGAR) 실시간 데이터를
분기 단위로 병합하고, 부족한 분기만 샘플 데이터로 채운다. 상세 배경은
README.md 참고.
"""

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from lib.chat_context import build_chat_context
from lib.companies import COMPANIES, COMPANY_MAP, QUARTERS, YEARS
from lib.dataset import load_dataset
from lib.finance import format_krw, format_percent, get_annual_lines, get_quarter_lines

# Reuse the Next.js app's .env one directory up when running locally from
# this repo (DART_API_KEY, OPENAI_API_KEY, ...). On Streamlit Cloud there is
# no .env at all — secrets come from st.secrets instead (bridged below).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")
# Streamlit Cloud secrets -> environment, so lib/ modules (plain os.environ
# readers, no Streamlit dependency) work the same locally and deployed.
if hasattr(st, "secrets"):
    try:
        for key, value in st.secrets.items():
            os.environ.setdefault(key, str(value))
    except Exception:  # noqa: BLE001 - no secrets.toml locally is fine
        pass

st.set_page_config(page_title="글로벌 철강 동종사 재무 대시보드", page_icon="🔩", layout="wide")

PALETTE = ["#b5502d", "#3f7d58", "#3b6db2", "#8a5fb2", "#b28a3b", "#4a9aa0"]

CSS = """
<style>
:root{
  --bg:#f3f4f0; --surface:#ffffff; --surface-2:#eaebe5;
  --ink:#1b2430; --ink-soft:#57616b; --ink-faint:#8a9198;
  --line:#dbded4; --accent:#b5502d; --accent-ink:#7a3419; --accent-soft:#f1e1d4;
  --pos:#3f7d58; --neg:#b23b3b;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#14181b; --surface:#1b2124; --surface-2:#21272a;
    --ink:#e9eae4; --ink-soft:#aab2a9; --ink-faint:#7a8279;
    --line:#2c3336; --accent:#e0895d; --accent-ink:#f2c0a0; --accent-soft:#332419;
    --pos:#6fbf8b; --neg:#e08080;
  }
}
.kpi-card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;background:var(--surface);margin-bottom:10px;}
.kpi-card .name{font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:6px;}
.kpi-card .dot{width:9px;height:9px;border-radius:50%;display:inline-block;}
.kpi-row{display:flex;justify-content:space-between;font-size:13.5px;padding:2px 0;}
.kpi-row .label{color:var(--ink-faint);}
.delta{font-size:11px;padding:1px 6px;border-radius:100px;margin-left:6px;}
.delta.pos{color:var(--pos);background:color-mix(in srgb, var(--pos) 15%, transparent);}
.delta.neg{color:var(--neg);background:color-mix(in srgb, var(--neg) 15%, transparent);}
.tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:100px;background:var(--surface-2);color:var(--ink-soft);border:1px solid var(--line);margin:2px 4px 2px 0;}
.tag.accent{background:var(--accent-soft);color:var(--accent-ink);}
.faq-card{border:1px solid var(--line);border-radius:8px;padding:12px 14px;background:var(--surface);height:100%;}
.faq-card .q{font-weight:700;margin-bottom:6px;}
.faq-card .a{font-size:12.5px;color:var(--ink-soft);}
.sample-banner{font-size:12px;color:var(--accent-ink);background:var(--accent-soft);border-radius:100px;padding:4px 12px;display:inline-block;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner="공식 API에서 데이터 조회 중…")
def cached_dataset():
    records, sources = load_dataset()
    return records, sources


def get_line_for(quarter_lines, annual_lines, company_id, year, quarter, mode):
    pool = annual_lines if mode == "annual" else quarter_lines
    for l in pool:
        if l.company_id == company_id and l.year == year and (mode == "annual" or l.quarter == quarter):
            return l
    return None


def previous_period(year, quarter, mode):
    if mode == "annual":
        return year - 1, 4
    if quarter == 1:
        return year - 1, 4
    return year, quarter - 1


def yoy_period(year, quarter):
    return year - 1, quarter


# ---------------------------------------------------------------- data ----
records, sources = cached_dataset()
quarter_lines = get_quarter_lines(records)
annual_lines = get_annual_lines(quarter_lines)

# ------------------------------------------------------------- header -----
col_title, col_banner = st.columns([3, 1])
with col_title:
    st.caption("HYUNDAI STEEL · ACCOUNTING TEAM")
    st.title("글로벌 철강 동종사 재무 대시보드")
with col_banner:
    st.markdown(
        '<div style="text-align:right;padding-top:28px;">'
        '<span class="sample-banner">DART · SEC EDGAR 실시간 연동 (일부 분기는 샘플 데이터 보완)</span>'
        "</div>",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------ controls ----
if "selected_companies" not in st.session_state:
    st.session_state.selected_companies = [c.id for c in COMPANIES]

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        selected = st.multiselect(
            "비교 기업",
            options=[c.id for c in COMPANIES],
            default=st.session_state.selected_companies,
            format_func=lambda cid: COMPANY_MAP[cid].name_ko + (" · 자사" if COMPANY_MAP[cid].is_self else ""),
        )
        st.session_state.selected_companies = selected or [COMPANIES[0].id]
    with c2:
        mode_label = st.radio("기간", ["분기", "연간"], horizontal=True, label_visibility="visible")
        mode = "annual" if mode_label == "연간" else "quarter"
    with c3:
        year = st.selectbox("연도", YEARS, index=len(YEARS) - 1)
    with c4:
        quarter = st.selectbox("분기", QUARTERS, index=len(QUARTERS) - 1, disabled=(mode == "annual"))

companies = st.session_state.selected_companies

# source status badges
badge_html = ""
error_notes = []
for cid in companies:
    info = sources.get(cid)
    if not info:
        continue
    label = {"sec-edgar": "SEC EDGAR", "dart": "DART", "mock": "샘플"}[info.provider]
    status_label = {"live": "실시간", "partial": "실시간 일부", "mock": "샘플", "error": "연동 오류"}[info.status]
    cls = "tag accent" if info.status in ("live", "partial") else "tag"
    extra = f" ({info.live_quarter_count}/{info.total_quarter_count}분기)" if info.status == "partial" else ""
    title = " / ".join(info.notes).replace('"', "'")
    badge_html += f'<span class="{cls}" title="{title}">{COMPANY_MAP[cid].name_ko} · {label} {status_label}{extra}</span>'
    if info.notes:
        error_notes.append((COMPANY_MAP[cid].name_ko, info.notes))
st.markdown(badge_html, unsafe_allow_html=True)

if error_notes:
    with st.expander("⚠ 연동 오류/알림 상세 보기"):
        for name, notes in error_notes:
            for n in notes:
                st.write(f"- **{name}**: {n}")

st.divider()

# ------------------------------------------------------------ KPI cards ---
st.subheader("핵심 지표 요약")
compare_mode = st.radio("증감 비교 기준", ["전년동기대비", "전기대비"], horizontal=True, label_visibility="collapsed")

kpi_cols = st.columns(min(len(companies), 4) or 1)
for i, cid in enumerate(companies):
    current = get_line_for(quarter_lines, annual_lines, cid, year, quarter, mode)
    if current is None:
        continue
    if compare_mode == "전기대비" and mode == "quarter":
        py, pq = previous_period(year, quarter, mode)
    else:
        py, pq = yoy_period(year, quarter)
    prev = get_line_for(quarter_lines, annual_lines, cid, py, pq, mode)

    revenue_delta = (current.krw.revenue / prev.krw.revenue - 1) if prev and prev.krw.revenue else None
    net_delta = (current.krw.net_income / prev.krw.net_income - 1) if prev and prev.krw.net_income else None

    company = COMPANY_MAP[cid]
    color = PALETTE[i % len(PALETTE)]

    def delta_html(v):
        if v is None:
            return ""
        cls = "pos" if v >= 0 else "neg"
        return f'<span class="delta {cls}">{format_percent(v)}</span>'

    with kpi_cols[i % len(kpi_cols)]:
        st.markdown(
            f"""<div class="kpi-card">
<div class="name"><span class="dot" style="background:{color}"></span>{company.name_ko}{' <span class="tag accent">자사</span>' if company.is_self else ''}</div>
<div class="kpi-row"><span class="label">매출액</span><span>{format_krw(current.krw.revenue)}{delta_html(revenue_delta)}</span></div>
<div class="kpi-row"><span class="label">영업이익</span><span>{format_krw(current.krw.operating_income)} ({format_percent(current.operating_margin)})</span></div>
<div class="kpi-row"><span class="label">당기순이익</span><span>{format_krw(current.krw.net_income)}{delta_html(net_delta)}</span></div>
</div>""",
            unsafe_allow_html=True,
        )

st.divider()

# -------------------------------------------------------- comparison chart-
st.subheader("계정별 비교")
st.caption("단위 원화(KRW) 환산")

ACCOUNT_CHOICES = {
    "매출액": "revenue",
    "영업이익": "operating_income",
    "당기순이익": "net_income",
    "자산": "assets",
    "자본": "equity",
}
chosen_label = st.radio("계정", list(ACCOUNT_CHOICES.keys()), horizontal=True, label_visibility="collapsed")
chosen_key = ACCOUNT_CHOICES[chosen_label]

chart_rows = []
for i, cid in enumerate(companies):
    line = get_line_for(quarter_lines, annual_lines, cid, year, quarter, mode)
    if line is None:
        continue
    val = getattr(line.krw, chosen_key)
    chart_rows.append({"name": COMPANY_MAP[cid].name_ko, "value": val / 1_000_000, "color": PALETTE[i % len(PALETTE)]})

if chart_rows:
    fig = go.Figure(
        go.Bar(
            x=[r["name"] for r in chart_rows],
            y=[r["value"] for r in chart_rows],
            marker_color=[r["color"] for r in chart_rows],
            text=[f"{r['value']:.1f}조" for r in chart_rows],
            textposition="outside",
        )
    )
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="조원",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ------------------------------------------------------------ table -------
st.subheader("상세 비교 테이블")
st.caption("매출액~자본 12개 계정 + 마진율")

ACCOUNTS = [
    ("매출액", "revenue"),
    ("매출원가", "cogs"),
    ("매출총이익", "gross_profit"),
    ("판관비", "sga_expense"),
    ("영업이익", "operating_income"),
    ("영업외수익", "non_operating_income"),
    ("영업외비용", "non_operating_expense"),
    ("세전이익", "pretax_income"),
    ("당기순이익", "net_income"),
    ("자산", "assets"),
    ("부채", "liabilities"),
    ("자본", "equity"),
]

table_data = {"계정과목": [label for label, _ in ACCOUNTS]}
for cid in companies:
    line = get_line_for(quarter_lines, annual_lines, cid, year, quarter, mode)
    table_data[COMPANY_MAP[cid].name_ko] = [
        format_krw(getattr(line.krw, key)) if line else "—" for _, key in ACCOUNTS
    ]

margin_rows = {"매출총이익률": "gross_margin", "영업이익률": "operating_margin", "순이익률": "net_margin"}
df = pd.DataFrame(table_data)
margin_df_rows = []
for label, key in margin_rows.items():
    row = {"계정과목": label}
    for cid in companies:
        line = get_line_for(quarter_lines, annual_lines, cid, year, quarter, mode)
        row[COMPANY_MAP[cid].name_ko] = format_percent(getattr(line, key)) if line else "—"
    margin_df_rows.append(row)
df = pd.concat([df, pd.DataFrame(margin_df_rows)], ignore_index=True)
st.dataframe(df, hide_index=True, use_container_width=True)

st.divider()

# -------------------------------------------------------- cost drilldown --
st.subheader("비용 Drill-down")
st.caption("상각비 · 인건비 · 원재료비 · 금융비용")

focus = st.radio(
    "Drill-down 대상 기업",
    companies,
    format_func=lambda cid: COMPANY_MAP[cid].name_ko,
    horizontal=True,
    label_visibility="collapsed",
)
focus_line = get_line_for(quarter_lines, annual_lines, focus, year, quarter, mode)

if focus_line:
    cb = focus_line.krw.cost_breakdown
    cogs_other = max(0.0, focus_line.krw.cogs - cb.raw_material_in_cogs - cb.depreciation_in_cogs - cb.labor_in_cogs)
    sga_other = max(0.0, focus_line.krw.sga_expense - cb.depreciation_in_sga - cb.labor_in_sga)
    non_op_other = max(0.0, focus_line.krw.non_operating_expense - cb.finance_cost_in_non_op_expense)

    def stacked_bar(title, total, segments):
        fig = go.Figure()
        for seg_label, seg_val, seg_color in segments:
            if total > 0 and seg_val > 0:
                fig.add_trace(
                    go.Bar(
                        y=[title],
                        x=[seg_val / total * 100],
                        name=seg_label,
                        orientation="h",
                        marker_color=seg_color,
                        hovertemplate=f"{seg_label}: %{{x:.1f}}%<extra></extra>",
                    )
                )
        fig.update_layout(
            barmode="stack",
            height=90,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            xaxis=dict(visible=False, range=[0, 100]),
            yaxis=dict(visible=False),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    seg_colors = {"원재료비": "#b5502d", "상각비": "#6b7d3f", "인건비": "#3b6db2", "금융비용": "#8a5fb2", "기타": "#9aa0a6"}

    st.markdown(f"**매출원가** {format_krw(focus_line.krw.cogs)}")
    st.plotly_chart(
        stacked_bar(
            "COGS",
            focus_line.krw.cogs,
            [
                ("원재료비", cb.raw_material_in_cogs, seg_colors["원재료비"]),
                ("상각비", cb.depreciation_in_cogs, seg_colors["상각비"]),
                ("인건비", cb.labor_in_cogs, seg_colors["인건비"]),
                ("기타", cogs_other, seg_colors["기타"]),
            ],
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.markdown(f"**판관비** {format_krw(focus_line.krw.sga_expense)}")
    st.plotly_chart(
        stacked_bar(
            "SGA",
            focus_line.krw.sga_expense,
            [
                ("상각비", cb.depreciation_in_sga, seg_colors["상각비"]),
                ("인건비", cb.labor_in_sga, seg_colors["인건비"]),
                ("기타", sga_other, seg_colors["기타"]),
            ],
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.markdown(f"**영업외비용** {format_krw(focus_line.krw.non_operating_expense)}")
    st.plotly_chart(
        stacked_bar(
            "NonOp",
            focus_line.krw.non_operating_expense,
            [
                ("금융비용", cb.finance_cost_in_non_op_expense, seg_colors["금융비용"]),
                ("기타", non_op_other, seg_colors["기타"]),
            ],
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    legend = "".join(
        f'<span class="tag" style="border-color:{c}"><span style="color:{c}">●</span> {l}</span>'
        for l, c in seg_colors.items()
    )
    st.markdown(legend, unsafe_allow_html=True)

    if any(
        sources[cid].provider != "mock" for cid in companies if cid in sources
    ):
        st.caption("DART·SEC EDGAR 공시는 원재료비·인건비를 별도 계정으로 제공하지 않는 경우가 많아 '기타'에 포함됩니다.")

    st.markdown("##### 동종사 원재료비율 비교 (매출액 대비)")
    ratio_rows = []
    for i, cid in enumerate(companies):
        line = get_line_for(quarter_lines, annual_lines, cid, year, quarter, mode)
        if not line or not line.krw.revenue:
            continue
        ratio = line.krw.cost_breakdown.raw_material_in_cogs / line.krw.revenue * 100
        ratio_rows.append({"name": COMPANY_MAP[cid].name_ko, "value": ratio, "color": PALETTE[i % len(PALETTE)]})
    if ratio_rows:
        fig2 = go.Figure(
            go.Bar(
                x=[r["value"] for r in ratio_rows],
                y=[r["name"] for r in ratio_rows],
                orientation="h",
                marker_color=[r["color"] for r in ratio_rows],
                text=[f"{r['value']:.1f}%" for r in ratio_rows],
                textposition="outside",
            )
        )
        fig2.update_layout(
            height=max(150, len(ratio_rows) * 40),
            margin=dict(l=0, r=20, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ------------------------------------------------------------------ FAQ ---
st.subheader("FAQ 라이브러리")
st.caption("챗봇 반복 질문 임베딩 클러스터링 (샘플)")

SEED_FAQS = [
    ("포스코와 현대제철의 최근 영업이익률 차이는?",
     "상단에서 두 회사를 선택하면 분기별 영업이익률이 표에 자동 표시됩니다. 원재료 가격 변동에 따른 마진 사이클 차이를 함께 확인하세요.",
     47, "수익성"),
    ("Nucor의 원재료비율이 낮은 이유는?",
     "Nucor는 전기로(EAF) 기반 미니밀 구조로 철스크랩을 주원료로 사용해 고로사 대비 원재료비 비중이 낮게 나타납니다.",
     31, "원가구조"),
    ("동국제강은 왜 일부 분기가 비어있나?",
     "동국제강은 2023년 인적분할로 신설된 법인이라, 분할 이전 분기는 DART에 이 법인 명의의 공시 자체가 없습니다.",
     19, "데이터정의"),
    ("원화 환산에 적용한 환율 기준은?",
     "현재는 조회 시점의 단일 환율(무료 API 기준)을 모든 분기에 동일하게 적용합니다. 분기별 시점 환율 적용은 다음 개선 과제입니다.",
     12, "환율"),
]

faq_cols = st.columns(4)
for i, (q, a, count, tag) in enumerate(SEED_FAQS):
    with faq_cols[i % 4]:
        st.markdown(
            f"""<div class="faq-card"><div class="q">{q}</div><div class="a">{a}</div>
<div style="margin-top:10px;"><span class="tag">질문 {count}회</span><span class="tag accent">{tag}</span></div></div>""",
            unsafe_allow_html=True,
        )

st.divider()

# -------------------------------------------------------------- chatbot ---
st.subheader("AI 챗봇")
st.caption("선택된 기업·기간 데이터를 근거로 답변합니다 (OpenAI 연동)")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": '안녕하세요. 현재 대시보드에 로드된 재무 데이터에 대해 질문해주세요. 예: "포스코 대비 현대제철 영업이익률 차이는?"'}
    ]

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

SYSTEM_PROMPT = """당신은 현대제철 회계팀이 사용하는 "글로벌 철강 동종사 재무 대시보드"의 분석 도우미입니다.
아래 CONTEXT에 주어진 재무 데이터(원화 환산 기준)만 근거로 답하세요.
CONTEXT에 없는 수치나 회사에 대한 질문에는 추측하지 말고 "현재 대시보드에 로드된 데이터에는 없습니다"라고 명확히 답하세요.
답변은 한국어로, 간결하게, 근거가 된 회사·계정·기간을 함께 언급하세요.
매출총이익률·영업이익률·순이익률 등 비율은 CONTEXT에 이미 계산되어 괄호로 제공되어 있으니 그 값을 그대로 인용하세요.
"조원"·"억원" 등으로 서식화된 문자열에서 숫자를 다시 뽑아 나눗셈을 하지 마세요 — 조/억 단위를 착각해 10배 단위로 틀린 값을 낼 수 있습니다.
각 기업 항목에 "출처: DART/SEC EDGAR 실제 데이터" 또는 "샘플(mock) 데이터"가 표시되어 있습니다 — 샘플 데이터로 답할 때는 실제 공시 수치가 아님을 함께 알려주세요."""


def ask_openai(question: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ".env 또는 Streamlit Secrets에 OPENAI_API_KEY가 설정되어 있지 않습니다."
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        context = build_chat_context(
            companies, mode, year, quarter,
            lambda cid, y, q, m: get_line_for(quarter_lines, annual_lines, cid, y, q, m),
            sources,
        )
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}"}]
        for m in st.session_state.chat_history[-8:]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})
        completion = client.chat.completions.create(model=model, temperature=0.2, messages=messages)
        return completion.choices[0].message.content or "응답을 생성하지 못했습니다."
    except Exception as err:  # noqa: BLE001
        return f"챗봇 응답 중 오류가 발생했습니다: {err}"


SUGGESTIONS = [
    "선택된 기업 중 영업이익률이 가장 높은 곳은?",
    "원재료비율이 가장 낮은 회사와 이유는?",
    "당기순이익이 전기 대비 가장 많이 늘어난 곳은?",
]
sug_cols = st.columns(len(SUGGESTIONS))
suggestion_clicked = None
for i, s in enumerate(SUGGESTIONS):
    if sug_cols[i].button(s, use_container_width=True, key=f"sug-{i}"):
        suggestion_clicked = s

user_input = st.chat_input("질문을 입력하세요")
question = suggestion_clicked or user_input

if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("답변 작성 중…"):
            reply = ask_openai(question)
        st.write(reply)
    st.session_state.chat_history.append({"role": "assistant", "content": reply})

st.divider()
st.caption("HYUNDAI STEEL · ACCOUNTING TEAM — INTERNAL DASHBOARD (DEMO)")
