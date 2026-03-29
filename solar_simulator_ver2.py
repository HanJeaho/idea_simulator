import streamlit as st
import numpy as np
import matplotlib.pyplot as plt

# 🚨 비밀번호 잠금 장치 시작
# ==========================================
password = st.text_input("시뮬레이터에 접속하려면 비밀번호를 입력하세요:", type="password")

if password != "khu22":  # "1234" 대신 원하는 비밀번호로 바꾸세요!
    st.warning("올바른 비밀번호를 입력해야 시뮬레이터가 작동합니다. 🔒")
    st.stop()  # 비밀번호가 틀리면 여기서 코드 실행을 멈추고 아래 화면을 안 보여줌!

st.set_page_config(layout="wide")

st.title("🌞 AI 기반 가변형 태양광 도로 울타리 시뮬레이터")

# ---------------------------
# 1. 입력 (한글 UI)
# ---------------------------
st.sidebar.header("입력 설정")

panel_angle = st.sidebar.slider("패널 각도 (°)", 0, 90, 30)
time = st.sidebar.slider("시간 (시)", 0, 23, 12)

latitude = st.sidebar.slider("위도 (°)", 0, 60, 37)
day = st.sidebar.slider("날짜 (1~365)", 1, 365, 172)

weather = st.sidebar.selectbox("날씨", ["맑음", "흐림", "비"])
mode = st.sidebar.selectbox("추적 방식", ["연속 추적", "간헐 추적(1시간)"])

# ---------------------------
# 2. 태양 위치 계산
# ---------------------------
def declination(day):
    return 23.45 * np.sin(np.radians(360*(284+day)/365))

def solar_altitude(lat, decl, hour):
    h = (hour - 12)*15
    alt = np.degrees(
        np.arcsin(
            np.sin(np.radians(lat))*np.sin(np.radians(decl)) +
            np.cos(np.radians(lat))*np.cos(np.radians(decl))*np.cos(np.radians(h))
        )
    )
    return max(0, alt)

# ---------------------------
# 3. 날씨 보정
# ---------------------------
def weather_factor(w):
    if w == "맑음":
        return 1.0
    elif w == "흐림":
        return 0.6
    else:
        return 0.3

# ---------------------------
# 4. 발전량 모델
# ---------------------------
PANEL_AREA = 1.6
EFFICIENCY = 0.20
SOLAR_IRRADIANCE = 1000

def power(panel_angle, solar_alt, weather):
    theta = abs(panel_angle - (90 - solar_alt))
    return max(0, np.cos(np.radians(theta))) * PANEL_AREA * SOLAR_IRRADIANCE * EFFICIENCY * weather_factor(weather)

# ---------------------------
# 5. 모터 에너지 모델
# ---------------------------
MASS = 20
GRAVITY = 9.81
RADIUS = 0.8

def motor_energy(angle_change_deg):
    theta = np.radians(abs(angle_change_deg))
    torque = MASS * GRAVITY * RADIUS
    energy = torque * theta
    return energy / 3600  # Wh

# ---------------------------
# 6. AI 최적 각도
# ---------------------------
def optimal_angle(alt):
    return 90 - alt

current_alt = solar_altitude(latitude, declination(day), time)
current_opt_angle = optimal_angle(current_alt)

st.info(f"현재 시간 기준 AI 최적 각도: {current_opt_angle:.2f}°")

# ---------------------------
# 7. 시뮬레이션
# ---------------------------
hours = np.arange(6, 18)

fixed_output = []
tracking_output = []
motor_energy_total = 0

prev_angle = panel_angle

for h in hours:
    alt = solar_altitude(latitude, declination(day), h)

    fixed_output.append(power(panel_angle, alt, weather))

    opt_angle = optimal_angle(alt)
    tracking_output.append(power(opt_angle, alt, weather))

    if mode == "연속 추적":
        angle_diff = opt_angle - prev_angle
    else:
        angle_diff = opt_angle - panel_angle

    motor_energy_total += motor_energy(angle_diff)
    prev_angle = opt_angle

# ---------------------------
# 8. 그래프 1 (영어 유지)
# ---------------------------
st.subheader("발전량 비교 그래프")

fig1, ax1 = plt.subplots()

ax1.plot(hours, fixed_output, label="Fixed")
ax1.plot(hours, tracking_output, label="Tracking")

ax1.set_xlabel("Time")
ax1.set_ylabel("Power (W)")
ax1.legend()

st.pyplot(fig1)

# ---------------------------
# 9. 그래프 2 (순 발전량)
# ---------------------------
net_tracking = np.array(tracking_output) - motor_energy_total

st.subheader("모터 소비 전력 고려 순 발전량")

fig2, ax2 = plt.subplots()

ax2.plot(hours, fixed_output, label="Fixed")
ax2.plot(hours, net_tracking, label="Tracking Net")

ax2.set_xlabel("Time")
ax2.set_ylabel("Power (W)")
ax2.legend()

st.pyplot(fig2)

# ---------------------------
# 10. 총 발전량 비교
# ---------------------------
total_fixed = np.sum(fixed_output)
total_tracking = np.sum(tracking_output)
net_total = total_tracking - motor_energy_total

st.subheader("총 발전량 비교")

col1, col2, col3 = st.columns(3)

col1.metric("고정형 총 발전량 (Wh)", f"{total_fixed:.1f}")
col2.metric("가변형 총 발전량 (Wh)", f"{total_tracking:.1f}")
col3.metric("순 발전량 (Wh)", f"{net_total:.1f}")

st.warning(f"모터 소비 전력: {motor_energy_total:.4f} Wh")

