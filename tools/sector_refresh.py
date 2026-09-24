#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sector_refresh.py - 板块轮动页数据刷新器（仓库权威版，本地与 GitHub Actions 共用）
- 从 sector/index.html 解析 10 板块 × 10 股的股票池
- 腾讯 fqkline 拉日K（前复权） -> 按页面口径的 8 条斐波那契均线复算 9 级分类
- 个股层级 L = 站上均线条数 + 1 (1~9)
- 板块强弱指标 = 成分股近 5 个交易日平均层级；prevStrength = 前 5 个交易日同口径
- 回写：SECTORS 数据块 + 头部日期 + 近期热点 + 轮动时间线
用法：python tools/sector_refresh.py [--dry]
（本地旧版 scripts/sector_refresh.py 已由本文件取代）
"""
import urllib.request
import json
import time
import os
import re
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根
PAGE = os.path.join(BASE, 'sector', 'index.html')
CACHE = os.path.join(BASE, 'data', 'sector_kline_cache.json')
RESULT = os.path.join(BASE, 'data', 'sector_refresh_result.json')

MA_PERIODS = [5, 13, 21, 34, 55, 89, 144, 233]
KLINE_BARS = 800          # 覆盖 MA233 且留足冗余
DELAY = 0.12
PREV_OFFSET = 5           # “上周”= 5 个交易日前


def prefix(code):
    if code[0] == '6':
        return 'sh'
    if code[0] in '03':
        return 'sz'
    if code[0] in '48':
        return 'bj'
    return 'sh'


def fetch_kline(code):
    p = prefix(code)
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'
           'param=%s%s,day,,,%d,qfq' % (p, code, KLINE_BARS))
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://gu.qq.com/'})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode('utf-8'))
    node = d['data']['%s%s' % (p, code)]
    k = node.get('qfqday') or node.get('day') or []
    return [{'d': x[0], 'c': float(x[2])} for x in k]


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def level_series(bars):
    """返回 [(date, L)]。口径与页面 calcLevel() 完全一致：
    L = 1，逐个检查 MA5..MA233，若收盘 > 该均线则 L = 该均线序号+2；最后 clamp 到 9。
    （即“突破到的最高均线等级”，非“站上条数”）"""
    closes = [b['c'] for b in bars]
    dates = [b['d'] for b in bars]
    n = len(closes)
    pre = [0.0] * (n + 1)
    for i, c in enumerate(closes):
        pre[i + 1] = pre[i] + c
    out = []
    for t in range(n):
        lvl = 1
        for i, p in enumerate(MA_PERIODS):
            if t + 1 >= p:
                ma = (pre[t + 1] - pre[t + 1 - p]) / p
                if closes[t] > ma:
                    lvl = i + 2
        if t + 1 >= MA_PERIODS[-1]:      # MA233 可用才计入
            out.append((dates[t], min(lvl, 9)))
    return out


def parse_sectors(html):
    i = html.find('const SECTORS = [')
    j = html.find('\n];', i)
    body = html[i:j]
    sectors = []
    cur = None
    for ln in body.split('\n'):
        m = re.search(r"name:'([^']+)',code:'([^']+)',strength:[\d.]+,prevStrength:[\d.]+,\s*trend:'\w+',desc:'([^']*)'", ln)
        if m:
            cur = {'name': m.group(1), 'code': m.group(2), 'desc': m.group(3), 'stocks': []}
            sectors.append(cur)
            continue
        m2 = re.search(r"\{name:'([^']+)',code:'(\d+)',level:\d+\}", ln)
        if m2 and cur is not None:
            cur['stocks'].append({'name': m2.group(1), 'code': m2.group(2)})
    return sectors, i, j


def classify(strength, trend):
    """板块等级/建议（沿用原页阈值）"""
    if strength >= 5.8:
        return 'strong', ('强烈推荐' if strength >= 6.3 else '推荐')
    if strength >= 4.0:
        return 'neutral', ('可选' if trend == 'up' else '观察')
    return 'weak', '规避'


def main():
    dry = '--dry' in sys.argv
    html = open(PAGE, encoding='utf-8').read()
    sectors, bi, bj = parse_sectors(html)
    total = sum(len(s['stocks']) for s in sectors)
    print('解析: %d 板块 / %d 只个股' % (len(sectors), total))
    if len(sectors) == 0 or total == 0:
        print('!! 股票池解析为空，页面标记可能被破坏，拒绝刷新')
        sys.exit(2)

    cache = load_cache()
    codes = [st['code'] for s in sectors for st in s['stocks']]
    series = {}   # code -> [(date,L)]
    miss = []
    for idx, code in enumerate(codes):
        bars = cache.get(code)
        if not bars:
            try:
                bars = fetch_kline(code)
                cache[code] = bars
                time.sleep(DELAY)
            except Exception as e:
                print('  [%3d/%d] %s 取数失败: %s' % (idx + 1, len(codes), code, e))
                miss.append(code)
                continue
        ser = level_series(bars)
        if ser:
            series[code] = ser
        else:
            miss.append(code)
        if (idx + 1) % 20 == 0:
            print('  [%3d/%d] 已算层级...' % (idx + 1, len(codes)))

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

    # 取全体共同的最后交易日
    last_dates = sorted({s[-1][0] for s in series.values()})
    last = last_dates[-1]
    print('最新交易日:', last, '| 缺数据:', miss)

    def L_at(code, date):
        for d, l in series[code]:
            if d == date:
                return l
        return None

    # 逐板块汇总：strength = 近5个交易日平均层级；prevStrength = 前5个交易日平均层级
    result = []
    all_dates = sorted({d for s in series.values() for d, _ in s})
    W = PREV_OFFSET
    win_now, win_prev = all_dates[-W:], all_dates[-2 * W:-W]

    def sector_series(stocks):
        """返回 {date: 该板块当日平均层级}"""
        per = {}
        for st in stocks:
            for d, l in series.get(st['code'], []):
                per.setdefault(d, []).append(l)
        return {d: sum(v) / len(v) for d, v in per.items()}

    sec_series = {s['name']: sector_series(s['stocks']) for s in sectors}

    def week_metric(name, end_pos):
        wd = all_dates[max(0, end_pos - W + 1):end_pos + 1]
        ss = sec_series[name]
        vals = [ss[d] for d in wd if d in ss]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    for s in sectors:
        strength = week_metric(s['name'], len(all_dates) - 1)
        prev = week_metric(s['name'], len(all_dates) - 1 - W)
        diff = round(strength - prev, 1)
        trend = 'up' if diff > 0.1 else ('down' if diff < -0.1 else 'flat')
        level, rec = classify(strength, trend)
        result.append({'name': s['name'], 'code': s['code'], 'desc': s['desc'],
                       'strength': strength, 'prev': prev, 'trend': trend,
                       'level': level, 'rec': rec,
                       'stocks': [{'name': st['name'], 'code': st['code'],
                                   'level': (L_at(st['code'], last) or 1)}
                                  for st in s['stocks']]})
    result.sort(key=lambda x: -x['strength'])

    # ---- 生成 SECTORS 块 ----
    lines = ['const SECTORS = [']
    for r in result:
        lines.append('  {')
        lines.append("    name:'%s',code:'%s',strength:%s,prevStrength:%s,trend:'%s',desc:'%s',"
                     % (r['name'], r['code'], r['strength'], r['prev'], r['trend'], r['desc']))
        lines.append("    level:'%s',rec:'%s'," % (r['level'], r['rec']))
        lines.append('    stocks:[')
        for st in r['stocks']:
            lines.append("      {name:'%s',code:'%s',level:%d}," % (st['name'], st['code'], st['level']))
        lines.append('    ]')
        lines.append('  },')
    lines.append(']')
    new_block = '\n'.join(lines)

    # ---- 时间线（近4周，同口径周均值）----
    tl = []
    for k in range(3, -1, -1):
        pos = len(all_dates) - 1 - k * W
        if pos < 0:
            continue
        dt = all_dates[pos]
        stats = [(s['name'], week_metric(s['name'], pos)) for s in sectors]
        stats.sort(key=lambda x: -x[1])
        top = stats[:3]
        tail = '；'.join('%s(%s)' % (n, v) for n, v in stats[3:5])
        title = '领跑：%s' % ' · '.join('%s(%s)' % (n, v) for n, v in top)
        tl.append({'date': dt, 'title': title,
                   'desc': '周度强弱指标排序，前三为 %s；其后 %s。' % (top[0][0] if top else '-', tail)})

    # ---- 热点标签 ----
    hot = []
    for r in result[:3]:
        arrow = {'up': '↗', 'down': '↘', 'flat': '→'}[r['trend']]
        hot.append('<div class="hot-tag up">🔥 %s %s%s</div>' % (r['name'], arrow, r['strength']))
    for r in result[-2:]:
        hot.append('<div class="hot-tag down">❄ %s ↓%s</div>' % (r['name'], r['strength']))

    month = last[:7] + '月'
    print('\n===== 预览：板块强弱（新口径）=====')
    for r in result:
        print('  %-12s 强度%5.1f (上期%5.1f %+4.1f) %-5s %-8s %s' % (
            r['name'], r['strength'], r['prev'], r['strength'] - r['prev'],
            r['trend'], r['level'], r['rec']))
    print('\n===== 预览：轮动时间线 =====')
    for t in tl:
        print('  %s  %s' % (t['date'], t['title']))

    if dry:
        print('\n[dry-run] 未写入文件')
        return

    # ---- 回写页面 ----
    new_html = html[:bi] + new_block + html[bj + 2:]  # 去掉原 '\n];'
    # 头部日期（兼容 <b> 包裹与裸日期两种写法）
    new_html, n1 = re.subn(r'(📅 最新更新：<b>)[\d-]+(</b>)', r'\g<1>%s\g<2>' % last, new_html)
    if n1 == 0:
        new_html = re.sub(r'📅 最新更新：[\d-]+', '📅 最新更新：%s' % last, new_html)
    # 热点标题月份
    new_html = re.sub(r'🔥 近期市场热点（[^）]*）', '🔥 近期市场热点（%s）' % month, new_html)
    # 热点标签体
    new_html = re.sub(r'(<div class="hotbar">)\s*(?:<div class="hot-tag[^>]*>[^<]*</div>\s*)+(</div>)',
                      lambda m: m.group(1) + '\n      ' + '\n      '.join(hot) + '\n    ' + m.group(2),
                      new_html, count=1)
    # 时间线
    tl_js = 'const TIMELINE = [\n' + '\n'.join(
        "  {date:'%s',title:'%s',desc:'%s'}," % (t['date'], t['title'], t['desc']) for t in tl) + '\n];'
    new_html = re.sub(r'const TIMELINE = \[.*?\n\];', tl_js, new_html, count=1, flags=re.S)

    open(PAGE, 'w', encoding='utf-8').write(new_html)
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    with open(RESULT, 'w', encoding='utf-8') as f:
        json.dump({'run_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'latest_date': last, 'prev_window': [win_prev[0], win_prev[-1]],
                   'sectors': result}, f, ensure_ascii=False, indent=2)
    print('\n已写入: %s' % PAGE)
    print('结果存档: %s' % RESULT)


if __name__ == '__main__':
    main()
