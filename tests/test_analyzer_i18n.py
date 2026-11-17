#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_analyzer_i18n.py —— 分析引擎文案的中英文校验

为什么必须测这个：
  analyzer 的文案模板用 .format(**kw) 填坑。模板里写错一个变量名，
  运行时就是 KeyError，而 analyze() 跑在采集线程的 try 里——异常被吞掉，
  结果是「那条规则从此静默消失」，界面上什么都看不出来。这类 bug 靠肉眼
  看 20 条规则几乎不可能发现，只能靠测试把每条规则都过一遍。

跑法：build/venv/Scripts/python.exe tests/test_analyzer_i18n.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import i18n_rules            # noqa: E402
import analyzer              # noqa: E402

CJK = re.compile(r'[\u4e00-\u9fff]')
HERE = os.path.dirname(os.path.abspath(__file__))

# 每条规则一组假参数，尽量用英文/数字，这样英文输出里出现中文就能立刻定位是漏翻
CASES = {
    "wired_idle": dict(active_desc="Realtek 8812CU USB NIC", link=150,
                       radio=" (802.11n / 2.4GHz / channel 6)",
                       eth_desc="Realtek PCIe GbE Family Controller", eth_speed=1000,
                       eth_status="Disconnected", ratio=" (~6.7x)"),
    "band_24": dict(radio="802.11n", band="2.4GHz", channel=6),
    "sig_weak": dict(sig=28),
    "sig_low": dict(sig=45),
    "usb_wifi": {},
    "wired_100": dict(link=100),
    "nic_err": dict(err_d=3, err_in=12, err_out=4),
    "nic_drop": dict(drop_d=2),
    "link_saturated": dict(down=120.0, link=150, util=80.0),
    "bw_idle_lat": dict(down=1.2, link=1000, pub_avg=180),
    "cpu_full": dict(cpu=95),
    "cpu_high": dict(cpu=80),
    "single_core": dict(hot=3, core_max=99, cpu=35),
    "cpu_throttle": dict(cur=2200, max=4600, pct=48),
    "mem_pressure": dict(mem=93, used=45, total=48),
    "power_plan": dict(plan="Balanced"),
    "probe_fail": dict(att=20, err=12, detail="no route to host"),
    "gw_loss": dict(n=50, loss=6.0, to=3, att=50, timeout=4000),
    "pub_loss": dict(target="223.5.5.5", loss=4.0, to=2, att=50, timeout=4000),
    "gw_latency": dict(gw=12.5),
    "upstream_latency": dict(gw=3, pub=120.0, up=117.0, target="223.5.5.5"),
    "jitter": dict(jitter=60),
    "dns_slow": dict(ms=200),
    "all_ok": {},
}

SUMMARY_CASES = {
    "crit": dict(n=2, head="CPU overloaded"),
    "warn_wired": dict(score=62, nic="Ethernet", n=3),
    "warn": dict(score=70, head="Wi-Fi signal weak", n=2),
    "ok": dict(score=95),
}


def main():
    bad = 0

    # 1) 每条规则的每个语言都要能渲染，英文里不能有中文
    for key, kw in sorted(CASES.items()):
        for lang in ("zh", "en"):
            try:
                txt = i18n_rules.render(key, lang, **kw)
            except Exception as e:
                print("  [FAIL] %-16s %s 渲染失败: %s: %s"
                      % (key, lang, type(e).__name__, e))
                bad += 1
                continue
            for field in ("title", "detail", "cat"):
                if not txt[field].strip():
                    print("  [FAIL] %-16s %s 的 %s 为空" % (key, lang, field))
                    bad += 1
            if lang == "en":
                for field in ("title", "detail", "advice", "cat"):
                    if CJK.search(txt[field]):
                        print("  [FAIL] %-16s en.%s 里还有中文: %s"
                              % (key, field, txt[field][:60]))
                        bad += 1
        print("  [OK]   %s" % key)

    # 2) 规则表里不能有漏测的新规则
    untouched = [k for k in i18n_rules.RULES if k not in CASES]
    if untouched:
        print("  [FAIL] 这些规则没有测试用例（模板可能有拼写错误）: %s"
              % ", ".join(untouched))
        bad += 1

    # 3) 小结与等级
    for key, kw in SUMMARY_CASES.items():
        for lang in ("zh", "en"):
            try:
                s = i18n_rules.summary(key, lang, **kw)
            except Exception as e:
                print("  [FAIL] summary.%s %s 失败: %s" % (key, lang, e))
                bad += 1
                continue
            if not s.strip():
                print("  [FAIL] summary.%s %s 为空" % (key, lang))
                bad += 1
            if lang == "en" and CJK.search(s):
                print("  [FAIL] summary.%s en 里还有中文: %s" % (key, s[:60]))
                bad += 1
    for score, zh, en in ((95, "优秀", "Excellent"), (75, "良好", "Good"),
                          (55, "一般", "Fair"), (20, "较差", "Poor")):
        if i18n_rules.grade(score, "zh") != zh or i18n_rules.grade(score, "en") != en:
            print("  [FAIL] grade(%d) 期望 %s/%s，实际 %s/%s"
                  % (score, zh, en, i18n_rules.grade(score, "zh"),
                     i18n_rules.grade(score, "en")))
            bad += 1
    print("  [OK]   summary + grade")

    # 4) 真实快照走完整 analyze：两种语言都不能抛异常，英文不能残留中文
    fx_path = os.path.join(HERE, "fixture_snapshot.json")
    if os.path.isfile(fx_path):
        fx = json.load(open(fx_path, encoding="utf-8"))
        latest = fx["latest"]
        profile = fx.get("profile") or {}
        for lang in ("zh", "en"):
            a = analyzer.Analyzer(profile, lang=lang)
            try:
                r = a.analyze(latest, latest.get("wifi"),
                              probe_stats=(latest.get("analysis") or {}).get("stats"))
            except Exception as e:
                print("  [FAIL] 真实快照 analyze(%s) 抛错: %s: %s" % (lang, type(e).__name__, e))
                bad += 1
                continue
            if lang == "en":
                # title 完全来自模板，含中文就是漏翻；
                # detail/advice/summary 会被塞进网卡名、探测目标这类真实数据，
                # 中文 Windows 上设备名本身就是中文，不能算漏翻
                for it in r["items"]:
                    if CJK.search(it["title"] or ""):
                        print("  [FAIL] 真实快照英文标题含中文: %s" % it["title"][:60])
                        bad += 1
                if not r["items"]:
                    print("  [FAIL] 真实快照没产出任何结论")
                    bad += 1
            print("  [OK]   真实快照 %s（%d 条结论，得分 %d）"
                  % (lang, len(r["items"]), r["score"]))
    else:
        print("  [SKIP] 没有 fixture_snapshot.json")

    print("\n%s" % ("全部通过" if not bad else "%d 处失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
