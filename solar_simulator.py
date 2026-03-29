import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# 🚨 비밀번호 잠금 장치 시작
# ==========================================
password = st.text_input("시뮬레이터에 접속하려면 비밀번호를 입력하세요:", type="password")

if password != "khu22":  # "1234" 대신 원하는 비밀번호로 바꾸세요!
    st.warning("올바른 비밀번호를 입력해야 시뮬레이터가 작동합니다. 🔒")
    st.stop()  # 비밀번호가 틀리면 여기서 코드 실행을 멈추고 아래 화면을 안 보여줌!

st.title("태양광 시뮬레이터 테스트 화면")
st. write("정상적으로 실행됩니다!")

# ---------------------------
# 2. 사용자 입력 (UI)
# ---------------------------
st.sidebar.header("🔧 입력 설정")

panel_angle = st.sidebar.slider("패널 각도 (°)", 0, 90, 30)
time = st.sidebar.slider("시간 (시)", 0, 23, 12)

latitude = st.sidebar.slider("위도 (°)", 0, 60, 37)
day_of_year = st.sidebar.slider("날짜 (1~365)", 1, 365, 172)

weather = st.sidebar.selectbox("날씨", ["맑음", "흐림", "비"])

# ---------------------------
# 3. 태양 위치 계산
# ---------------------------
def solar_declination(day):
    return 23.45 * np.sin(np.radians(360 * (284 + day) / 365))

def solar_altitude(lat, decl, hour):
    hour_angle = (hour - 12) * 15
    altitude = np.degrees(
        np.arcsin(
            np.sin(np.radians(lat)) * np.sin(np.radians(decl)) +
            np.cos(np.radians(lat)) * np.cos(np.radians(decl)) * np.cos(np.radians(hour_angle))
        )
    )
    return max(0, altitude)

decl = solar_declination(day_of_year)
solar_alt = solar_altitude(latitude, decl, time)

# ---------------------------
# 4. 발전량 계산
# ---------------------------
def weather_factor(w):
    if w == "맑음":
        return 1.0
    elif w == "흐림":
        return 0.6
    else:
        return 0.3

def power_output(panel_angle, solar_alt, weather):
    theta = abs(panel_angle - (90 - solar_alt))
    return max(0, np.cos(np.radians(theta))) * weather_factor(weather)

current_power = power_output(panel_angle, solar_alt, weather)
efficiency = current_power * 100

# ---------------------------
# 5. AI 최적 각도 계산
# ---------------------------
def find_optimal_angle(solar_alt):
    return 90 - solar_alt

if st.sidebar.button("🤖 AI 최적 각도 적용"):
    panel_angle = find_optimal_angle(solar_alt)

# ---------------------------
# 6. 결과 출력 (숫자)
# ---------------------------
col1, col2 = st.columns(2)

with col1:
    st.metric("현재 발전량 (상대값)", f"{current_power:.2f}")

with col2:
    st.metric("효율 (%)", f"{efficiency:.1f}")

# ---------------------------
# 7. 그래프 생성 (핵심)
# ---------------------------
hours = np.arange(6, 18)

fixed_outputs = []
tracking_outputs = []

fixed_angle = panel_angle

for h in hours:
    alt = solar_altitude(latitude, decl, h)

    # 고정형
    fixed_outputs.append(power_output(fixed_angle, alt, weather))

    # 가변형 (AI 최적)
    optimal_angle = find_optimal_angle(alt)
    tracking_outputs.append(power_output(optimal_angle, alt, weather))

# ---------------------------
# 8. 그래프 출력
# ---------------------------
st.subheader("📈 발전량 비교 (고정형 vs 가변형)")

fig, ax = plt.subplots()

ax.plot(hours, fixed_outputs, label="고정형")
ax.plot(hours, tracking_outputs, label="가변형 (AI)")

ax.set_xlabel("시간")
ax.set_ylabel("발전량")
ax.legend()

st.pyplot(fig)

# ---------------------------
# 9. 총 발전량 비교
# ---------------------------
total_fixed = np.sum(fixed_outputs)
total_tracking = np.sum(tracking_outputs)

st.subheader("⚡ 총 발전량 비교")

col3, col4 = st.columns(2)

with col3:
    st.metric("고정형 총 발전량", f"{total_fixed:.2f}")

with col4:
    st.metric("가변형 총 발전량", f"{total_tracking:.2f}")

improvement = (total_tracking / total_fixed - 1) * 100 if total_fixed > 0 else 0

st.success(f"🚀 발전량 증가율: {improvement:.1f}%")

import matplotlib.pyplot as plt

# 윈도우 '맑은 고딕' 폰트 적용
plt.rcParams['font.family'] = 'Malgun Gothic'

# 마이너스(-) 기호 깨짐 방지
plt.rcParams['axes.unicode_minus'] = False

