import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. 데이터베이스 설정 ---
conn = sqlite3.connect('classroom_v9.db', check_same_thread=False)
c = conn.cursor()

# 테이블 생성
c.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, pw TEXT, name TEXT, balance REAL, status TEXT, role TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS portfolio (name TEXT, stock TEXT, quantity INTEGER, avg_price REAL, PRIMARY KEY(name, stock))')
c.execute('CREATE TABLE IF NOT EXISTS stocks (name TEXT PRIMARY KEY, price REAL, sector TEXT, description TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS price_history (stock TEXT, price REAL, timestamp DATETIME)')
c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, stock TEXT, content TEXT, timestamp DATETIME)')

# 초기 설정 (관리자 비번: admin777)
c.execute('INSERT OR IGNORE INTO settings VALUES ("currency", "미소")')
c.execute('INSERT OR IGNORE INTO users VALUES ("admin", "admin777", "관리자선생님", 0, "Active", "Admin")')
conn.commit()

# --- 2. 핵심 유틸리티 함수 ---
def get_setting(key):
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    res = c.fetchone()
    return res[0] if res else ""

def log_price(stock, price):
    c.execute('INSERT INTO price_history (stock, price, timestamp) VALUES (?, ?, ?)', (stock, price, datetime.now()))
    conn.commit()

def get_leaderboard():
    """현금 + 주식 가치를 합산한 전체 순위표 계산"""
    students = pd.read_sql('SELECT name, balance FROM users WHERE role="Student" AND status="Active"', conn)
    stocks_price = {r[0]: r[1] for r in c.execute('SELECT name, price FROM stocks').fetchall()}
    
    leaderboard = []
    for _, s in students.iterrows():
        # 해당 학생의 포트폴리오 가져오기
        portfolio = c.execute('SELECT stock, quantity FROM portfolio WHERE name=?', (s['name'],)).fetchall()
        stock_val = 0
        for stock_name, quantity in portfolio:
            cur_price = stocks_price.get(stock_name, 0)
            stock_val += (quantity * cur_price)
        
        total_assets = s['balance'] + stock_val
        leaderboard.append({
            "이름": s['name'],
            "현금": s['balance'],
            "주식자산": stock_val,
            "총자산": total_assets
        })
    
    if not leaderboard: return pd.DataFrame()
    return pd.DataFrame(leaderboard).sort_values(by="총자산", ascending=False).reset_index(drop=True)

# --- 3. UI 설정 및 세션 관리 ---
st.set_page_config(page_title="퍼플 9.0 경제 시스템", layout="wide")
currency = get_setting("currency")

if 'user_id' not in st.session_state: st.session_state.user_id = None
if 'view_stock' not in st.session_state: st.session_state.view_stock = None

# 사이드바 로그인
with st.sidebar:
    st.title(f"🏦 {currency} 거래소")
    if st.session_state.user_id is None:
        menu = st.radio("메뉴", ["로그인", "회원가입"])
        s_id = st.text_input("아이디")
        s_pw = st.text_input("비밀번호", type="password")
        if menu == "로그인" and st.button("접속"):
            c.execute('SELECT id, role, status, name FROM users WHERE id=? AND pw=?', (s_id, s_pw))
            user = c.fetchone()
            if user:
                if user[2] == 'Active' or user[1] == 'Admin':
                    st.session_state.user_id, st.session_state.user_role, st.session_state.user_name = user[0], user[1], user[3]
                    st.rerun()
                else: st.warning("승인이 필요합니다.")
            else: st.error("정보 불일치")
        elif menu == "회원가입":
            s_name = st.text_input("이름")
            if st.button("가입 신청"):
                try:
                    c.execute('INSERT INTO users VALUES (?, ?, ?, 100000, "Pending", "Student")', (s_id, s_pw, s_name))
                    conn.commit() ; st.success("신청 완료!")
                except: st.error("이미 존재하는 아이디")
    else:
        st.write(f"✅ **{st.session_state.user_name}**님 ({st.session_state.user_role})")
        if st.button("로그아웃"):
            st.session_state.clear() ; st.rerun()
        if st.session_state.view_stock and st.button("🏠 홈으로"):
            st.session_state.view_stock = None ; st.rerun()

# --- 4. 종목 상세 페이지 ---
if st.session_state.view_stock:
    stock_name = st.session_state.view_stock
    st.title(f"📈 {stock_name} 상세 정보")
    stock_info = c.execute('SELECT * FROM stocks WHERE name=?', (stock_name,)).fetchone()
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("📊 시세 그래프")
        history = pd.read_sql('SELECT price, timestamp FROM price_history WHERE stock=? ORDER BY timestamp ASC', conn, params=(stock_name,))
        if not history.empty:
            history['timestamp'] = pd.to_datetime(history['timestamp'])
            st.line_chart(history.set_index('timestamp'))
        st.info(f"**종목 설명:** {stock_info[3]}")

    with col2:
        st.subheader("📢 관련 뉴스")
        news = pd.read_sql('SELECT content, timestamp FROM news WHERE stock=? ORDER BY timestamp DESC', conn, params=(stock_name,))
        for _, n in news.iterrows():
            st.caption(f"📅 {n['timestamp']}")
            st.write(n['content'])
            st.divider()

# --- 5. 관리자 화면 ---
elif st.session_state.get('user_role') == "Admin":
    st.title("👨‍🏫 중앙 은행 관리자")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["👥 학생 관리", "🏢 종목/시세", "📢 뉴스 관리", "🏆 순위표", "⚙️ 설정"])
    
    with tab1:
        st.subheader("학생 목록 및 승인")
        u_df = pd.read_sql('SELECT id, name, balance, status FROM users WHERE role="Student" ORDER BY name ASC', conn)
        
        # 전체 선택 기능
        all_select = st.checkbox("전체 선택하기")
        u_df.insert(0, "선택", all_select)
        
        edited_df = st.data_editor(u_df, use_container_width=True, hide_index=True, key="admin_user_editor")
        selected_ids = edited_df[edited_df["선택"] == True]["id"].tolist()
        
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ 선택 승인"):
            for sid in selected_ids: c.execute('UPDATE users SET status="Active" WHERE id=?', (sid,))
            conn.commit() ; st.rerun()
        if c2.button("❌ 선택 삭제"):
            for sid in selected_ids: c.execute('DELETE FROM users WHERE id=?', (sid,))
            conn.commit() ; st.rerun()

        st.divider()
        st.subheader("💰 자산 일괄 조정 (송금 및 회수)")
        amt = st.number_input("조정 금액 (지급은 +, 회수는 -)", value=0, step=1000)
        col_b1, col_b2 = st.columns(2)
        if col_b1.button("💸 선택한 학생에게만 적용"):
            if not selected_ids: st.warning("대상을 선택하세요.")
            else:
                for sid in selected_ids:
                    c.execute('UPDATE users SET balance = balance + ? WHERE id=?', (amt, sid))
                conn.commit() ; st.success("반영 완료") ; st.rerun()
        if col_b2.button("🌍 승인된 전체 학생에게 적용"):
            c.execute('UPDATE users SET balance = balance + ? WHERE role="Student" AND status="Active"', (amt,))
            conn.commit() ; st.success("전체 반영 완료") ; st.rerun()

    with tab2: # 종목 상장 (커스텀 섹터)
        with st.form("add_s"):
            n1, n2, n3 = st.text_input("종목명"), st.number_input("시작가", value=1000), st.text_input("섹터 직접 입력")
            n4 = st.text_area("설명")
            if st.form_submit_button("상장"):
                c.execute('INSERT INTO stocks VALUES (?, ?, ?, ?)', (n1, n2, n3, n4))
                log_price(n1, n2) ; conn.commit() ; st.rerun()
        st.divider()
        for _, r in pd.read_sql('SELECT * FROM stocks', conn).iterrows():
            cc1, cc2, cc3 = st.columns([2,2,1])
            cc1.write(f"**{r['name']}** ({r['price']} {currency})")
            up_p = cc2.number_input("조정가", value=float(r['price']), key=f"up_{r['name']}")
            if cc3.button("변경", key=f"btn_{r['name']}"):
                c.execute('UPDATE stocks SET price=? WHERE name=?', (up_p, r['name']))
                log_price(r['name'], up_p) ; conn.commit() ; st.rerun()

    with tab3: # 뉴스 관리
        st.subheader("📢 종목별 뉴스 발행")
        stock_list = [r[0] for r in c.execute('SELECT name FROM stocks').fetchall()]
        with st.form("n_form"):
            t_s = st.selectbox("대상 종목", stock_list)
            t_c = st.text_area("뉴스 내용")
            if st.form_submit_button("발행"):
                c.execute('INSERT INTO news (stock, content, timestamp) VALUES (?, ?, ?)', 
                          (t_s, t_c, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit() ; st.success("발행됨")

    with tab4: # 관리자 순위표
        st.subheader("🏅 전체 자산 순위표")
        lb = get_leaderboard()
        if not lb.empty: 
            lb.index += 1
            st.table(lb)
        else: st.write("데이터가 없습니다.")

    with tab5: # 설정
        new_cur = st.text_input("화폐 명칭", value=currency)
        if st.button("저장"):
            c.execute('UPDATE settings SET value=? WHERE key="currency"', (new_cur,))
            conn.commit() ; st.rerun()

# --- 6. 학생 화면 ---
elif st.session_state.get('user_role') == "Student":
    st.title(f"💰 {st.session_state.user_name}님의 계좌")
    t1, t2, t3 = st.tabs(["📉 거래소", "💼 내 지갑", "🏆 순위표"])
    
    with t1:
        for _, r in pd.read_sql('SELECT * FROM stocks', conn).iterrows():
            if st.button(f"📊 {r['name']} | {r['price']} {currency} | {r['sector']}", use_container_width=True):
                st.session_state.view_stock = r['name'] ; st.rerun()
            
    with t2:
        bal = c.execute('SELECT balance FROM users WHERE id=?', (st.session_state.user_id,)).fetchone()[0]
        st.metric("현재 잔고", f"{bal:,.0f} {currency}")
        my_p = pd.read_sql('SELECT stock, quantity, avg_price FROM portfolio WHERE name=?', conn, params=(st.session_state.user_name,))
        if not my_p.empty: st.table(my_p)
        else: st.write("보유 주식 없음")

    with t3:
        st.subheader("🏅 우리 반 자산 순위")
        lb = get_leaderboard()
        if not lb.empty:
            lb.index += 1
            st.table(lb)

else:
    st.title("👋 안녕하세요! 대영재국 경제 시스템입니다.")
    st.info("왼쪽 사이드바에서 로그인하세요. 관리자 비번은 ???? 입니다.")