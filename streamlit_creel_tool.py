import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
import holidays
import calendar
import altair as alt

# ----------------------------------
# 1. Sampling Calendar Generator
# ----------------------------------
def generate_sampling_calendar(start_date, end_date):
    sampling_days = []
    month_starts = pd.date_range(start_date, end_date, freq='MS')
    for dt in month_starts:
        y, m = dt.year, dt.month
        month_dates = [d for d in calendar.Calendar().itermonthdates(y, m) if d.month == m]
        weekdays = [d for d in month_dates if d.weekday() < 5]
        weekends = [d for d in month_dates if d.weekday() >= 5]
        wd_sample = list(np.random.choice(weekdays, min(3, len(weekdays)), replace=False)) if weekdays else []
        we_sample = list(np.random.choice(weekends, min(3, len(weekends)), replace=False)) if weekends else []
        sampling_days.extend(wd_sample + we_sample)
    return sorted({d for d in sampling_days})

# ----------------------------------
# 2. Preprocessing Functions
# ----------------------------------
def preprocess_contact(df):
    # build date
    if {'year','month','day'}.issubset(df.columns):
        df['date'] = pd.to_datetime(df[['year','month','day']])
    else:
        df['date'] = pd.to_datetime(df['date'])
    df = df.rename(columns={'num_ind':'anglers'})
    df['effort'] = pd.to_numeric(df['effort'], errors='coerce')
    df['anglers'] = pd.to_numeric(df['anglers'], errors='coerce')
    df = df.dropna(subset=['date','effort','anglers'])
    return df[['date','effort','anglers']]


def preprocess_fish(df):
    # build date
    if {'Year','Month','Day'}.issubset(df.columns):
        df['date'] = pd.to_datetime(df[['Year','Month','Day']])
    else:
        df['date'] = pd.to_datetime(df['date'])
    df['species'] = df['species']
    df['length'] = pd.to_numeric(df['length'], errors='coerce')
    df['catch'] = 1
    df = df.dropna(subset=['date','species','length'])
    return df[['date','species','length','catch']]


def preprocess_count(df):
    # build date
    if {'Year','Month','Day'}.issubset(df.columns):
        df['date'] = pd.to_datetime(df[['Year','Month','Day']])
    else:
        df['date'] = pd.to_datetime(df['date'])
    # identify method columns
    methods = [col for col in df.columns if col.lower() in ['boat','shore','tube','ice']]
    for m in methods:
        df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0)
    return df[['date'] + methods]

# ----------------------------------
# 3. Main App
# ----------------------------------
def main():
    st.title("Creel Survey Scheduler & Analyzer")
    mode = st.sidebar.radio("Mode", ["Calendar","Analysis"])

    if mode == "Calendar":
        st.header("📅 Sampling Calendar")
        start = st.sidebar.date_input("Start Date", date.today())
        end = st.sidebar.date_input("End Date", date.today())
        if start > end:
            st.sidebar.error("Start must be before End.")
            return
        days = generate_sampling_calendar(start, end)
        sel_month = st.sidebar.selectbox("Select Month", sorted({d.strftime('%Y-%m') for d in days}))
        y, m = map(int, sel_month.split('-'))
        sset = {d.strftime('%Y-%m-%d') for d in days}
        st.markdown(f"### {calendar.month_name[m]} {y}")
        matrix = calendar.monthcalendar(y, m)
        html = '<table style="border-collapse: collapse; width: 100%;">'
        html += '<tr>' + ''.join(f'<th style="padding:5px;border:1px solid #ddd">{wd}</th>' for wd in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']) + '</tr>'
        for wk in matrix:
            html += '<tr>'
            for day in wk:
                if day == 0:
                    html += '<td style="padding:10px;border:1px solid #ddd;background:#f0f0f0"></td>'
                else:
                    dstr = date(y, m, day).strftime('%Y-%m-%d')
                    style = 'background:#c6f7d0' if dstr in sset else 'background:white'
                    html += f'<td style="padding:10px;border:1px solid #ddd;{style};text-align:center">{day}</td>'
            html += '</tr>'
        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)

    else:
        st.header("🔍 Data QC & Analysis")
        st.sidebar.header("Upload Raw Excel Files")
        up_con = st.sidebar.file_uploader("Contact Info Excel", type=['xlsx'], key='c')
        up_cnt = st.sidebar.file_uploader("Count Data Excel", type=['xlsx'], key='n')
        up_spc = st.sidebar.file_uploader("Species Composition Excel", type=['xlsx'], key='s')

        if not up_con or not up_spc:
            st.info("Please upload both Contact Info and Species Composition files.")
            return

        # load & preprocess
        contact_df = preprocess_contact(pd.read_excel(up_con))
        fish_df = preprocess_fish(pd.read_excel(up_spc))
        method_counts = None
        if up_cnt:
            cnt_raw = pd.read_excel(up_cnt)
            cnt_df = preprocess_count(cnt_raw)
            # merge total catch into contact for consistency if needed
            contact_df = contact_df.merge(cnt_df.assign(total_catch=cnt_df[[c for c in cnt_df.columns if c!='date']].sum(axis=1)), on='date', how='left')
            # prepare method summary
            melt = cnt_df.melt(id_vars=['date'], var_name='method', value_name='catch')
            method_counts = melt.groupby('method')['catch'].sum().reset_index()

        # QC summary
        st.subheader("QC Summary")
        st.write(f"Contact rows: {len(contact_df)}")
        st.write(f"Fish rows: {len(fish_df)}")

        # Summaries
        # Daily
        csum = contact_df.groupby('date').agg(total_effort=('effort','sum')).reset_index()
        fsum = fish_df.groupby('date').agg(total_catch=('catch','sum')).reset_index()
        summary = pd.merge(csum, fsum, on='date', how='outer').fillna(0)
        summary['CPUE'] = summary['total_catch'] / summary['total_effort'].replace(0, np.nan)
        # Monthly
        summary['month'] = summary['date'].dt.to_period('M').dt.to_timestamp()
        monthly = summary.groupby('month').agg(monthly_effort=('total_effort','sum'),
                                               monthly_catch=('total_catch','sum')).reset_index()
        monthly['monthly_cpue'] = monthly['monthly_catch'] / monthly['monthly_effort'].replace(0, np.nan)

        # Overall
        total_effort = summary['total_effort'].sum()
        total_catch = summary['total_catch'].sum()
        avg_cpue = total_catch / total_effort if total_effort>0 else np.nan

        st.subheader("Summary Statistics")
        view = st.selectbox("Choose View", ["Overall","Monthly","Catch by Method","Species-Method"])

        if view == "Overall":
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Effort", f"{total_effort:.1f}")
            col2.metric("Total Catch", f"{total_catch:.0f}")
            col3.metric("Average CPUE", f"{avg_cpue:.2f}")

        elif view == "Monthly":
            bar_month = alt.Chart(monthly).mark_bar().encode(
                x='month:T', y='monthly_catch:Q', tooltip=['monthly_effort','monthly_cpue']
            ).properties(title='Monthly Total Catch')
            st.altair_chart(bar_month, use_container_width=True)

        elif view == "Catch by Method":
            if method_counts is None:
                st.error("Please upload a Count Data file to view Catch by Method.")
            else:
                bar_meth = alt.Chart(method_counts).mark_bar().encode(
                    x='method:N', y='catch:Q', color='method:N'
                ).properties(title='Catch by Method')
                st.altair_chart(bar_meth, use_container_width=True)

        else:  # Species-Method breakdown
            if 'method' in fish_df.columns and not fish_df['method'].isna().all():
                spm = fish_df.groupby(['species','method']).agg(catch=('catch','sum')).reset_index()
                species = st.selectbox("Select Species", spm['species'].unique().tolist())
                spf = spm[spm['species']==species]
                bar_sp = alt.Chart(spf).mark_bar().encode(
                    x='method:N', y='catch:Q', color='method:N'
                ).properties(title=f"{species} Catch by Method")
                st.altair_chart(bar_sp, use_container_width=True)
            else:
                st.error("Species file lacks method info. Method breakdown requires a Count Data upload.")

if __name__ == '__main__':
    main()


