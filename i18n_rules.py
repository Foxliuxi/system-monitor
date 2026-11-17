#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
i18n_rules.py —— 分析引擎的文案表（中 / 英）

为什么把文案从 analyzer.py 抽出来：
  analyzer 里原本每条规则都是内联中文 f-string。加英文意味着每处都写两遍，
  逻辑和文案搅在一起，改一个数字要读三段话。抽成模板后，analyzer 只剩
  "什么条件、扣多少分"这类真正的逻辑，文案改动集中在同一个文件里。

占位符用 {name}，由 analyzer 用 .format(**kw) 填。文案里不能出现裸的
花括号 —— 会直接抛异常，这点在 tests/test_i18n_rules.py 里有校验。
"""

CATS = {
    "link":     {"zh": "链路媒介",   "en": "Link medium"},
    "integrity": {"zh": "数据完整性", "en": "Data integrity"},
    "throughput": {"zh": "吞吐能力", "en": "Throughput"},
    "host":     {"zh": "主机算力",   "en": "Host compute"},
    "power":    {"zh": "电源策略",   "en": "Power policy"},
    "e2e":      {"zh": "端到端质量", "en": "End-to-end"},
    "overall":  {"zh": "总体",       "en": "Overall"},
}

RULES = {
    # ---------------------------------------------------------- A. 链路媒介
    "wired_idle": {
        "cat": "link",
        "zh": {
            "title": "千兆有线口空着，当前走无线",
            "detail": "当前承载业务的是「{active_desc}」，链路 {link:.0f} Mbps{radio}；"
                      "而「{eth_desc}」具备 {eth_speed:.0f} Mbps 能力却处于 {eth_status}。",
            "advice": "插上网线可把上限提到 {eth_speed:.0f} Mbps{ratio}，"
                      "更关键的是有线没有空口重传，RTT 抖动通常从毫秒级降到 <1ms。"
                      "这是零成本收益最高的一步：先插线，再谈其他优化。",
        },
        "en": {
            "title": "Gigabit Ethernet port is idle while Wi-Fi carries the traffic",
            "detail": "Traffic is currently on \"{active_desc}\" at {link:.0f} Mbps{radio}, "
                      "while \"{eth_desc}\" can do {eth_speed:.0f} Mbps but is {eth_status}.",
            "advice": "Plugging in a cable raises the ceiling to {eth_speed:.0f} Mbps{ratio}. "
                      "More importantly, wired links have no over-the-air retransmission — "
                      "RTT jitter typically drops from milliseconds to under 1 ms. "
                      "Highest payoff for zero cost: plug it in before optimizing anything else.",
        },
    },
    "band_24": {
        "cat": "link",
        "zh": {
            "title": "无线工作在 2.4GHz 拥挤频段",
            "detail": "当前 {radio}，{band}，通道 {channel}。"
                      "2.4GHz 只有 1/6/11 三个互不重叠信道，蓝牙耳机、无线键鼠、微波炉、邻居 AP "
                      "都在同一段频谱上，冲突后退避重传——表现出来就是延迟忽高忽低、打游戏跳 ping。",
            "advice": "登录路由器后台，把 2.4G 与 5G 拆成两个不同 SSID，电脑连 5GHz。"
                      "802.11ac 下 5GHz 通常能跑 433-866Mbps，且干扰源少一个量级。",
        },
        "en": {
            "title": "Wi-Fi is running on the crowded 2.4 GHz band",
            "detail": "Currently {radio}, {band}, channel {channel}. "
                      "2.4 GHz only has three non-overlapping channels (1/6/11), and Bluetooth "
                      "headsets, wireless peripherals, microwave ovens and neighbours' APs all "
                      "share this spectrum. Collisions trigger backoff and retransmission — "
                      "exactly what shows up as erratic latency and ping spikes in games.",
            "advice": "Split 2.4 GHz and 5 GHz into separate SSIDs on the router and connect the "
                      "PC to 5 GHz. Under 802.11ac it usually runs 433-866 Mbps with an order of "
                      "magnitude fewer interferers.",
        },
    },
    "sig_weak": {
        "cat": "link",
        "zh": {
            "title": "无线信号过弱",
            "detail": "信号强度仅 {sig:.0f}%。低于 35% 时速率会大幅回退、丢包明显上升，"
                      "这是物理层问题，任何软件优化都救不回来。",
            "advice": "把 USB 网卡用延长线挪到桌面开阔处（别插在机箱背面贴墙的接口），"
                      "或换带外置天线的型号；路由器与电脑之间减少承重墙。",
        },
        "en": {
            "title": "Wi-Fi signal is too weak",
            "detail": "Signal strength is only {sig:.0f}%. Below 35% the link rate falls back "
                      "sharply and loss climbs. This is a physical-layer problem — no software "
                      "tweak can fix it.",
            "advice": "Move the USB adapter to open space on the desk using an extension cable "
                      "(avoid rear ports against a wall), or switch to a model with an external "
                      "antenna; reduce the number of load-bearing walls between router and PC.",
        },
    },
    "sig_low": {
        "cat": "link",
        "zh": {
            "title": "无线信号偏弱",
            "detail": "信号强度 {sig:.0f}%。低于 55% 时空口速率协商会降档，吞吐与稳定性都会打折。",
            "advice": "调整 USB 网卡位置或用延长线抬高，避开机箱金属遮挡。",
        },
        "en": {
            "title": "Wi-Fi signal is weak",
            "detail": "Signal strength is {sig:.0f}%. Below 55% the negotiated link rate drops a "
                      "tier, costing both throughput and stability.",
            "advice": "Reposition the USB adapter or raise it on an extension cable, clear of the "
                      "metal case.",
        },
    },
    "usb_wifi": {
        "cat": "link",
        "zh": {
            "title": "USB 无线网卡的物理限制",
            "detail": "USB 网卡靠总线供电，且天线尺寸远小于 PCIe 网卡与外置天线。"
                      "更麻烦的是：USB 3.0 接口与线缆在工作时会在 2.4GHz 附近产生宽带噪声，"
                      "USB3 设备离网卡越近，2.4G 收包错误率越高（这是可复现的实测现象）。",
            "advice": "把网卡插在远离 USB3 硬盘/扩展坞的接口，优先用 USB 2.0 延长线拉开距离；"
                      "长期方案还是走有线或换 PCIe 无线网卡。",
        },
        "en": {
            "title": "Physical limits of USB Wi-Fi adapters",
            "detail": "USB adapters draw power from the bus and have far smaller antennas than "
                      "PCIe cards. Worse, USB 3.0 ports and cables emit broadband noise around "
                      "2.4 GHz while active — the closer a USB3 device sits to the adapter, the "
                      "higher the 2.4 GHz receive error rate (reproducible in practice).",
            "advice": "Move the adapter away from USB3 drives and docks; a USB 2.0 extension "
                      "cable buys distance. Long term, go wired or switch to a PCIe Wi-Fi card.",
        },
    },
    "wired_100": {
        "cat": "link",
        "zh": {
            "title": "有线链路只协商到百兆",
            "detail": "链路速率 {link:.0f} Mbps。千兆网卡跑出百兆，绝大多数是网线问题："
                      "只有 4 芯的劣质线、水晶头氧化/压接不良、或墙内面板接线错误。",
            "advice": "换一根超五类以上（Cat5e/Cat6）成品线直连路由器和电脑，绕过墙内线路验证；"
                      "若直连能到 1000Mbps，问题就在墙内线或面板。",
        },
        "en": {
            "title": "Wired link negotiated at 100 Mbps only",
            "detail": "Link rate is {link:.0f} Mbps. A gigabit NIC negotiating 100 Mbps is almost "
                      "always a cabling problem: cheap 4-wire cable, oxidised or badly crimped "
                      "connectors, or miswired wall panels.",
            "advice": "Test with a known-good Cat5e/Cat6 patch cable straight between router and "
                      "PC to bypass in-wall wiring. If it links at 1000 Mbps, the wall run or "
                      "panel is the culprit.",
        },
    },

    # ---------------------------------------------------------- B. 错误与丢弃
    "nic_err": {
        "cat": "integrity",
        "zh": {
            "title": "网卡错误计数在增长",
            "detail": "本次采样新增错误包 {err_d} 个（累计 RX {err_in} / TX {err_out}）。"
                      "网卡错误不是「网速慢」，是物理层在纠错：无线侧多为信号弱/干扰，"
                      "有线侧多为线缆或接口接触问题。",
            "advice": "先看信号强度与频段；有线则换线换口。若两者都正常，更新网卡驱动。",
        },
        "en": {
            "title": "NIC error counters are rising",
            "detail": "{err_d} new errored packets in this sample (cumulative RX {err_in} / "
                      "TX {err_out}). NIC errors are not \"slow internet\" — they are the "
                      "physical layer correcting itself: weak signal or interference on Wi-Fi, "
                      "cable or contact problems on wired.",
            "advice": "Check signal strength and band first; on wired, swap the cable and port. "
                      "If both are fine, update the NIC driver.",
        },
    },
    "nic_drop": {
        "cat": "integrity",
        "zh": {
            "title": "出现丢包（drop）",
            "detail": "本次采样新增丢弃 {drop_d} 个包。与 error 不同，drop 通常是缓冲区不足或"
                      "上层来不及消费——高吞吐时出现属正常，空闲时出现就要查驱动与中断处理。",
            "advice": "观察是否只在跑满带宽时出现；空闲时也丢，考虑关闭网卡节能、更新驱动。",
        },
        "en": {
            "title": "Packet drops detected",
            "detail": "{drop_d} new dropped packets in this sample. Unlike errors, drops usually "
                      "mean buffer exhaustion or the stack failing to keep up — normal under "
                      "saturation, suspicious when idle.",
            "advice": "Check whether it only happens at full bandwidth. If it drops while idle, "
                      "disable NIC power saving and update the driver.",
        },
    },

    # ---------------------------------------------------------- C. 吞吐
    "link_saturated": {
        "cat": "throughput",
        "zh": {
            "title": "当前业务已接近链路上限",
            "detail": "下行 {down:.1f} Mbps，已达链路 {link:.0f} Mbps 的 {util:.0f}%。"
                      "无线链路跑到 75% 以上后，重传概率显著上升，其他应用会被挤掉。",
            "advice": "这是容量问题而不是故障：要么上 5GHz/有线扩带宽，要么给下载类任务限速。",
        },
        "en": {
            "title": "Traffic is close to the link ceiling",
            "detail": "Download is {down:.1f} Mbps, {util:.0f}% of the {link:.0f} Mbps link. "
                      "Above 75% on Wi-Fi, retransmission rises sharply and other apps get "
                      "starved.",
            "advice": "This is capacity, not a fault: move to 5 GHz or wired for more headroom, "
                      "or rate-limit bulk downloads.",
        },
    },
    "bw_idle_lat": {
        "cat": "throughput",
        "zh": {
            "title": "带宽空着但延迟很高",
            "detail": "下行仅 {down:.2f} Mbps，链路能力 {link:.0f} Mbps 远未用满，"
                      "但公网 RTT 平均 {pub_avg} ms。说明瓶颈不在带宽，在延迟链路。",
            "advice": "排查方向应是：无线重传、上游路由跳数、对端服务器位置，而不是升带宽套餐。",
        },
        "en": {
            "title": "Bandwidth is idle while latency stays high",
            "detail": "Download is only {down:.2f} Mbps out of {link:.0f} Mbps capacity, yet "
                      "public RTT averages {pub_avg} ms. The bottleneck is latency, not bandwidth.",
            "advice": "Look at Wi-Fi retransmission, upstream hop count and server distance — "
                      "not at buying a faster plan.",
        },
    },

    # ---------------------------------------------------------- D. 主机
    "cpu_full": {
        "cat": "host",
        "zh": {
            "title": "CPU 接近满载，协议栈被挤占",
            "detail": "CPU 总占用 {cpu:.0f}%。网络收发包要走内核协议栈与网卡中断，"
                      "CPU 打满时中断响应被推迟，表现为吞吐抖动、延迟尖刺，甚至 TCP 超时重传。",
            "advice": "找出吃 CPU 的进程；对高吞吐场景把网卡中断分散到多核，或降低并发。",
        },
        "en": {
            "title": "CPU near saturation is squeezing the network stack",
            "detail": "Total CPU usage is {cpu:.0f}%. Every packet traverses the kernel stack and "
                      "raises an interrupt; when CPU is maxed out, interrupt handling is delayed "
                      "— visible as throughput jitter, latency spikes and even TCP retransmits.",
            "advice": "Find the CPU hog. For high-throughput work, spread NIC interrupts across "
                      "cores or reduce concurrency.",
        },
    },
    "cpu_high": {
        "cat": "host",
        "zh": {
            "title": "CPU 占用偏高",
            "detail": "CPU 总占用 {cpu:.0f}%，已进入会影响中断响应的区间。",
            "advice": "确认是否有后台编译、杀毒全盘扫描、浏览器多标签在同时抢 CPU。",
        },
        "en": {
            "title": "CPU usage is elevated",
            "detail": "Total CPU usage is {cpu:.0f}%, high enough to affect interrupt response.",
            "advice": "Check for background compiles, full-disk antivirus scans, or a browser with "
                      "many tabs competing for CPU.",
        },
    },
    "single_core": {
        "cat": "host",
        "zh": {
            "title": "单核被打满，整体却很闲",
            "detail": "CPU {hot} 号核心占用 {core_max:.0f}%，而总体仅 {cpu:.0f}%。"
                      "这种形态非常典型：网卡中断/软中断集中绑定在单核上（RSS/RPS 未生效），"
                      "千兆以上链路会因此出现丢包，而你看总 CPU 曲线完全正常。",
            "advice": "若追求极限吞吐，可开启多队列 RSS、或把中断亲和性分散到多个核心；"
                      "日常使用不必处理。",
        },
        "en": {
            "title": "One core is pegged while overall usage looks idle",
            "detail": "Core {hot} is at {core_max:.0f}% while the total is only {cpu:.0f}%. "
                      "Classic signature of NIC interrupts/softirqs pinned to a single core "
                      "(RSS/RPS not effective). Links above 1 Gbps will drop packets because of "
                      "it, while the total CPU graph looks perfectly healthy.",
            "advice": "If you need maximum throughput, enable multi-queue RSS or spread IRQ "
                      "affinity across cores. For everyday use, no action needed.",
        },
    },
    "cpu_throttle": {
        "cat": "host",
        "zh": {
            "title": "CPU 处于降频运行",
            "detail": "当前 {cur:.0f} MHz / 标称 {max:.0f} MHz（{pct:.0f}%）。"
                      "降频时单次中断处理耗时变长，高包速率场景会放大延迟抖动。",
            "advice": "把电源计划切到「高性能/卓越性能」，并检查是否因温度触发了降频。",
        },
        "en": {
            "title": "CPU is running below its rated clock",
            "detail": "Currently {cur:.0f} MHz of {max:.0f} MHz rated ({pct:.0f}%). At lower "
                      "clocks each interrupt takes longer, amplifying latency jitter under high "
                      "packet rates.",
            "advice": "Switch the power plan to High performance, and check whether thermal "
                      "throttling is the cause.",
        },
    },
    "mem_pressure": {
        "cat": "host",
        "zh": {
            "title": "内存压力大",
            "detail": "内存占用 {mem:.0f}%（{used}/{total} GB）。"
                      "内存紧张会压缩 socket 缓冲区与页缓存，大流量传输容易触发重传。",
            "advice": "关掉不用的浏览器标签与虚拟机；长期看要加内存。",
        },
        "en": {
            "title": "High memory pressure",
            "detail": "Memory usage is {mem:.0f}% ({used}/{total} GB). Tight memory shrinks socket "
                      "buffers and page cache, which makes bulk transfers prone to retransmission.",
            "advice": "Close unused browser tabs and VMs; longer term, add RAM.",
        },
    },
    "power_plan": {
        "cat": "power",
        "zh": {
            "title": "电源计划可能让网卡降速",
            "detail": "当前电源计划「{plan}」。平衡/节能模式会启用 PCIe ASPM 与网卡省电，"
                      "空闲后重新唤醒有额外延迟，表现为「停一会儿再动就卡一下」。",
            "advice": "控制面板 → 电源选项 → 高性能；或在设备管理器里取消网卡的"
                      "「允许计算机关闭此设备以节约电源」。",
        },
        "en": {
            "title": "The power plan may be slowing the NIC down",
            "detail": "Current plan is \"{plan}\". Balanced/Power saver enables PCIe ASPM and NIC "
                      "power saving; waking from idle adds latency — the familiar \"pause, then "
                      "stutter\" pattern.",
            "advice": "Control Panel → Power Options → High performance; or untick \"Allow the "
                      "computer to turn off this device to save power\" for the NIC in Device "
                      "Manager.",
        },
    },

    # ---------------------------------------------------------- E. 端到端
    "probe_fail": {
        "cat": "e2e",
        "zh": {
            "title": "公网探测本身失败，丢包率无法取信",
            "detail": "最近 {att} 次探测里有 {err} 次连包都没发出去：{detail}。"
                      "这类失败是「解析不到 / 路由不通 / ICMP 被拦截」，不是丢包，"
                      "所以不会计入丢包率。",
            "advice": "换一个能通的探测目标（启动参数 --ping-target），或改用 TCP 建连时间判断质量。",
        },
        "en": {
            "title": "Public probes are failing — loss figures are unreliable",
            "detail": "{err} of the last {att} probes never even left the host: {detail}. "
                      "These are resolution failures, unreachable routes or blocked ICMP — not "
                      "packet loss, so they are excluded from the loss rate.",
            "advice": "Pick a reachable target (--ping-target) or judge quality by TCP connect "
                      "time instead.",
        },
    },
    "gw_loss": {
        "cat": "e2e",
        "zh": {
            "title": "到网关就丢包，问题在本地",
            "detail": "最近 {n} 次有效探测中，到网关丢包 {loss}%（超时 {to} 次 / 共 {att} 次）。"
                      "探测超时窗口 {timeout}ms，网关是第一跳，"
                      "这一段丢包说明问题在你自己的链路：无线干扰、网线、网卡驱动、路由器。",
            "advice": "换运营商、升带宽都不会有任何改善。"
                      "有线：换线换口；无线：换 5GHz 或靠近路由器。先修复第一跳。",
        },
        "en": {
            "title": "Loss starts at the gateway — the problem is local",
            "detail": "Across {n} valid probes, {loss}% were lost to the gateway ({to} timeouts "
                      "out of {att}). Timeout window is {timeout} ms. The gateway is the "
                      "first hop, so loss here points at your own link: Wi-Fi interference, "
                      "cabling, NIC driver or the router.",
            "advice": "Changing ISP or buying a faster plan will not help. Wired: swap cable and "
                      "port. Wi-Fi: move to 5 GHz or get closer. Fix the first hop first.",
        },
    },
    "pub_loss": {
        "cat": "e2e",
        "zh": {
            "title": "本地链路干净，公网侧有丢包",
            "detail": "到网关不丢包，但到 {target} 丢包 {loss}%"
                      "（超时 {to} 次 / 共 {att} 次，超时窗口 {timeout}ms）。"
                      "这说明从路由器往上（运营商/骨干网/对端）有问题，本地硬件与 WiFi 是无辜的。",
            "advice": "记录丢包时间段，联系运营商报障时提供这个数据；"
                      "跨境/跨网访问出现丢包属常态，可换条线路缓解。",
        },
        "en": {
            "title": "Local link is clean — loss appears upstream",
            "detail": "No loss to the gateway, but {loss}% loss to {target} "
                      "({to} timeouts out of {att}, window {timeout} ms). The problem sits "
                      "above the router — ISP, backbone or the far end. Your hardware and Wi-Fi "
                      "are not at fault.",
            "advice": "Note the time window and give it to your ISP when filing a ticket. "
                      "Cross-border routes dropping packets is normal; try an alternative path.",
        },
    },
    "gw_latency": {
        "cat": "e2e",
        "zh": {
            "title": "到网关延迟偏高",
            "detail": "到网关平均 {gw} ms。健康的有线应在 1ms 内，健康无线在 3ms 内。"
                      "超过 6ms 基本可以判定空口存在重传等待。",
            "advice": "结合信号强度与频段一起看：信号弱就挪位置，2.4GHz 就换 5GHz。",
        },
        "en": {
            "title": "Gateway latency is high",
            "detail": "Average {gw} ms to the gateway. A healthy wired link stays under 1 ms, "
                      "healthy Wi-Fi under 3 ms. Above 6 ms almost certainly means over-the-air "
                      "retransmission.",
            "advice": "Read it together with signal strength and band: weak signal → move closer; "
                      "2.4 GHz → switch to 5 GHz.",
        },
    },
    "upstream_latency": {
        "cat": "e2e",
        "zh": {
            "title": "主要延迟来自上游，不是你的硬件",
            "detail": "第一跳 {gw} ms，公网 {target} 平均 {pub} ms，"
                      "上游贡献约 {up:.0f} ms。本地硬件与 WiFi 只占很小一部分。",
            "advice": "这部分延迟无法通过换网卡、插网线改善；能动的只有选择更近的服务节点。",
        },
        "en": {
            "title": "Most of the latency comes from upstream, not your hardware",
            "detail": "First hop {gw} ms, {target} averages {pub} ms — upstream accounts for about "
                      "{up:.0f} ms. Local hardware and Wi-Fi contribute very little.",
            "advice": "This latency cannot be fixed by a new NIC or a cable. The only lever is "
                      "choosing a closer service endpoint.",
        },
    },
    "jitter": {
        "cat": "e2e",
        "zh": {
            "title": "延迟抖动大，实时业务会受影响",
            "detail": "公网 RTT 抖动 {jitter} ms（相邻采样平均变化量）。"
                      "抖动比平均延迟更影响视频会议、游戏、远程桌面——平均 30ms 但抖动 80ms，"
                      "体感比稳定的 80ms 还差。",
            "advice": "抖动主要来自无线重传与链路拥塞，优先改有线或 5GHz；"
                      "实时业务可开 QoS 优先队列。",
        },
        "en": {
            "title": "High latency jitter hurts real-time traffic",
            "detail": "Public RTT jitter is {jitter} ms (mean change between adjacent samples). "
                      "Jitter matters more than average latency for calls, games and remote "
                      "desktop — 30 ms average with 80 ms jitter feels worse than a steady 80 ms.",
            "advice": "Jitter comes mostly from Wi-Fi retransmission and congestion: prefer wired "
                      "or 5 GHz. For real-time apps, enable QoS priority queues.",
        },
    },
    "dns_slow": {
        "cat": "e2e",
        "zh": {
            "title": "DNS 解析慢",
            "detail": "解析域名耗时 {ms} ms。DNS 只在建连时用，但慢一次就是"
                      "整个页面白屏等待——用户感知上非常明显。",
            "advice": "把 DNS 换成 223.5.5.5 / 119.29.29.29，并在本机做 DNS 缓存；"
                      "浏览器开 DoH 也可缓解。",
        },
        "en": {
            "title": "DNS resolution is slow",
            "detail": "Resolving a hostname took {ms} ms. DNS is only used when a connection is "
                      "established, but one slow lookup means a blank screen — extremely visible "
                      "to the user.",
            "advice": "Switch to a faster resolver (223.5.5.5 or 119.29.29.29), enable local DNS "
                      "caching, or turn on DoH in the browser.",
        },
    },
    "all_ok": {
        "cat": "overall",
        "zh": {
            "title": "未发现硬件层面的明显短板",
            "detail": "链路、错误计数、主机资源、端到端延迟均无异常项。",
            "advice": "保持现状即可。若仍有体感卡顿，问题多半在具体应用或对端服务器，不在本机网络栈。",
        },
        "en": {
            "title": "No obvious hardware-level bottlenecks found",
            "detail": "Link, error counters, host resources and end-to-end latency all look "
                      "normal.",
            "advice": "Nothing to change. If things still feel slow, the cause is likely a "
                      "specific app or the remote server, not your local network stack.",
        },
    },
}

# 一句话结论（顶栏下面那行）
SUMMARY = {
    "crit": {
        "zh": "存在 {n} 项严重问题：「{head}」——建议先处理它，其余优化都是次要的。",
        "en": "{n} critical issue(s): \"{head}\" — fix that first, everything else is secondary.",
    },
    "warn_wired": {
        "zh": "当前健康度 {score}/100。最值得做的一件事：插上网线，把「{nic}」用起来。"
              "此外还有 {n} 项待改善。",
        "en": "Health score {score}/100. The single best move: plug in a cable and put \"{nic}\" "
              "to use. {n} other item(s) could be improved.",
    },
    "warn": {
        "zh": "当前健康度 {score}/100，主要短板是「{head}」，共 {n} 项待改善。",
        "en": "Health score {score}/100. Main weak spot: \"{head}\". {n} item(s) to improve.",
    },
    "ok": {
        "zh": "当前健康度 {score}/100，未发现硬件层面的明显短板。",
        "en": "Health score {score}/100 — no obvious hardware-level bottlenecks.",
    },
}

# 评分等级
GRADES = {
    "excellent": {"zh": "优秀", "en": "Excellent"},
    "good":      {"zh": "良好", "en": "Good"},
    "fair":      {"zh": "一般", "en": "Fair"},
    "poor":      {"zh": "较差", "en": "Poor"},
}


def render(rule_key, lang, **kw):
    """取某条规则的三段文案。lang 不是 en 时一律用中文。"""
    r = RULES[rule_key]
    pack = r["en"] if lang == "en" else r["zh"]
    cat = CATS[r["cat"]]
    return {
        "cat": cat["en"] if lang == "en" else cat["zh"],
        "title": pack["title"].format(**kw),
        "detail": pack["detail"].format(**kw),
        "advice": (pack.get("advice") or "").format(**kw),
    }


def summary(key, lang, **kw):
    pack = SUMMARY[key]
    return (pack["en"] if lang == "en" else pack["zh"]).format(**kw)


def grade(score, lang):
    key = ("excellent" if score >= 85 else
           "good" if score >= 70 else
           "fair" if score >= 50 else "poor")
    return GRADES[key]["en" if lang == "en" else "zh"]
