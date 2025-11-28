import platform
import subprocess
import re
import time
import threading
import json
import webbrowser
import psutil
import collections
from flask import Flask, jsonify, render_template_string

# =================================================
# [配置区] 在这里手动填入你的路由器网关 IP
# 常见IP: "192.168.1.1", "192.168.0.1", "192.168.31.1", "192.168.5.1"
# =================================================
MANUAL_GATEWAY = "192.168.5.1"
# =================================================

# -------------- 诊断引擎 --------------

class NetworkDoctor:
    def __init__(self):
        # 保存最近 300 秒的数据（约 5 分钟）
        self.history = collections.deque(maxlen=300)
        self.diagnosis_color = "var(--p)"

    def analyze(self, stats):
        s_dbm = stats.get('signal_dbm', -100)
        pg = stats.get('gateway_ping', 0)
        pn = stats.get('internet_ping', 0)
        loss = stats.get('ping_loss', False)
        hw_err = stats.get('err_in', 0) + stats.get('err_out', 0)
        tx_pps = stats.get('tx_pps', 0)

        self.history.append({
            "time": time.time(),
            "signal_dbm": s_dbm,
            "gateway_ping": pg,
            "internet_ping": pn,
            "loss": loss,
            "hw_err": hw_err,
        })

        # 统计最近 5 分钟内的丢包次数和 Ping 波动
        loss_count = sum(1 for h in self.history if h["loss"])
        gw_pings = [h["gateway_ping"] for h in self.history if h["gateway_ping"] != 999]
        if gw_pings:
            stats["gw_min"] = min(gw_pings)
            stats["gw_max"] = max(gw_pings)
        sigs = [h["signal_dbm"] for h in self.history if h["signal_dbm"] < 0]
        if sigs:
            stats["sig_min"] = min(sigs)
            stats["sig_max"] = max(sigs)
        stats["loss_count"] = loss_count

        # 1. 硬件错误
        if hw_err > 5:
            self.diagnosis_color = "var(--alert)"
            return "硬件故障: 网卡错误计数持续增加，请检查/重装驱动或更换网卡。"

        # 2. 丢包（本地段）
        if loss:
            if s_dbm > -65:
                # 信号好但丢包 -> 干扰或扫描
                if self.detect_periodic_loss():
                    self.diagnosis_color = "var(--warn)"
                    return "周期性丢包: 疑似 Windows 后台扫描 WiFi，建议关闭自动扫描/漫游增强。"
                else:
                    self.diagnosis_color = "var(--alert)"
                    return "强干扰: 信号强但本地丢包，可能是同信道干扰或临时屏蔽（2.4G 常见）。"
            else:
                self.diagnosis_color = "var(--alert)"
                return f"物理信号过弱 ({s_dbm} dBm): 穿墙或距离过远导致链路断开。"

        # 3. 高内网延迟
        if pg > 50 and pg != 999:
            if tx_pps > 800:
                self.diagnosis_color = "var(--warn)"
                return "路由器过载/缓冲膨胀(Bufferbloat): 内网流量过大，路由器处理排队。"
            elif s_dbm > -65:
                self.diagnosis_color = "var(--warn)"
                return "信道拥堵: 信号良好但内网延迟高，邻居 WiFi 或同频设备干扰。"
            else:
                self.diagnosis_color = "var(--warn)"
                return "边缘信号: 信号偏弱+高延迟，建议靠近路由器或减少障碍物。"

        # 4. 外网问题
        if pn > 150 and pg < 10 and pg != 999:
            self.diagnosis_color = "#0ff"
            return "运营商/光猫问题: 内网正常但外网延迟/丢包严重，建议重启光猫或联系 ISP。"

        # 5. 稳定状态
        self.diagnosis_color = "var(--p)"
        if s_dbm > -50:
            return "系统稳定: 信号强、内外延迟正常。"
        if s_dbm > -70:
            return "系统基本稳定: 信号中等，偶有波动属正常范围。"
        return "系统可用: 信号偏弱，建议不要频繁移动设备。"

    def detect_periodic_loss(self):
        # 检测丢包是否有“固定节奏”，以判断是否是后台扫描导致
        loss_indices = [i for i, h in enumerate(self.history) if h["loss"]]
        if len(loss_indices) < 3:
            return False
        intervals = [loss_indices[i + 1] - loss_indices[i] for i in range(len(loss_indices) - 1)]
        if not intervals:
            return False
        avg = sum(intervals) / len(intervals)
        return all(abs(iv - avg) < 2 for iv in intervals)

doctor = NetworkDoctor()
app = Flask(__name__)

# -------------- 全局状态 --------------

current_stats = {
    "ssid": "Scanning...",
    "interface_name": "Init...",
    "signal_quality": 0,
    "signal_dbm": -100,
    "link_speed_mbps": 0,
    "gateway_ip": "Unknown",
    "gateway_ping": 0,
    "internet_ping": 0,
    "ping_loss": False,
    "tx_speed": 0,
    "rx_speed": 0,
    "tx_pps": 0,
    "rx_pps": 0,
    "drop_in": 0,
    "drop_out": 0,
    "err_in": 0,
    "err_out": 0,
    # 扩展统计
    "loss_count": 0,
    "gw_min": 0,
    "gw_max": 0,
    "sig_min": -100,
    "sig_max": -100,
    # 诊断信息
    "diagnosis": "Initializing...",
    "diag_color": "#0f0",
}

# -------------- 工具函数 --------------

def get_cmd_out(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode("gbk", "ignore")
    except Exception:
        try:
            return subprocess.check_output(cmd, shell=True).decode("utf-8", "ignore")
        except Exception:
            return ""

def find_gateway():
    if MANUAL_GATEWAY:
        return MANUAL_GATEWAY
    # 备用自动检测
    try:
        if platform.system() == "Windows":
            out = get_cmd_out("ipconfig")
            matches = re.findall(r"(?:Default Gateway|默认网关)[ .]*: ((?:\d{1,3}\.){3}\d{1,3})", out)
            for ip in matches:
                if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                    return ip
        elif platform.system() == "Darwin":
            m = re.search(r"default\s+((?:\d{1,3}\.){3}\d{1,3})", get_cmd_out("netstat -nr"))
            if m:
                return m.group(1)
        else:
            m = re.search(r"default via ((?:\d{1,3}\.){3}\d{1,3})", get_cmd_out("ip route show"))
            if m:
                return m.group(1)
    except Exception:
        pass
    return "Unknown"

def get_wifi_phy():
    if platform.system() != "Windows":
        return "Non-Win", 0, -100, 0.0

    out = get_cmd_out("netsh wlan show interfaces")

    # SSID
    ssid_match = re.search(r"SSID\s*[:：]\s*(.+)", out)
    ssid = ssid_match.group(1).strip() if ssid_match else "Unknown"

    # RSSI / 信号
    rssi_match = re.search(r"Rssi\s*[:：]\s*(-?\d+)", out)
    if rssi_match:
        rssi = int(rssi_match.group(1))
        qual = min(100, max(0, 2 * (rssi + 100)))
    else:
        sig_match = re.search(r"(?:Signal|信号)\s*[:：]\s*(\d+)%", out)
        qual = int(sig_match.group(1)) if sig_match else 0
        rssi = (qual / 2) - 100

    # 链接速率
    speed = 0.0
    try:
        speed_match = re.search(r"(?:Transmit rate|传输速率).*?[:：]\s*([\d\.]+)", out)
        if speed_match:
            speed = float(speed_match.group(1))
        else:
            mbps_match = re.search(r"(\d+)\s*Mbps", out, re.IGNORECASE)
            if mbps_match:
                speed = float(mbps_match.group(1))
    except Exception:
        speed = 0.0

    return ssid, qual, rssi, speed

# IO 统计
last_io = [0, 0, 0, 0, time.time()]

def update_io():
    global last_io
    try:
        stats = psutil.net_if_stats()
        iface = next(
            (k for k, v in stats.items() if v.isup and any(x in k for x in ["WLAN", "Wi-Fi", "Wireless"])),
            None,
        )
        if not iface:
            iface = next((k for k, v in stats.items() if v.isup and "Loop" not in k), None)

        current_stats["interface_name"] = iface if iface else "No Iface"
        if not iface:
            return

        c = psutil.net_io_counters(pernic=True).get(iface)
        now = time.time()
        dt = now - last_io[4]
        if dt < 0.8:
            return

        current_stats["tx_speed"] = round(((c.bytes_sent - last_io[0]) / dt) / 1024, 1)
        current_stats["rx_speed"] = round(((c.bytes_recv - last_io[1]) / dt) / 1024, 1)
        current_stats["tx_pps"] = int((c.packets_sent - last_io[2]) / dt)
        current_stats["rx_pps"] = int((c.packets_recv - last_io[3]) / dt)
        current_stats["drop_in"] = c.dropin
        current_stats["drop_out"] = c.dropout
        current_stats["err_in"] = c.errin
        current_stats["err_out"] = c.errout

        last_io = [c.bytes_sent, c.bytes_recv, c.packets_sent, c.packets_recv, now]
    except Exception:
        pass

def do_ping(host):
    if not host or host in ["Unknown", "Error"]:
        return 999
    param = "-n" if platform.system() == "Windows" else "-c"
    try:
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(
            ["ping", param, "1", "-w", "1000", host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
        )
        if res.returncode == 0:
            m = re.search(r"[=<]\s*(\d+)ms", res.stdout.decode("gbk", "ignore"))
            return int(m.group(1)) if m else 1
        return 999
    except Exception:
        return 999

# -------------- 主循环 --------------

def loop():
    print(f"[*] System Online. Targeting Gateway: {MANUAL_GATEWAY if MANUAL_GATEWAY else 'Auto'}")
    while True:
        gw = find_gateway()
        current_stats["gateway_ip"] = gw

        ssid, qual, rssi, speed = get_wifi_phy()
        current_stats["ssid"] = ssid
        current_stats["signal_quality"] = qual
        current_stats["signal_dbm"] = rssi
        current_stats["link_speed_mbps"] = speed

        update_io()

        pg = do_ping(gw)
        pn = do_ping("223.5.5.5")
        current_stats["gateway_ping"] = pg
        current_stats["internet_ping"] = pn
        current_stats["ping_loss"] = pg == 999 or pn == 999

        diag_text = doctor.analyze(current_stats)
        current_stats["diagnosis"] = diag_text
        current_stats["diag_color"] = doctor.diagnosis_color

        time.sleep(1)

threading.Thread(target=loop, daemon=True).start()

# -------------- 前端 --------------

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>NET.DOCTOR // EXTENDED VIEW</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
    :root { --p:#0f0; --warn:#ffb000; --alert:#f00; }
    body { background:#050505; color:var(--p); font-family:'Share Tech Mono', monospace; margin:0; height:100vh;
           display:grid; grid-template-rows:auto 1fr auto; gap:10px; padding:10px; overflow:hidden; }
    .header { border-bottom:2px solid var(--p); display:flex; justify-content:space-between; padding-bottom:5px; font-size:0.9rem; }
    .grid { display:grid; grid-template-columns:1.2fr 1.4fr 1.4fr; gap:10px; height:100%; }
    .panel { border:1px solid #333; background:rgba(0,30,0,0.35); padding:10px; display:flex; flex-direction:column; position:relative; }
    .panel-title { font-size:0.8rem; color:#888; margin-bottom:4px; }
    .val { font-size:2.2rem; font-weight:bold; }
    .sub { font-size:0.8rem; color:#888; }
    .diag-bar { border:2px solid #333; padding:10px 15px; font-size:1rem; background:#000; color:#fff; display:flex; align-items:center; min-height:60px; }
    .diag-label { margin-right:10px; color:var(--warn); }
    canvas { width:100%; height:90px; flex-grow:1; image-rendering:pixelated; }
</style>
</head>
<body>
    <div class="header">
        <div>NET.DOCTOR // EXTENDED VIEW</div>
        <div>GW: <span id="gw-ip" style="color:#fff">...</span> | IFACE: <span id="iface" style="color:#fff">...</span></div>
    </div>

    <div class="grid">
        <!-- 左：物理层 + 信号历史区间 -->
        <div class="panel">
            <div class="panel-title">PHYSICAL LAYER</div>
            <div><span id="dbm" class="val">--</span> dBm</div>
            <div class="sub">LINK: <span id="link">--</span> Mbps</div>
            <div class="sub">SSID: <span id="ssid" style="color:#fff">...</span></div>
            <div class="sub" style="margin-top:6px;">
                RSSI 5min: <span id="sig-min">--</span> dBm → <span id="sig-max">--</span> dBm
            </div>
        </div>

        <!-- 中：延迟 + 5 分钟波形 + Ping 区间 -->
        <div class="panel">
            <div class="panel-title">LATENCY (GATEWAY / INTERNET)</div>
            <div style="display:flex; gap:20px;">
                <div><span id="pg" class="val">--</span><span class="sub"> ms</span></div>
                <div><span id="pn" class="val" style="opacity:0.7">--</span><span class="sub"> ms</span></div>
            </div>
            <div class="sub" style="margin-top:6px;">
                GW 5min: <span id="gw-min">--</span> ms → <span id="gw-max">--</span> ms |
                LOSS: <span id="loss-count">0</span>
            </div>
            <canvas id="c_ping"></canvas>
        </div>

        <!-- 右：流量 + 5 分钟带宽图 -->
        <div class="panel">
            <div class="panel-title">THROUGHPUT (5min)</div>
            <div>
                <span id="rx" class="val">0</span><span class="sub"> KB/s DN</span> /
                <span id="tx" class="val">0</span><span class="sub"> KB/s UP</span>
            </div>
            <div class="sub">
                PPS: <span id="pps">0</span> |
                ERR: <span id="err" style="color:var(--alert)">0</span>
            </div>
            <canvas id="c_traf"></canvas>
        </div>
    </div>

    <div class="diag-bar" id="diag-box">
        <span class="diag-label">[DIAGNOSIS]</span>
        <span id="diag-text">SYSTEM ANALYZING...</span>
    </div>

    <script>
        class Line {
            constructor(id, color) {
                this.c = document.getElementById(id);
                this.ctx = this.c.getContext('2d');
                this.color = color;
                this.data = new Array(300).fill(0); // ~5分钟
                window.addEventListener('resize', () => this.resize());
                this.resize();
            }
            resize() {
                this.c.width = this.c.clientWidth;
                this.c.height = this.c.clientHeight;
            }
            add(v) {
                this.data.push(v);
                this.data.shift();
            }
            draw(maxVal) {
                const width = this.c.width;
                const height = this.c.height;
                this.ctx.clearRect(0, 0, width, height);
                this.ctx.beginPath();
                this.ctx.strokeStyle = this.color;
                this.ctx.lineWidth = 1.5;
                const n = this.data.length;
                const step = width / (n - 1);
                for (let i = 0; i < n; i++) {
                    const v = this.data[i];
                    const nv = maxVal > 0 ? Math.min(v / maxVal, 1) : 0;
                    const y = height - nv * height;
                    if (i === 0) this.ctx.moveTo(0, y);
                    else this.ctx.lineTo(i * step, y);
                }
                this.ctx.stroke();
            }
        }

        const pingLine = new Line('c_ping', '#0f0');
        const trafLine = new Line('c_traf', '#0ff');

        setInterval(() => {
            fetch('/api/data').then(r => r.json()).then(d => {
                document.getElementById('gw-ip').innerText = d.gateway_ip;
                document.getElementById('iface').innerText = d.interface_name;
                document.getElementById('ssid').innerText = d.ssid;

                document.getElementById('dbm').innerText = d.signal_dbm;
                document.getElementById('link').innerText = d.link_speed_mbps;

                document.getElementById('pg').innerText = d.gateway_ping;
                document.getElementById('pn').innerText = d.internet_ping;

                document.getElementById('rx').innerText = d.rx_speed;
                document.getElementById('tx').innerText = d.tx_speed;
                document.getElementById('pps').innerText = d.rx_pps + d.tx_pps;
                document.getElementById('err').innerText = d.err_in + d.err_out;

                document.getElementById('loss-count').innerText = d.loss_count || 0;
                document.getElementById('gw-min').innerText = (d.gw_min || 0);
                document.getElementById('gw-max').innerText = (d.gw_max || 0);
                document.getElementById('sig-min').innerText = (d.sig_min || 0);
                document.getElementById('sig-max').innerText = (d.sig_max || 0);

                const db = document.getElementById('diag-box');
                const dt = document.getElementById('diag-text');
                dt.innerText = d.diagnosis;
                db.style.borderColor = d.diag_color;
                dt.style.color = d.diag_color;

                pingLine.add(d.gateway_ping === 999 ? 200 : d.gateway_ping);
                pingLine.draw(200);

                trafLine.add(d.rx_speed);
                trafLine.draw(2000);
            });
        }, 1000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/data")
def api_data():
    return jsonify(current_stats)

if __name__ == "__main__":
    print(f"[*] System Online. Targeting Gateway: {MANUAL_GATEWAY if MANUAL_GATEWAY else 'Auto'}")
    webbrowser.open("http://127.0.0.1:5000")
    app.run(port=5000)
