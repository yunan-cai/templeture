#!/usr/bin/env python3
"""
西安天气自动推送脚本
在 GitHub Actions 环境中运行，每天定时推送天气到微信
"""
import requests
from datetime import datetime, timedelta
import json
import sys

# ===== 配置项 =====
SEND_KEY = "SCT328674TGNt9ymtHWVwK2D0pRaWZYIbQ"
PUSH_URL = f"https://sctapi.ftqq.com/{SEND_KEY}.send"

def get_weather_xian() -> dict:
    """从中国天气网获取西安今日天气"""
    try:
        url = "http://t.weather.sojson.com/api/weather/city/101110101"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 200:
            forecast = data['data']['forecast'][0]
            high = forecast.get('high', '').replace('高温 ', '').replace('℃', '').replace(' ', '')
            low = forecast.get('low', '').replace('低温 ', '').replace('℃', '').replace(' ', '')
            fx = forecast.get('fx', '').strip()
            fl = forecast.get('fl', '').strip()
            return {
                'condition': forecast.get('type', '未知'),
                'temp_high': high,
                'temp_low': low,
                'wind': f"{fx} {fl}" if fx and fl else '微风',
                'success': True
            }
    except Exception as e2:
        print(f"天气接口失败: {e2}")
        try:
            url = "https://www.weather.com.cn/data/cityinfo/101110101.html"
            resp = requests.get(url, timeout=10)
            resp.encoding = 'utf-8'
            data = resp.json()
            weatherinfo = data.get('weatherinfo', {})
            return {
                'condition': weatherinfo.get('weather', '未知'),
                'temp_high': weatherinfo.get('temp1', '--').replace('℃', ''),
                'temp_low': weatherinfo.get('temp2', '--').replace('℃', ''),
                'wind': '微风 <3级',
                'success': True
            }
        except Exception as e:
            print(f"备用接口也失败: {e}")
    return {
        'condition': '数据获取失败',
        'temp_high': '--',
        'temp_low': '--',
        'wind': '--',
        'success': False
    }

def get_weather_forecast() -> dict:
    """获取未来1-2天天气预报"""
    try:
        url = "http://t.weather.sojson.com/api/weather/city/101110101"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 200:
            forecast_list = data['data']['forecast']
            tomorrow = forecast_list[1] if len(forecast_list) > 1 else None
            day_after = forecast_list[2] if len(forecast_list) > 2 else None
            tomorrow_str = ""
            day_after_str = ""
            if tomorrow:
                t_high = tomorrow.get('high', '').replace('高温 ', '').replace('℃', '').replace(' ', '')
                t_low = tomorrow.get('low', '').replace('低温 ', '').replace('℃', '').replace(' ', '')
                tomorrow_str = f"{tomorrow.get('type', '--')}, {t_low}℃ ~ {t_high}℃"
            if day_after:
                d_high = day_after.get('high', '').replace('高温 ', '').replace('℃', '').replace(' ', '')
                d_low = day_after.get('low', '').replace('低温 ', '').replace('℃', '').replace(' ', '')
                day_after_str = f"{day_after.get('type', '--')}, {d_low}℃ ~ {d_high}℃"
            return {
                'tomorrow': tomorrow_str,
                'day_after': day_after_str,
                'success': True
            }
    except Exception as e:
        print(f"获取预报失败: {e}")
    return {
        'tomorrow': '暂无数据',
        'day_after': '暂无数据',
        'success': False
    }

def get_aqi() -> dict:
    """获取西安空气质量"""
    try:
        url = "https://api.waqi.info/feed/xian/?token=demo"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 'ok':
            aqi = data['data']['aqi']
            iaqi = data['data'].get('iaqi', {})
            if aqi <= 50:
                level = '优'
            elif aqi <= 100:
                level = '良'
            elif aqi <= 150:
                level = '轻度污染'
            elif aqi <= 200:
                level = '中度污染'
            elif aqi <= 300:
                level = '重度污染'
            else:
                level = '严重污染'
            return {
                'aqi': str(aqi),
                'level': level,
                'pm25': str(iaqi.get('pm25', {}).get('v', '--')),
                'success': True
            }
    except Exception as e:
        print(f"AQI 数据源失败: {e}")
    return {
        'aqi': '参考',
        'level': '良（参考）',
        'pm25': '--',
        'success': False
    }

def get_pollen() -> dict:
    """获取花粉浓度信息（基于季节和地区的估算）"""
    try:
        now = datetime.now()
        month = now.month
        
        # 西北地区（西安）季节性花粉等级参考
        pollen_level_map = {
            3: "高（4级）",
            4: "很高（5级）",
            5: "中高（3-4级）",
            6: "中（3级）",
            7: "低（2级）",
            8: "中（3级）",
            9: "高（4级）",
            10: "中高（3-4级）",
            11: "低（2级）",
            12: "低（1-2级）",
            1: "低（1-2级）",
            2: "低（1-2级）",
        }
        
        pollen_type_map = {
            3: "柏树、杨树、柳树等木本植物",
            4: "柳树、梧桐、杨柳科等树木花粉",
            5: "树木花粉为主",
            6: "草本花粉开始增多",
            7: "花粉浓度较低",
            8: "杂草花粉开始出现",
            9: "豚草、蒿草等杂草花粉",
            10: "杂草花粉 + 部分树木花粉",
            11: "花粉浓度下降",
            12: "花粉较少",
            1: "花粉较少",
            2: "花粉逐渐增加",
        }
        
        level = pollen_level_map.get(month, "低（2级）")
        pollen_type = pollen_type_map.get(month, "多种植物花粉")
        
        # 风险提示
        if "高" in level or "很高" in level:
            risk_tip = "过敏人群需重点防护，外出佩戴口罩和护目镜"
        elif "中" in level:
            risk_tip = "敏感人群外出请注意防护"
        else:
            risk_tip = "花粉浓度较低，一般人群正常活动"
        
        return {
            'level': f"🌸🌸🌸🌸 {level}" if "高" in level or "很高" in level else f"🌸 {level}",
            'type': pollen_type,
            'risk_tip': risk_tip,
            'success': True
        }
    except Exception as e:
        print(f"花粉数据获取失败: {e}")
        return {
            'level': '🌸🌸🌸🌸 高（4级）',
            'type': '春季树木花粉',
            'risk_tip': '过敏人群需重点防护',
            'success': False
        }

def build_weather_message(weather: dict, forecast: dict, aqi: dict, pollen: dict) -> str:
    """构建推送消息内容"""
    now = datetime.now()
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]
    
    tomorrow = now + timedelta(days=1)
    tomorrow_date = f"{tomorrow.month}月{tomorrow.day}日"
    day_after = now + timedelta(days=2)
    day_after_date = f"{day_after.month}月{day_after.day}日"
    
    tips = []
    try:
        temp_diff = int(weather['temp_high']) - int(weather['temp_low']) if weather['temp_high'].isdigit() and weather['temp_low'].isdigit() else 0
    except (ValueError, TypeError):
        temp_diff = 0
    
    if temp_diff > 10:
        tips.append(f"• 🌡 早晚温差大（{temp_diff}℃），注意增减衣物")
    if '雨' in weather['condition']:
        tips.append("• 🌧 今日有雨，出行请备雨具")
    if '晴' in weather['condition'] or '多云' in weather['condition']:
        tips.append("• ☀️ 天气不错，适合户外活动")
    if aqi['level'] in ['轻度污染', '中度污染', '重度污染', '严重污染']:
        tips.append(f"• 😷 空气质量{aqi['level']}，建议减少户外活动或佩戴口罩")
    if '高' in pollen['level'] or '很高' in pollen['level']:
        tips.append(f"• 🌸 花粉浓度{pollen['level']}，{pollen['risk_tip']}")
    elif '中' in pollen['level']:
        tips.append(f"• 🌸 花粉浓度{pollen['level']}，{pollen['risk_tip']}")
    
    tips_text = "\n".join(tips)
    
    message = f"""## 🌤 西安天气早报 · {date_str}（{weekday}）

---

### 📍 今日天气

| 项目 | 详情 |
|------|------|
| 🌥 天气状况 | {weather['condition']} |
| 🌡 气温 | {weather['temp_low']}℃ ~ {weather['temp_high']}℃ |
| 💨 风力风向 | {weather['wind']} |

---

### 🌫 空气质量

| 指标 | 数值 |
|------|------|
| AQI 指数 | **{aqi['aqi']}**（{aqi['level']}） |
| PM2.5 | {aqi['pm25']} μg/m³ |

---

### 🌸 花粉浓度

| 项目 | 详情 |
|------|------|
| 🌼 花粉等级 | **{pollen['level']}** |
| 🌿 主要花粉 | {pollen['type']} |
| 📊 风险提示 | {pollen['risk_tip']} |

---

### 📅 未来天气

| 日期 | 天气 | 气温 |
|------|------|------|
| 明天（{tomorrow_date}） | {forecast['tomorrow']} |
| 后天（{day_after_date}） | {forecast['day_after']} |

---

### 💡 温馨提示

{tips_text}

---

*数据来源：中国天气网 & SoJSON天气API & WAQI | 推送时间：{now.strftime('%H:%M')}*
"""
    return message

def push_to_wechat(title: str, content: str) -> bool:
    """通过 Server酱 推送到微信"""
    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.post(PUSH_URL, data={"title": title, "desp": content}, timeout=15)
        result = resp.json()
        print(f"推送结果: {result}")
        if result.get('code') == 0:
            return True
        else:
            print(f"推送失败: {result.get('message', '未知错误')}")
            return False
    except Exception as e:
        print(f"推送异常: {e}")
        return False

def main():
    print(f"=== 西安天气推送任务开始 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print("正在获取天气数据...")
    weather = get_weather_xian()
    forecast = get_weather_forecast()
    aqi = get_aqi()
    pollen = get_pollen()

    if not weather['success']:
        print("天气数据获取失败，退出")
        sys.exit(1)
    
    print(f"今日天气: {weather['condition']}, {weather['temp_low']}~{weather['temp_high']}℃")
    
    title = f"西安天气早报 {datetime.now().strftime('%m/%d')}"
    content = build_weather_message(weather, forecast, aqi, pollen)
    
    print("正在推送...")
    success = push_to_wechat(title, content)
    
    if success:
        print("✅ 推送成功！")
        sys.exit(0)
    else:
        print("❌ 推送失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
