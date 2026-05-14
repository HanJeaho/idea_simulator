import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# =========================================================
# 0. 기본 설정
# =========================================================
st.set_page_config(
    page_title="AI 기반 가변형 태양광 도로 울타리 시뮬레이터",
    layout="wide"
)

st.title("🌞 AI 기반 가변형 태양광 도로 울타리 시뮬레이터")
st.caption("10분 단위 시뮬레이션: 고정형 · 연속 추적형 · 간헐 추적형 비교")

# =========================================================
# 1. 사이드바 입력
# =========================================================
st.sidebar.header("입력 설정")

fixed_panel_angle = st.sidebar.slider("고정형 패널 각도 (°)", 0, 90, 30, 1)
selected_time = st.sidebar.slider("현재 시간 (시)", 0, 23, 12, 1)
latitude = st.sidebar.slider("위도 (°)", 0, 60, 37, 1)

month_days = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
month_labels = {i: f"{i}월" for i in range(1, 13)}

month = st.sidebar.selectbox(
    "월", list(month_days.keys()),
    format_func=lambda x: month_labels[x], index=5
)
day_of_month = st.sidebar.slider(
    "일", 1, month_days[month], min(21, month_days[month]), 1
)
day = sum(month_days[m] for m in range(1, month)) + day_of_month
st.sidebar.caption(f"선택 날짜: {month}월 {day_of_month}일 / 1년 중 {day}번째 날")

weather = st.sidebar.selectbox("날씨", ["맑음", "흐림", "비"])
st.sidebar.divider()

# 패널 조건
st.sidebar.header("패널 조건")
panel_area = st.sidebar.number_input("패널 면적 (m²)", 0.1, 5.0, 1.6, 0.1)
panel_efficiency = st.sidebar.slider("패널 효율 (%)", 5, 30, 20, 1) / 100
solar_irradiance = st.sidebar.slider("기준 일사량 (W/m²)", 200, 1200, 1000, 50)
num_panels = int(st.sidebar.number_input(
    "설치 패널 수 (장)", min_value=1, max_value=1000, value=10, step=1
))
st.sidebar.divider()

# [개선 1] 울타리 방향 설정
st.sidebar.header("울타리 방향 설정")
panel_face_az = st.sidebar.slider(
    "패널 전면 방향 (°, 북=0°, 동=90°, 남=180°, 서=270°)",
    min_value=0, max_value=359, value=180, step=1
)
_dir_map = {0:"북",45:"북동",90:"동",135:"남동",180:"남",225:"남서",270:"서",315:"북서"}
_nearest = min(_dir_map.keys(), key=lambda k: abs(k - panel_face_az))
st.sidebar.caption(
    f"패널 전면 방향 ≈ {_dir_map[_nearest]} ({panel_face_az}°)  \n"
    "남향(180°)이 한국 기준 가장 효율적입니다."
)
st.sidebar.divider()

# 모터 조건
st.sidebar.header("모터 조건")
panel_mass = st.sidebar.number_input("패널 질량 (kg)", 1.0, 50.0, 20.0, 1.0)
rotation_radius = st.sidebar.number_input("회전 중심 거리 (m)", 0.1, 2.0, 0.8, 0.1)
motor_efficiency = st.sidebar.slider("모터 효율 (%)", 10, 100, 70, 5) / 100

# [개선 5] 간헐 추적 간격 일반화
tracking_interval_min = st.sidebar.slider("간헐 추적 간격 (분)", 10, 120, 60, 10)
st.sidebar.divider()

# [개선 2] 전력망 손실 설정
st.sidebar.header("전력망 손실 설정")
transmission_loss_pct = st.sidebar.slider(
    "장거리 송전 손실률 (%)", 0.0, 10.0, 3.5, 0.1
)
transmission_loss_rate = transmission_loss_pct / 100
local_wire_loss_pct = st.sidebar.slider(
    "분산형 배선 손실률 (%)", 0.0, 5.0, 0.5, 0.1
)
local_wire_loss_rate = local_wire_loss_pct / 100
st.sidebar.divider()

# [개선 3] 경제성 분석 설정
st.sidebar.header("경제성 분석")
electricity_price = st.sidebar.number_input(
    "전력 단가 (원/kWh)", min_value=50, max_value=500, value=130, step=10
)
carbon_factor = st.sidebar.number_input(
    "탄소 배출 계수 (kg CO₂/kWh)", min_value=0.1, max_value=1.0,
    value=0.4594, step=0.001, format="%.4f"
)

# =========================================================
# 2. 태양 위치 계산 함수
# =========================================================
def solar_declination(day_of_year):
    return 23.45 * np.sin(np.radians(360 * (284 + day_of_year) / 365))


def solar_altitude(latitude_deg, declination_deg, hour):
    hour_angle = (hour - 12) * 15
    sin_alt = np.clip(
        np.sin(np.radians(latitude_deg)) * np.sin(np.radians(declination_deg)) +
        np.cos(np.radians(latitude_deg)) * np.cos(np.radians(declination_deg)) *
        np.cos(np.radians(hour_angle)),
        -1, 1
    )
    return max(0.0, np.degrees(np.arcsin(sin_alt)))


# [개선 1] 태양 방위각 계산 추가 (북=0°, 동=90°, 남=180°, 서=270°)
def solar_azimuth(latitude_deg, declination_deg, hour):
    lat = np.radians(latitude_deg)
    decl_r = np.radians(declination_deg)
    H = np.radians((hour - 12) * 15)

    sin_alt = np.clip(
        np.sin(lat) * np.sin(decl_r) + np.cos(lat) * np.cos(decl_r) * np.cos(H),
        -1, 1
    )
    alt = np.arcsin(sin_alt)

    if alt <= 0 or np.cos(alt) < 1e-9:
        return 180.0  # 일몰/일출 경계: 남쪽 기본값

    sin_az = -np.cos(decl_r) * np.sin(H) / np.cos(alt)
    cos_az = (np.sin(decl_r) - np.sin(alt) * np.sin(lat)) / (np.cos(alt) * np.cos(lat))
    az = np.degrees(np.arctan2(sin_az, cos_az))
    return az % 360


# =========================================================
# 3. 날씨 보정
# =========================================================
def weather_factor(weather_condition):
    return {"맑음": 1.0, "흐림": 0.6, "비": 0.3}.get(weather_condition, 1.0)


# =========================================================
# 4. 발전량 계산 함수 (방위각 반영)
# =========================================================
# [개선 1] 3D 벡터 내적으로 실제 입사각 계산
def incidence_angle_factor(panel_angle_deg, solar_alt_deg, solar_az_deg, face_az_deg):
    """
    panel_angle_deg : 패널 기울기 (0°=수평, 90°=수직)
    face_az_deg     : 패널 전면 방향 방위각 (북=0°, 남=180°)
    반환값          : 입사각 코사인 (0~1)
    """
    if solar_alt_deg <= 0:
        return 0.0

    alt = np.radians(solar_alt_deg)
    saz = np.radians(solar_az_deg)
    pan = np.radians(panel_angle_deg)
    faz = np.radians(face_az_deg)

    # 태양 단위벡터 (동=x, 북=y, 상=z)
    sx = np.sin(saz) * np.cos(alt)
    sy = np.cos(saz) * np.cos(alt)
    sz = np.sin(alt)

    # 패널 법선벡터
    nx = np.sin(pan) * np.sin(faz)
    ny = np.sin(pan) * np.cos(faz)
    nz = np.cos(pan)

    return max(0.0, sx * nx + sy * ny + sz * nz)


def calculate_power(panel_angle_deg, solar_alt_deg, solar_az_deg, weather_condition):
    factor = incidence_angle_factor(
        panel_angle_deg, solar_alt_deg, solar_az_deg, panel_face_az
    )
    return (
        solar_irradiance * panel_area * panel_efficiency
        * factor * weather_factor(weather_condition)
    )


# [개선 1] 울타리 방향을 반영한 AI 최적 각도 계산
def ai_optimal_angle(solar_alt_deg, solar_az_deg):
    """
    입사각 인수 = C·sin(θ) + B·cos(θ)  (θ = 패널 각도)
    C = cos(alt)·cos(solar_az - face_az),  B = sin(alt)
    최대화: θ* = arctan(C/B)
    """
    if solar_alt_deg <= 0:
        return 0.0

    alt = np.radians(solar_alt_deg)
    az_diff = np.radians(solar_az_deg - panel_face_az)
    C = np.cos(alt) * np.cos(az_diff)
    B = np.sin(alt)

    if B < 1e-9 and C <= 0:
        return 0.0

    angle = np.degrees(np.arctan2(C, B))
    return float(np.clip(angle, 0, 90))


# =========================================================
# 5. 모터 소비 에너지
# =========================================================
def calculate_motor_energy(angle_change_deg):
    if abs(angle_change_deg) < 1e-9:
        return 0.0
    torque = panel_mass * 9.81 * rotation_radius
    energy_j = torque * np.radians(abs(angle_change_deg)) / motor_efficiency
    return energy_j / 3600  # → Wh


# =========================================================
# 6. 현재 시간 기준 계산
# =========================================================
decl = solar_declination(day)

current_alt = solar_altitude(latitude, decl, selected_time)
current_az  = solar_azimuth(latitude, decl, selected_time)
current_ai_angle = ai_optimal_angle(current_alt, current_az)

current_fixed_power    = calculate_power(fixed_panel_angle, current_alt, current_az, weather)
current_tracking_power = calculate_power(current_ai_angle,  current_alt, current_az, weather)
current_gain           = current_tracking_power - current_fixed_power

st.subheader("현재 시간 기준 결과")
c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("태양 고도각",     f"{current_alt:.2f}°")
with c2: st.metric("태양 방위각",     f"{current_az:.1f}°")
with c3: st.metric("AI 최적 패널 각도", f"{current_ai_angle:.2f}°")
with c4: st.metric("고정형 발전량",   f"{current_fixed_power:.2f} W")
with c5: st.metric("AI 최적각 발전량", f"{current_tracking_power:.2f} W", f"{current_gain:.2f} W")

# =========================================================
# 7. 10분 단위 시뮬레이션
# =========================================================
time_step_hour       = 1 / 6
times                = np.arange(6, 18 + time_step_hour, time_step_hour)
tracking_interval_hr = tracking_interval_min / 60

solar_altitudes, solar_azimuths_list, optimal_angles = [], [], []
fixed_powers, fixed_energies = [], []
cont_angles, cont_gross_powers, cont_motor_energies = [], [], []
cont_net_powers, cont_net_energies, cont_gains = [], [], []
step_angles, step_gross_powers, step_motor_energies = [], [], []
step_net_powers, step_net_energies, step_gains = [], [], []

prev_cont_angle  = fixed_panel_angle
prev_step_angle  = fixed_panel_angle
curr_step_angle  = fixed_panel_angle
# 첫 타임스텝(t=6)에서 즉시 최적화 시작
last_step_time   = 6.0 - tracking_interval_hr

for t in times:
    alt = solar_altitude(latitude, decl, t)
    az  = solar_azimuth(latitude, decl, t)
    opt = ai_optimal_angle(alt, az)

    # 고정형
    fp = calculate_power(fixed_panel_angle, alt, az, weather)
    fe = fp * time_step_hour

    # 연속 추적형 (10분마다 최적 각도)
    ca  = opt
    cgp = calculate_power(ca, alt, az, weather)
    cme = calculate_motor_energy(ca - prev_cont_angle)
    cge = cgp * time_step_hour
    cne = cge - cme
    cnp = cne / time_step_hour

    # [개선 5] 간헐 추적형 (사용자 지정 간격)
    if (t - last_step_time) >= tracking_interval_hr - 1e-9:
        curr_step_angle = opt
        sme = calculate_motor_energy(curr_step_angle - prev_step_angle)
        prev_step_angle = curr_step_angle
        last_step_time  = t
    else:
        sme = 0.0

    sgp = calculate_power(curr_step_angle, alt, az, weather)
    sge = sgp * time_step_hour
    sne = sge - sme
    snp = sne / time_step_hour

    solar_altitudes.append(alt)
    solar_azimuths_list.append(az)
    optimal_angles.append(opt)
    fixed_powers.append(fp);       fixed_energies.append(fe)
    cont_angles.append(ca);        cont_gross_powers.append(cgp)
    cont_motor_energies.append(cme); cont_net_powers.append(cnp)
    cont_net_energies.append(cne); cont_gains.append(cnp - fp)
    step_angles.append(curr_step_angle); step_gross_powers.append(sgp)
    step_motor_energies.append(sme); step_net_powers.append(snp)
    step_net_energies.append(sne); step_gains.append(snp - fp)

    prev_cont_angle = ca


def format_time(h):
    hr = int(h); mn = int(round((h - hr) * 60))
    if mn == 60: hr += 1; mn = 0
    return f"{hr:02d}:{mn:02d}"


df = pd.DataFrame({
    "Time": times,
    "Solar Altitude": solar_altitudes,
    "Solar Azimuth":  solar_azimuths_list,
    "AI Optimal Angle": optimal_angles,
    "Fixed Power": fixed_powers,
    "Fixed Energy": fixed_energies,
    "Continuous Angle": cont_angles,
    "Continuous Gross Power": cont_gross_powers,
    "Continuous Motor Energy": cont_motor_energies,
    "Continuous Net Power": cont_net_powers,
    "Continuous Net Energy": cont_net_energies,
    "Continuous Gain": cont_gains,
    "Step Angle": step_angles,
    "Step Gross Power": step_gross_powers,
    "Step Motor Energy": step_motor_energies,
    "Step Net Power": step_net_powers,
    "Step Net Energy": step_net_energies,
    "Step Gain": step_gains,
})
df["Time Label"] = df["Time"].apply(format_time)

# =========================================================
# 8. 그래프 1: 발전량 비교
# =========================================================
st.subheader("10분 단위 발전량 비교")
fig_power = go.Figure()
fig_power.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Fixed Power"], mode="lines", name="고정형",
    customdata=np.stack([df["Solar Altitude"], df["Solar Azimuth"],
                         df["AI Optimal Angle"], df["Fixed Power"]], axis=-1),
    hovertemplate=(
        "시간: %{x}<br>태양 고도: %{customdata[0]:.2f}°<br>"
        "태양 방위: %{customdata[1]:.1f}°<br>AI 최적각: %{customdata[2]:.2f}°<br>"
        "발전량: %{customdata[3]:.2f} W<extra></extra>"
    )
))
fig_power.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Continuous Net Power"], mode="lines", name="연속 추적형 (순)",
    customdata=np.stack([df["Solar Altitude"], df["Solar Azimuth"], df["Continuous Angle"],
                         df["Continuous Motor Energy"], df["Continuous Net Power"],
                         df["Continuous Gain"]], axis=-1),
    hovertemplate=(
        "시간: %{x}<br>태양 고도: %{customdata[0]:.2f}°<br>"
        "태양 방위: %{customdata[1]:.1f}°<br>패널 각도: %{customdata[2]:.2f}°<br>"
        "모터 소비: %{customdata[3]:.4f} Wh<br>순발전량: %{customdata[4]:.2f} W<br>"
        "고정형 대비: %{customdata[5]:.2f} W<extra></extra>"
    )
))
fig_power.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Step Net Power"], mode="lines",
    name=f"간헐 추적형 {tracking_interval_min}분 (순)",
    customdata=np.stack([df["Solar Altitude"], df["Solar Azimuth"], df["Step Angle"],
                         df["Step Motor Energy"], df["Step Net Power"],
                         df["Step Gain"]], axis=-1),
    hovertemplate=(
        "시간: %{x}<br>태양 고도: %{customdata[0]:.2f}°<br>"
        "태양 방위: %{customdata[1]:.1f}°<br>패널 각도: %{customdata[2]:.2f}°<br>"
        "모터 소비: %{customdata[3]:.4f} Wh<br>순발전량: %{customdata[4]:.2f} W<br>"
        "고정형 대비: %{customdata[5]:.2f} W<extra></extra>"
    )
))
fig_power.update_layout(
    xaxis_title="시간", yaxis_title="발전량 (W)",
    hovermode="x unified", legend_title="방식", height=560
)
st.plotly_chart(fig_power, use_container_width=True)

# =========================================================
# 9. 그래프 2: 태양 방위각 + 패널 각도 비교 (개선 1)
# =========================================================
st.subheader("태양 방위각 및 패널 각도 변화")
fig_angle = go.Figure()
fig_angle.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Solar Azimuth"],
    mode="lines", name="태양 방위각", line=dict(dash="dot", color="orange"),
    hovertemplate="시간: %{x}<br>태양 방위각: %{y:.1f}°<extra></extra>"
))
fig_angle.add_hline(
    y=panel_face_az, line_dash="dash", line_color="gray",
    annotation_text=f"패널 전면 방향 {panel_face_az}°"
)
fig_angle.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Continuous Angle"],
    mode="lines", name="연속 추적형 패널 각도",
    hovertemplate="시간: %{x}<br>연속 추적 각도: %{y:.2f}°<extra></extra>"
))
fig_angle.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Step Angle"],
    mode="lines", name=f"간헐 추적형 패널 각도 ({tracking_interval_min}분)",
    hovertemplate="시간: %{x}<br>간헐 추적 각도: %{y:.2f}°<extra></extra>"
))
fig_angle.update_layout(
    xaxis_title="시간", yaxis_title="각도 (°)",
    hovermode="x unified", legend_title="항목", height=440
)
st.plotly_chart(fig_angle, use_container_width=True)

# =========================================================
# 10. 그래프 3: 모터 소비 에너지
# =========================================================
st.subheader("10분 단위 모터 소비 에너지 비교")
fig_motor = go.Figure()
fig_motor.add_trace(go.Bar(
    x=df["Time Label"], y=df["Continuous Motor Energy"], name="연속 추적형",
    hovertemplate="시간: %{x}<br>모터 소비: %{y:.4f} Wh<extra></extra>"
))
fig_motor.add_trace(go.Bar(
    x=df["Time Label"], y=df["Step Motor Energy"],
    name=f"간헐 추적형 ({tracking_interval_min}분)",
    hovertemplate="시간: %{x}<br>모터 소비: %{y:.4f} Wh<extra></extra>"
))
fig_motor.update_layout(
    xaxis_title="시간", yaxis_title="모터 에너지 (Wh)",
    barmode="group", hovermode="x unified", height=400
)
st.plotly_chart(fig_motor, use_container_width=True)

# =========================================================
# 11. 그래프 4: 고정형 대비 순 증가량
# =========================================================
st.subheader("고정형 대비 순 발전 증가량")
fig_gain = go.Figure()
fig_gain.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Continuous Gain"], mode="lines", name="연속 추적형",
    hovertemplate="시간: %{x}<br>증가량: %{y:.2f} W<extra></extra>"
))
fig_gain.add_trace(go.Scatter(
    x=df["Time Label"], y=df["Step Gain"], mode="lines",
    name=f"간헐 추적형 ({tracking_interval_min}분)",
    hovertemplate="시간: %{x}<br>증가량: %{y:.2f} W<extra></extra>"
))
fig_gain.add_hline(y=0, line_dash="dash", line_color="gray")
fig_gain.update_layout(
    xaxis_title="시간", yaxis_title="순 발전 증가량 (W)",
    hovermode="x unified", legend_title="방식", height=400
)
st.plotly_chart(fig_gain, use_container_width=True)

# =========================================================
# 12. 총 발전량 — 단일 패널 기준
# =========================================================
total_fixed_energy = df["Fixed Energy"].sum()
total_cont_motor   = df["Continuous Motor Energy"].sum()
total_cont_net     = df["Continuous Net Energy"].sum()
total_step_motor   = df["Step Motor Energy"].sum()
total_step_net     = df["Step Net Energy"].sum()

cont_improve = ((total_cont_net / total_fixed_energy - 1) * 100) if total_fixed_energy > 0 else 0
step_improve = ((total_step_net / total_fixed_energy - 1) * 100) if total_fixed_energy > 0 else 0

st.subheader("총 발전량 비교 (단일 패널 기준)")
r1c1, r1c2, r1c3 = st.columns(3)
with r1c1: st.metric("고정형 총 발전량",    f"{total_fixed_energy:.2f} Wh")
with r1c2: st.metric("연속 추적형 순 발전량", f"{total_cont_net:.2f} Wh", f"{cont_improve:.2f}%")
with r1c3: st.metric(f"간헐 추적형 ({tracking_interval_min}분) 순 발전량",
                     f"{total_step_net:.2f} Wh", f"{step_improve:.2f}%")

r2c1, r2c2, r2c3 = st.columns(3)
with r2c1: st.metric("연속 추적형 모터 소비",   f"{total_cont_motor:.4f} Wh")
with r2c2: st.metric("간헐 추적형 모터 소비",   f"{total_step_motor:.4f} Wh")
with r2c3: st.metric("연속형 - 간헐형 차이",    f"{total_cont_net - total_step_net:.2f} Wh")

# =========================================================
# 13. [개선 4] 설치 규모 적용 발전량 (N장 기준)
# =========================================================
# 패널 간 상호 음영에 의한 간략 손실 보정
SHADING_FACTOR = 0.95

fixed_scaled = total_fixed_energy * num_panels * SHADING_FACTOR
cont_scaled  = total_cont_net    * num_panels * SHADING_FACTOR
step_scaled  = total_step_net    * num_panels * SHADING_FACTOR

st.subheader(f"설치 규모 적용 발전량 ({num_panels}장, 음영 보정 {SHADING_FACTOR*100:.0f}%)")
sc1, sc2, sc3 = st.columns(3)
with sc1:
    st.metric("고정형",
              f"{fixed_scaled:.1f} Wh",
              f"{fixed_scaled/1000:.3f} kWh")
with sc2:
    st.metric("연속 추적형",
              f"{cont_scaled:.1f} Wh",
              f"{cont_scaled/1000:.3f} kWh")
with sc3:
    st.metric(f"간헐 추적형 ({tracking_interval_min}분)",
              f"{step_scaled:.1f} Wh",
              f"{step_scaled/1000:.3f} kWh")

# =========================================================
# 14. [개선 2] 전력망 손실 비교 분석
# =========================================================
st.subheader("전력망 손실 비교 분석")
st.caption(
    f"장거리 송전 손실률: **{transmission_loss_pct:.1f}%** | "
    f"분산형 배선 손실률: **{local_wire_loss_pct:.1f}%**"
)
st.markdown(
    """
    > **계산 기준**
    > - 분산형 실효 공급량 = 발전량 × (1 - 배선 손실률)
    > - 동량 송전 시 필요 발전량 = 실효 공급량 ÷ (1 - 송전 손실률)
    > - 절감된 추가 발전 필요량 = 필요 발전량 - 발전량
    """
)

def grid_metrics(generated_wh):
    eff_supply    = generated_wh * (1 - local_wire_loss_rate)
    grid_needed   = eff_supply   / (1 - transmission_loss_rate) if transmission_loss_rate < 1 else 0
    loss_saved    = grid_needed  - generated_wh
    return eff_supply, grid_needed, loss_saved

fix_eff, fix_grid, fix_loss_saved   = grid_metrics(fixed_scaled)
cont_eff, cont_grid, cont_loss_saved = grid_metrics(cont_scaled)
step_eff, step_grid, step_loss_saved = grid_metrics(step_scaled)

tl1, tl2, tl3 = st.columns(3)
for col, label, eff, grid, ls in [
    (tl1, "고정형",                fix_eff,  fix_grid,  fix_loss_saved),
    (tl2, "연속 추적형",            cont_eff, cont_grid, cont_loss_saved),
    (tl3, f"간헐 추적형 ({tracking_interval_min}분)", step_eff, step_grid, step_loss_saved),
]:
    with col:
        st.markdown(f"**{label}**")
        st.metric("분산형 실효 공급량",         f"{eff:.1f} Wh")
        st.metric("동량 송전 시 필요 발전량",    f"{grid:.1f} Wh")
        st.metric("절감된 추가 발전 필요량",     f"{ls:.1f} Wh")

st.markdown("---")
st.markdown("**추적형 도입 시 추가 절감 효과 (고정형 대비)**")
ea1, ea2 = st.columns(2)
with ea1:
    extra_cont = cont_loss_saved - fix_loss_saved
    st.metric("연속 추적형 — 추가 송전 손실 절감",
              f"{extra_cont:.1f} Wh  ({extra_cont/1000:.4f} kWh)")
with ea2:
    extra_step = step_loss_saved - fix_loss_saved
    st.metric(f"간헐 추적형 — 추가 송전 손실 절감",
              f"{extra_step:.1f} Wh  ({extra_step/1000:.4f} kWh)")

# =========================================================
# 15. [개선 3] 경제성 및 탄소 절감 분석
# =========================================================
st.subheader("경제성 및 탄소 절감 분석")
st.caption(
    f"전력 단가: {electricity_price}원/kWh | "
    f"탄소 배출 계수: {carbon_factor:.4f} kg CO₂/kWh | "
    f"연간 환산: 하루 결과 × 365일 (계절 보정 미적용)"
)

cont_gain_kwh = (cont_scaled - fixed_scaled) / 1000
step_gain_kwh = (step_scaled - fixed_scaled) / 1000
cont_gain_annual = cont_gain_kwh * 365
step_gain_annual = step_gain_kwh * 365

ec1, ec2 = st.columns(2)
with ec1:
    st.markdown("**연속 추적형 (고정형 대비)**")
    st.metric("하루 추가 발전량",       f"{cont_gain_kwh*1000:.2f} Wh  ({cont_gain_kwh:.4f} kWh)")
    st.metric("연간 추가 발전량",       f"{cont_gain_annual:.2f} kWh")
    st.metric("연간 전기요금 절감",     f"{cont_gain_annual * electricity_price:,.0f} 원")
    st.metric("연간 CO₂ 절감량",       f"{cont_gain_annual * carbon_factor:.2f} kg CO₂")

with ec2:
    st.markdown(f"**간헐 추적형 {tracking_interval_min}분 (고정형 대비)**")
    st.metric("하루 추가 발전량",       f"{step_gain_kwh*1000:.2f} Wh  ({step_gain_kwh:.4f} kWh)")
    st.metric("연간 추가 발전량",       f"{step_gain_annual:.2f} kWh")
    st.metric("연간 전기요금 절감",     f"{step_gain_annual * electricity_price:,.0f} 원")
    st.metric("연간 CO₂ 절감량",       f"{step_gain_annual * carbon_factor:.2f} kg CO₂")

# =========================================================
# 16. [개선 5] 최적 간헐 추적 간격 탐색
# =========================================================
st.subheader("간헐 추적 간격별 순 발전량 비교")
st.caption("10분~120분 전수 계산으로 현재 조건의 최적 간격을 자동 탐색합니다.")

interval_results = {}
for iv_min in range(10, 130, 10):
    iv_hr   = iv_min / 60
    lst     = 6.0 - iv_hr
    psa     = fixed_panel_angle
    csa     = fixed_panel_angle
    total   = 0.0
    for t in times:
        alt = solar_altitude(latitude, decl, t)
        az  = solar_azimuth(latitude, decl, t)
        opt = ai_optimal_angle(alt, az)
        if (t - lst) >= iv_hr - 1e-9:
            m_e  = calculate_motor_energy(opt - psa)
            psa  = opt
            csa  = opt
            lst  = t
        else:
            m_e = 0.0
        gp     = calculate_power(csa, alt, az, weather)
        total += gp * time_step_hour - m_e
    interval_results[iv_min] = total * num_panels * SHADING_FACTOR

best_iv = max(interval_results, key=interval_results.get)
iv_df = pd.DataFrame({
    "간격 (분)":     list(interval_results.keys()),
    "순 발전량 (Wh)": list(interval_results.values())
})

fig_iv = go.Figure()
fig_iv.add_trace(go.Bar(
    x=[f"{x}분" for x in iv_df["간격 (분)"]],
    y=iv_df["순 발전량 (Wh)"],
    marker_color=[
        "crimson" if x == best_iv else
        ("steelblue" if x == tracking_interval_min else "lightsteelblue")
        for x in iv_df["간격 (분)"]
    ],
    hovertemplate="간격: %{x}<br>순 발전량: %{y:.2f} Wh<extra></extra>"
))
fig_iv.update_layout(
    xaxis_title="추적 간격", yaxis_title="순 발전량 (Wh)",
    height=380,
    annotations=[dict(
        text=f"최적: {best_iv}분 ({interval_results[best_iv]:.1f} Wh)  |  현재 설정: {tracking_interval_min}분",
        xref="paper", yref="paper", x=0.5, y=1.08,
        showarrow=False, font=dict(size=13)
    )]
)
st.plotly_chart(fig_iv, use_container_width=True)
st.info(
    f"현재 조건에서 최적 추적 간격: **{best_iv}분** "
    f"(순 발전량 {interval_results[best_iv]:.2f} Wh)  \n"
    f"현재 설정값 {tracking_interval_min}분: {interval_results[tracking_interval_min]:.2f} Wh"
)

# =========================================================
# 17. 데이터 테이블
# =========================================================
with st.expander("10분 단위 계산 데이터 보기"):
    st.dataframe(
        df.round({
            "Solar Altitude": 2, "Solar Azimuth": 1, "AI Optimal Angle": 2,
            "Fixed Power": 2, "Fixed Energy": 2,
            "Continuous Angle": 2, "Continuous Gross Power": 2,
            "Continuous Motor Energy": 4, "Continuous Net Power": 2,
            "Continuous Net Energy": 2, "Continuous Gain": 2,
            "Step Angle": 2, "Step Gross Power": 2,
            "Step Motor Energy": 4, "Step Net Power": 2,
            "Step Net Energy": 2, "Step Gain": 2,
        }),
        use_container_width=True
    )

# =========================================================
# 18. 종합 해석
# =========================================================
st.subheader("종합 해석")
st.write(f"""
현재 조건 (위도 {latitude}°, {month}월 {day_of_month}일, 패널 전면 방향 {panel_face_az}°,
날씨: {weather}, 설치 {num_panels}장)에서 시뮬레이션한 결과입니다.

**발전량 비교**
- 고정형 총 발전량: **{fixed_scaled:.1f} Wh**
- 연속 추적형 순 발전량: **{cont_scaled:.1f} Wh** (고정형 대비 **{cont_improve:.2f}%** 향상)
- 간헐 추적형 ({tracking_interval_min}분) 순 발전량: **{step_scaled:.1f} Wh** (고정형 대비 **{step_improve:.2f}%** 향상)
- 최적 간헐 추적 간격: **{best_iv}분**

**분산형 발전의 추가 효과 (장거리 송전 {transmission_loss_pct:.1f}% 손실 절감)**
- 연속 추적형 기준 추가 절감: **{cont_loss_saved - fix_loss_saved:.1f} Wh/일**

**연간 경제성 (연속 추적형, 고정형 대비)**
- 추가 발전량: **{cont_gain_annual:.2f} kWh/년**
- 전기요금 절감: **{cont_gain_annual * electricity_price:,.0f}원/년**
- CO₂ 절감: **{cont_gain_annual * carbon_factor:.2f} kg CO₂/년**
""")

st.info("""
**울타리 방향 설정 안내**
패널 전면 방향이 태양이 주로 위치하는 방향(한국 기준 남쪽 180°)에 가까울수록 발전량이 높습니다.
도로가 동-서 방향으로 놓인 경우 남향(180°), 남-북 방향인 경우 동향(90°) 또는 서향(270°)을 선택하세요.

**간헐 추적형 안내**
추적 간격이 짧을수록 발전량은 증가하지만 모터 소비도 증가합니다.
최적 간격 차트에서 붉은 막대(최적값)와 현재 설정(파란색)을 비교하세요.
""")
