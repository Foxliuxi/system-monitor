#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyzer.py —— 硬件对网络影响的分析引擎
设计原则：每条结论必须能说清「哪个硬件 → 通过什么机制 → 影响哪个指标」。
不写"建议优化网络"这种正确但无用的废话。

输出结构：
  {
    "score": 0-100,
    "grade": "优秀|良好|一般|较差",
    "items": [{level, cat, title, detail, advice, metric}],
  }
level: critical / warn / info / ok
"""
import statistics
from collections import deque

import i18n_rules

# 权重：决定扣多少分，也决定前端排序
_LEVEL_ORDER = {"critical": 0, "warn": 1, "info": 2, "ok": 3}


class Analyzer:
    def __init__(self, profile, window=60, lang="zh"):
        self.profile = profile or {}
        self.lang = "en" if lang == "en" else "zh"
        self.hist = deque(maxlen=window)      # (ts, gw_rtt, pub_rtt, down, up, cpu)
        self.err_base = None                  # 错误计数基线，用于判断"是否在增长"
        self._err_samples = deque(maxlen=30)

    def _stats_from_probes(self, ps, fallback):
        """
        用探测线程的统计覆盖 hist 推算值。
        与旧实现的差别：分母是"真正发出去的探测次数"，且 error（解析失败/无路由）
        不混进丢包率——那两类失败在界面上必须能区分开，否则就是误报。
        """
        gw = ps.get("gateway") or {}
        pub = ps.get("public") or {}
        st = dict(fallback or {})
        st.update({
            "n": pub.get("valid") or 0,
            "gw_loss_pct": gw.get("loss_pct"),
            "pub_loss_pct": pub.get("loss_pct"),
            "gw_avg": gw.get("avg"),
            "pub_avg": pub.get("avg"),
            "pub_max": pub.get("max"),
            "jitter": pub.get("jitter"),
            "gw_attempts": gw.get("attempts"),
            "pub_attempts": pub.get("attempts"),
            "gw_timeout": gw.get("timeout"),
            "pub_timeout": pub.get("timeout"),
            "gw_error": gw.get("error"),
            "pub_error": pub.get("error"),
            "pub_detail": pub.get("last_detail") or "",
            "source": "probe",
        })
        return st

    # ------------------------------------------------------------ 累积统计
    def _stats(self):
        if not self.hist:
            return {}
        gw = [h[1] for h in self.hist]
        pub = [h[2] for h in self.hist]
        gw_ok = [x for x in gw if x is not None]
        pub_ok = [x for x in pub if x is not None]
        n = len(self.hist)
        return {
            "n": n,
            "gw_loss_pct": round((n - len(gw_ok)) / n * 100, 1),
            "pub_loss_pct": round((n - len(pub_ok)) / n * 100, 1),
            "gw_avg": round(statistics.mean(gw_ok), 1) if gw_ok else None,
            "pub_avg": round(statistics.mean(pub_ok), 1) if pub_ok else None,
            "pub_max": round(max(pub_ok), 1) if pub_ok else None,
            "jitter": (round(statistics.mean([abs(b - a) for a, b in zip(pub_ok, pub_ok[1:])]), 1)
                       if len(pub_ok) > 2 else None),
        }

    # ------------------------------------------------------------ 主网卡 / 备用网卡
    def _nics(self, sample):
        nics = self.profile.get("nics") or []
        active_name = (sample.get("nic") or {}).get("name")
        active = next((n for n in nics if n.get("name") == active_name), None)
        if active is None:
            active = next((n for n in nics if n.get("status") == "Up"), None)
        spare_wired = [
            n for n in nics
            if not n.get("is_wireless")
            and (n.get("nominal_speed_mbps") or 0) >= 100
            and "tap" not in (n.get("desc") or "").lower()
            and "vpn" not in (n.get("desc") or "").lower()
        ]
        return active, spare_wired

    # ------------------------------------------------------------ 文案里的小括号
    # 这两段是"附注"，不是结论本身，模板里放不下（中英标点/语序不同），
    # 所以按语言现拼，避免英文句子里夹着「通道」这种中文词。
    def _en(self):
        return self.lang == "en"

    def _radio_note(self, wifi):
        if not wifi:
            return ""
        r, b, c = wifi.get("radio"), wifi.get("band"), wifi.get("channel")
        return (f" ({r} / {b} / channel {c})" if self._en()
                else f"（{r} / {b} / 通道 {c}）")

    def _ratio_note(self, ratio):
        if not ratio:
            return ""
        return f" (~{ratio}x)" if self._en() else f"（约 {ratio} 倍）"

    # ------------------------------------------------------------ 主入口
    def analyze(self, sample, wifi, probe_stats=None):
        s = sample or {}
        net = s.get("net") or {}
        hw = s.get("hardware") or {}
        lat = s.get("latency") or {}
        active, spare_wired = self._nics(s)

        self.hist.append((s.get("ts"), lat.get("gateway"), lat.get("public"),
                          net.get("down_mbps"), net.get("up_mbps"), hw.get("cpu_pct")))
        st = self._stats()
        # 有探测线程的权威统计就用它：分母是"真正发出去的探测"，且区分超时与失败
        if probe_stats:
            st = self._stats_from_probes(probe_stats, st)
        st.setdefault("target", lat.get("target"))
        st.setdefault("timeout_ms", lat.get("timeout_ms"))
        st.setdefault("source", "sample")

        items = []

        def add(level, rule_key, metric=None, **kw):
            """文案在 i18n_rules 里，这里只关心「什么条件、扣多少分」"""
            txt = i18n_rules.render(rule_key, self.lang, **kw)
            items.append({
                "level": level, "cat": txt["cat"], "title": txt["title"],
                "detail": txt["detail"], "advice": txt["advice"], "metric": metric,
            })

        link_mbps = (active or {}).get("link_speed_mbps") or 0
        is_wifi = bool((active or {}).get("is_wireless")) or wifi is not None
        down = net.get("down_mbps") or 0
        up = net.get("up_mbps") or 0
        cpu = hw.get("cpu_pct") or 0
        per_core = hw.get("cpu_per_core") or []
        freq = hw.get("freq") or {}
        mem_pct = hw.get("mem_pct") or 0

        # =========================================================== A. 链路媒介
        # A1 有线口空置（这台机器的最大问题）
        if is_wifi and spare_wired:
            eth = spare_wired[0]
            eth_speed = eth.get("nominal_speed_mbps") or 0
            ratio = round(eth_speed / link_mbps, 1) if link_mbps else None
            add("warn", "wired_idle",
                metric=f"{link_mbps:.0f}→{eth_speed:.0f} Mbps",
                active_desc=active.get("desc"),
                link=link_mbps,
                radio=self._radio_note(wifi),
                eth_desc=eth.get("desc"),
                eth_speed=eth_speed,
                eth_status=eth.get("status"),
                ratio=self._ratio_note(ratio))

        # A2 2.4GHz 频段
        if wifi and wifi.get("band") and "2.4" in str(wifi.get("band")):
            add("warn", "band_24",
                metric="2.4 GHz",
                radio=wifi.get("radio"), band=wifi.get("band"),
                channel=wifi.get("channel"))

        # A3 信号强度（USB 网卡天线小，对位置极敏感）
        sig = (wifi or {}).get("signal_pct")
        if sig is not None:
            if sig < 35:
                add("critical", "sig_weak", metric=f"{sig:.0f}%", sig=sig)
            elif sig < 55:
                add("warn", "sig_low", metric=f"{sig:.0f}%", sig=sig)

        # A4 USB 无线网卡的固有短板
        desc = ((active or {}).get("desc") or "").lower()
        if is_wifi and "usb" in desc:
            add("info", "usb_wifi")

        # A5 有线链路降速协商
        if not is_wifi and link_mbps:
            if link_mbps <= 100:
                add("warn", "wired_100", metric=f"{link_mbps:.0f} Mbps", link=link_mbps)

        # =========================================================== B. 错误与丢弃
        err_d = (net.get("err_in_delta") or 0) + (net.get("err_out_delta") or 0)
        drop_d = (net.get("drop_in_delta") or 0) + (net.get("drop_out_delta") or 0)
        if err_d > 0:
            add("critical", "nic_err", metric=f"+{err_d}",
                err_d=err_d,
                err_in=net.get("err_in_total", 0),
                err_out=net.get("err_out_total", 0))
        if drop_d > 0:
            add("warn", "nic_drop", metric=f"+{drop_d}", drop_d=drop_d)

        # =========================================================== C. 吞吐 vs 链路能力
        if link_mbps and down > 0:
            util = down / link_mbps * 100
            if util > 75:
                add("warn", "link_saturated", metric=f"{util:.0f}%",
                    down=down, link=link_mbps, util=util)
            elif util < 3 and st.get("pub_avg") and st["pub_avg"] > 100:
                add("info", "bw_idle_lat",
                    down=down, link=link_mbps, pub_avg=st["pub_avg"])

        # =========================================================== D. CPU / 协议栈
        if cpu >= 90:
            add("critical", "cpu_full", metric=f"{cpu:.0f}%", cpu=cpu)
        elif cpu >= 75:
            add("warn", "cpu_high", metric=f"{cpu:.0f}%", cpu=cpu)

        if per_core and max(per_core) >= 95 and cpu < 70:
            hot = per_core.index(max(per_core))
            add("info", "single_core", metric=f"core{hot}",
                hot=hot, core_max=max(per_core), cpu=cpu)

        cur_mhz, max_mhz = freq.get("current_mhz"), freq.get("max_mhz")
        if cur_mhz and max_mhz and max_mhz > 0 and cur_mhz < max_mhz * 0.6:
            add("info", "cpu_throttle", metric=f"{cur_mhz/max_mhz*100:.0f}%",
                cur=cur_mhz, max=max_mhz, pct=cur_mhz / max_mhz * 100)

        if mem_pct >= 90:
            add("warn", "mem_pressure", metric=f"{mem_pct:.0f}%",
                mem=mem_pct,
                used=hw.get("mem_used_gb"), total=hw.get("mem_total_gb"))

        plan = self.profile.get("power_plan")
        if plan and any(k in plan for k in ("节能", "平衡", "Power saver", "Balanced")):
            add("info", "power_plan", metric=plan, plan=plan)

        # =========================================================== E. 端到端质量
        gw_avg, pub_avg = st.get("gw_avg"), st.get("pub_avg")
        gw_loss, pub_loss = st.get("gw_loss_pct"), st.get("pub_loss_pct")
        target = st.get("target") or lat.get("target") or ("public target" if self._en() else "公网目标")
        timeout_ms = st.get("timeout_ms") or 4000
        n_probe = st.get("n") or 0
        pub_err = st.get("pub_error") or 0
        pub_att = st.get("pub_attempts") or 0

        # 探测本身失败（解析不到主机 / 无路由 / ICMP 被屏蔽）也要说出来，
        # 否则用户会以为"0% 丢包"就是链路干净
        if pub_att and pub_err >= max(3, pub_att * 0.5):
            add("warn", "probe_fail", metric=f"{pub_err}/{pub_att}",
                att=pub_att, err=pub_err,
                detail=st.get("pub_detail") or ("unknown reason" if self._en() else "未知原因"))
        elif gw_loss is not None and gw_loss > 0:
            add("critical", "gw_loss", metric=f"{gw_loss}%",
                n=n_probe, loss=gw_loss,
                to=st.get("gw_timeout"), att=st.get("gw_attempts"),
                timeout=int(timeout_ms))
        elif pub_loss is not None and pub_loss > 0:
            add("warn", "pub_loss", metric=f"{pub_loss}%",
                target=target, loss=pub_loss,
                to=st.get("pub_timeout"), att=st.get("pub_attempts"),
                timeout=int(timeout_ms))

        if gw_avg is not None and is_wifi and gw_avg > 6:
            add("warn", "gw_latency", metric=f"{gw_avg} ms", gw=gw_avg)

        if gw_avg and pub_avg and pub_avg - gw_avg > 45:
            add("info", "upstream_latency", metric=f"+{pub_avg - gw_avg:.0f} ms",
                gw=gw_avg, pub=pub_avg, up=pub_avg - gw_avg, target=target)

        jitter = st.get("jitter")
        if jitter is not None and jitter > 40:
            add("warn", "jitter", metric=f"{jitter} ms", jitter=jitter)

        dns_ms = lat.get("dns_ms")
        if dns_ms is not None and dns_ms > 120:
            add("warn", "dns_slow", metric=f"{dns_ms} ms", ms=dns_ms)

        # =========================================================== 无异常时的正向反馈
        if not any(i["level"] in ("critical", "warn") for i in items):
            add("ok", "all_ok")

        # =========================================================== 评分
        score = 100
        for i in items:
            if i["level"] == "critical":
                score -= 18
            elif i["level"] == "warn":
                score -= 8
        # 质量指标额外扣分（比"配置不够好"更影响实际体验）
        if pub_loss:
            score -= min(pub_loss * 4, 20)
        if jitter and jitter > 40:
            score -= min((jitter - 40) / 4, 12)
        if pub_avg:
            score -= min(max(pub_avg - 30, 0) / 6, 15)
        score = int(max(0, min(100, round(score))))

        grade = i18n_rules.grade(score, self.lang)

        items.sort(key=lambda i: _LEVEL_ORDER.get(i["level"], 9))
        return {
            "score": score,
            "grade": grade,
            "items": items,
            "stats": st,
            "summary": self._summary_text(score, items, st, is_wifi, spare_wired),
        }

    # ------------------------------------------------------------ 一句话结论
    def _summary_text(self, score, items, st, is_wifi, spare_wired):
        crit = [i for i in items if i["level"] == "critical"]
        warn = [i for i in items if i["level"] == "warn"]
        if crit:
            return i18n_rules.summary("crit", self.lang,
                                      n=len(crit), head=crit[0]["title"])
        if warn:
            if is_wifi and spare_wired:
                return i18n_rules.summary("warn_wired", self.lang, score=score,
                                          nic=spare_wired[0].get("name"), n=len(warn))
            return i18n_rules.summary("warn", self.lang, score=score,
                                      head=warn[0]["title"], n=len(warn))
        return i18n_rules.summary("ok", self.lang, score=score)
