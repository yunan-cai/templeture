#!/usr/bin/env python3
"""
西安天气自动推送脚本
在 GitHub Actions 环境中运行，每天定时推送天气到微信
"""
import requests
from datetime import datetime, timedelta
import json
import sys
import base64
import os
import tempfile

# ===== 配置项 =====
SEND_KEY = "SCT328674TGNt9ymtHWVwK2D0pRaWZYIbQ"
PUSH_URL = f"https://sctapi.ftqq.com/{SEND_KEY}.send"

# 图片生成开关
GENERATE_IMAGE = False  # 设为 False 则只发文字（先测试基础功能）

# 天气数据源（和风天气API，无需 key）
WEATHER_API_URL = "https://api.qweather.com/v7/weather/now"

# 或者使用中国天气网的免费接口（更稳定）
def get_weather_xian() -> dict:
    """从中国天气网获取西安今日天气"""
    try:
        # 备用：使用天气后报的实时接口（更稳定）
        url = "http://t.weather.sojson.com/api/weather/city/101110101"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('status') == 200:
            forecast = data['data']['forecast'][0]
            # API返回格式: {"high": "高温 24℃", "low": "低温 11℃", "fx": "东风", "fl": "<3级", "type": "阴"}
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
        # 尝试另一个数据源
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
    """获取西安空气质量（尽力而为，多个数据源）"""
    # 尝试多个数据源
    sources = [
        "https://api.waqi.info/feed/xian/?token=demo",  # WAQI demo token，可能有限制
    ]

    for url in sources:
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get('status') == 'ok':
                aqi = data['data']['aqi']
                iaqi = data['data'].get('iaqi', {})

                # 简单的 AQI 等级判断
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
            continue

    # 如果都失败，返回一个"参考值"
    return {
        'aqi': '参考',
        'level': '良（参考）',
        'pm25': '--',
        'success': False
    }


def get_pollen() -> dict:
    """
    获取西安花粉浓度信息
    数据来源优先级：
    1. 中国天气网官方花粉指数页面（国家卫生健康委 & 中国气象局联合发布，最权威）
    2. 和风天气过敏指数 API（需要 key，作为备用）
    3. 本地季节估算（兜底）
    """

    # ── 方法1：从中国天气网官方花粉指数页面抓取 ──────────────────────────────
    try:
        # 西安城市 ID: 101110101
        url = "https://www.weather.com.cn/forecast/hf_index.shtml?id=101110101"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.weather.com.cn/",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        html = resp.text

        # 解析页面中的花粉等级信息（中国天气网花粉页面结构）
        import re

        # 匹配等级数字（1~5）和等级文字，如：<p class="flevel">4</p><p>较高</p>
        level_match = re.search(
            r'class="[^"]*flevel[^"]*"[^>]*>\s*(\d)\s*</[^>]+>.*?<p[^>]*>\s*([^<]{1,8})\s*</p>',
            html, re.DOTALL
        )
        # 备用：搜索"很高""较高""偏高""较低""很低""未检测"等关键词附近的数字
        category_match = re.search(
            r'(\d)\s*级.*?(很高|较高|偏高|中|较低|很低|极低|未检测)',
            html
        )
        # 再备用：直接搜索花粉等级文字
        text_match = re.search(
            r'花粉[浓度指数]*[\s：:]*.*?(\d)\s*[级]?\s*(很高|较高|偏高|中|中等|较低|很低|未检测)',
            html
        )

        level_num = None
        level_text = None

        if level_match:
            level_num = int(level_match.group(1))
            level_text = level_match.group(2).strip()
        elif category_match:
            level_num = int(category_match.group(1))
            level_text = category_match.group(2).strip()
        elif text_match:
            level_num = int(text_match.group(1))
            level_text = text_match.group(2).strip()

        # 尝试解析主要花粉种类
        pollen_type_match = re.search(
            r'(柏[树木科]*|杨树|柳树|桦树|蒿草|豚草|梧桐|禾本|草本|木本)[^，。\n]{0,30}[花粉]*',
            html
        )
        pollen_type_str = pollen_type_match.group(0).strip() if pollen_type_match else None

        if level_num is not None and level_text:
            print(f"[中国天气网] 西安花粉等级: {level_num}级 ({level_text})")
            return _build_pollen_result(level_num, level_text, pollen_type_str, source="中国天气网（国家卫生健康委/气象局联合发布）")

    except Exception as e:
        print(f"[花粉] 中国天气网抓取失败: {e}")

    # ── 方法2：备用 sojson API 里的 fl (风力) + 季节推算 ─────────────────────
    # sojson 天气接口无花粉字段，此处直接降级
    print("[花粉] 降级到季节估算")
    return _pollen_season_fallback()


def _build_pollen_result(level_num: int, level_text: str, pollen_type_raw, source: str) -> dict:
    """根据等级数字构建花粉结果字典"""
    # 等级标准化
    level_map = {
        1: "极低（1级）",
        2: "较低（2级）",
        3: "偏高（3级）",
        4: "较高（4级）",
        5: "很高（5级）",
    }
    stars_map = {1: "🌸", 2: "🌸🌸", 3: "🌸🌸🌸", 4: "🌸🌸🌸🌸", 5: "🌸🌸🌸🌸🌸"}

    # 各等级对应参考浓度（粒/m³），基于 NAB/WHO 花粉监测标准及中国研究数据
    grains_ref_map = {
        1: "< 50 粒/m³",
        2: "50 ~ 200 粒/m³",
        3: "200 ~ 500 粒/m³",
        4: "500 ~ 1000 粒/m³",
        5: "> 1000 粒/m³",
    }

    level_str = level_map.get(level_num, f"{level_text}（{level_num}级）")
    stars = stars_map.get(level_num, "🌸")
    grains_ref = grains_ref_map.get(level_num, "未知")

    # 花粉种类（若未从页面解析出，则按月推算）
    now = datetime.now()
    seasonal_type_map = {
        1: "花粉极少",
        2: "柏树、杨树花粉开始增加",
        3: "柏树、杨树、垂柳等木本植物花粉",
        4: "柳树、桦树、杨柳科等树木花粉",
        5: "树木花粉为主，草本花粉渐增",
        6: "草本花粉为主",
        7: "杂草花粉（菊科、禾本科）",
        8: "杂草花粉（豚草、蒿草）开始增加",
        9: "豚草、蒿草等杂草花粉高峰期",
        10: "杂草花粉减少，部分树木花粉",
        11: "花粉浓度下降",
        12: "花粉极少",
    }
    pollen_type = pollen_type_raw if pollen_type_raw else seasonal_type_map.get(now.month, "多种植物花粉")

    # 风险提示
    if level_num >= 4:
        risk_tip = "过敏人群需重点防护！外出请佩戴防护口罩和护目镜，归家后及时清洗鼻腔"
    elif level_num == 3:
        risk_tip = "敏感人群外出请注意防护，建议佩戴口罩"
    elif level_num == 2:
        risk_tip = "花粉浓度偏低，一般人群可正常活动，敏感人群适当注意"
    else:
        risk_tip = "花粉浓度很低，对一般人群无明显影响"

    # 出行建议（加入最佳外出时段提示）
    if level_num >= 3:
        outing_tip = "建议避开上午10:00–下午5:00（花粉传播高峰期）"
    else:
        outing_tip = "外出时间无特别限制"

    return {
        'level': f"{stars} {level_str}",
        'level_num': level_num,
        'type': pollen_type,
        'grains_ref': grains_ref,
        'risk_tip': risk_tip,
        'outing_tip': outing_tip,
        'source': source,
        'success': True,
    }


def _pollen_season_fallback() -> dict:
    """基于季节的花粉估算（兜底方案）"""
    now = datetime.now()
    month = now.month

    season_map = {
        1:  (1, "极低（1级）", "花粉极少"),
        2:  (2, "较低（2级）", "柏树、杨树花粉开始增加"),
        3:  (4, "较高（4级）", "柏树、杨树、垂柳等木本植物花粉高峰"),
        4:  (5, "很高（5级）", "柳树、桦树、杨柳科等树木花粉"),
        5:  (3, "偏高（3级）", "树木花粉为主，草本花粉渐增"),
        6:  (3, "偏高（3级）", "草本花粉为主"),
        7:  (2, "较低（2级）", "杂草花粉（菊科、禾本科）"),
        8:  (3, "偏高（3级）", "豚草、蒿草等杂草花粉开始增加"),
        9:  (4, "较高（4级）", "豚草、蒿草等杂草花粉高峰期"),
        10: (3, "偏高（3级）", "杂草花粉减少，部分树木花粉"),
        11: (2, "较低（2级）", "花粉浓度下降"),
        12: (1, "极低（1级）", "花粉极少"),
    }
    level_num, level_str, pollen_type = season_map.get(month, (2, "较低（2级）", "多种植物花粉"))
    result = _build_pollen_result(level_num, level_str.split("（")[0], pollen_type, source="季节估算（参考）")
    result['level'] = f"{result['level']}（⚠️ 估算数据，非实测）"
    return result


def build_weather_message(weather: dict, forecast: dict, aqi: dict, pollen: dict) -> str:
    """构建推送消息内容"""
    now = datetime.now()
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]

    # 计算明日日期
    tomorrow = now + timedelta(days=1)
    tomorrow_date = f"{tomorrow.month}月{tomorrow.day}日"

    day_after = now + timedelta(days=2)
    day_after_date = f"{day_after.month}月{day_after.day}日"

    # 生成温馨提示
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
| 🔬 参考浓度 | {pollen.get('grains_ref', '--')} |
| 🌿 主要花粉 | {pollen['type']} |
| ⚠️ 风险提示 | {pollen['risk_tip']} |
| 🕐 出行建议 | {pollen.get('outing_tip', '敏感人群注意防护')} |
| 📡 数据来源 | {pollen.get('source', '参考数据')} |

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

*数据来源：SoJSON天气API（天气/预报）& WAQI（AQI）& 中国天气网（花粉，国家卫生健康委/气象局联合发布） | 推送时间：{now.strftime('%H:%M')}*
"""
    return message


def generate_weather_image_from_data(weather: dict, forecast: dict, aqi: dict, pollen: dict) -> str:
    """
    使用 og-image.vercel.app 生成天气卡片图片
    返回图片 URL 或 None（如果生成失败）
    """
    try:
        from datetime import datetime
        from urllib.parse import quote
        
        now = datetime.now()
        date_str = f"{now.year}年{now.month}月{now.day}日"
        
        # 构建简洁的天气摘要
        weather_summary = f"天气: {weather['condition']}"
        temp_summary = f"气温: {weather['temp_low']}℃ ~ {weather['temp_high']}℃"
        
        # 构建 og-image URL
        base_url = "https://og-image.vercel.app"
        
        # 标题和副标题
        title = "西安天气早报"
        subtitle = f"{date_str} | {weather_summary} | {temp_summary}"
        
        # 如果需要，可以添加更多信息
        if aqi.get('success', False):
            subtitle += f" | AQI: {aqi.get('aqi', '--')}"
        
        # URL 编码
        encoded_title = quote(title)
        encoded_subtitle = quote(subtitle)
        
        # 构建图片 URL
        image_url = f"{base_url}/{encoded_title}/{encoded_subtitle}.png?theme=light&fontSize=80px"
        
        print(f"生成天气卡片图片: {image_url[:100]}...")
        return image_url
        
    except Exception as e:
        print(f"图片生成失败: {e}，改用文字推送")
        return None


def generate_weather_image(message: str) -> str:
    """
    通过在线 API 将 Markdown 消息转换成图片
    使用 og-image.vercel.app 免费 API
    返回图片 URL 或 None（如果生成失败）
    
    注意: 为了兼容性，保留这个函数，但实际使用新的 generate_weather_image_from_data
    """
    try:
        # 使用 og-image 服务生成简洁的天气卡片
        # 由于 Markdown 转图片比较复杂，这里返回 None
        # 实际图片生成使用 generate_weather_image_from_data 函数
        print("使用新的 generate_weather_image_from_data 函数生成图片")
        return None
        
    except Exception as e:
        print(f"图片生成失败: {e}，改用文字推送")
        return None


def push_to_wechat(title: str, content: str) -> bool:
    """通过 Server酱 推送到微信（原始文字版）"""
    try:
        session = requests.Session()
        session.trust_env = False  # 绕过系统代理
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


def push_to_wechat_with_image(title: str, content: str, image_url: str = None) -> bool:
    """
    通过 Server酱 推送到微信（支持在线图片）
    
    参数:
    - title: 消息标题
    - content: 消息内容（支持 Markdown，可以包含 ![](url) 格式的图片引用）
    - image_url: 图片 URL（如果提供，会被插入到消息中）
    """
    try:
        session = requests.Session()
        session.trust_env = False
        
        # 如果提供了图片 URL，在内容开头插入
        if image_url:
            # 检查内容中是否已经包含了图片
            if "![" not in content:
                content = f"![天气卡片]({image_url})\n\n{content}"
        
        # 直接使用 Server酱 推送
        return push_to_wechat(title, content)
        
    except Exception as e:
        print(f"推送异常: {e}")
        return push_to_wechat(title, content)


def main():
    print(f"=== 西安天气推送任务开始 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    # 获取天气数据
    print("正在获取天气数据...")
    weather = get_weather_xian()
    forecast = get_weather_forecast()
    aqi = get_aqi()
    pollen = get_pollen()

    if not weather['success']:
        print("天气数据获取失败，退出")
        sys.exit(1)

    print(f"今日天气: {weather['condition']}, {weather['temp_low']}~{weather['temp_high']}℃")

    # 构建消息
    title = f"西安天气早报 {datetime.now().strftime('%m/%d')}"
    content = build_weather_message(weather, forecast, aqi, pollen)

    # 图片生成
    image_url = None
    if GENERATE_IMAGE:
        print("正在生成天气卡片图片...")
        image_url = generate_weather_image_from_data(weather, forecast, aqi, pollen)
    
    # 推送到微信
    print("正在推送...")
    if image_url:
        # 在消息开头插入图片
        content_with_image = f"![天气卡片]({image_url})\n\n{content}"
        success = push_to_wechat_with_image(title, content_with_image)
    else:
        success = push_to_wechat_with_image(title, content)

    if success:
        print("✅ 推送成功！")
        sys.exit(0)
    else:
        print("❌ 推送失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
