# 缠论分析站点（chanlun-analysis）

> 纯前端缠论技术分析站点 · GitHub Pages 自动部署 · 无后端、无构建依赖
>
> 在线地址：**https://zjrongvip.github.io/chanlun-analysis/**

---

## 一、页面地图

| 路径 | 页面 | 定位 | 内核 |
|---|---|---|---|
| `/` | **走势分析台 v3** | 单票全周期主分析台：分型→笔→中枢→走势段，一买/二买/三买 + 背驰量化 | `chan-core` + `chan-ext` |
| `/yimai/` | 缠论一买选股 | 单票一买即时判定（九道闸门），七周期 | `chan-core` |
| `/multi/` | 多级别中枢分析 | 日 / 周 / 月三级别同屏，看级别间共振 | `chan-core` + `chan-ext` |
| `/scan/` | 批量扫一买 | 自选股批量扫描，命中高亮 + CSV 导出 | `chan-core` + `chan-ext` |
| `/sector/` | 板块轮动选股 | 缠论第 106 课均线系统，板块强弱分级 | 独立（已换腾讯源） |
| `/legacy/` | 旧版对照 | v3 之前的旧算法，保留用于新旧口径对照 | 独立（已换腾讯源） |

六页顶部导航互通，当前页高亮；全站统一「一买」浅色卡片风格。

---

## 二、算法口径

### 核心计算链（严格按缠论课程顺序）

```
1 分型  →  2 笔  →  3 中枢  →  4 走势类型  →  5 背驰  →  6 买卖点
```

| 环节 | 实现依据 |
|---|---|
| K 线包含处理 | 标准合并（取高低点极值方向） |
| 分型 | 顶/底分型识别 + 分型序列筛选 |
| 笔 | 69 课画笔规则 + 12/14/15 号笔过滤 |
| 线段 | 67 / 71 课特征序列法 |
| 中枢 | 课 18「连续三笔重叠区间」ZD ~ ZG，**非**分位数箱体 |
| 一买 | 15 号脚本九道闸门（下跌 + 盘整 + 下跌走完） |
| 二买 | 一买/前低之后回抽不破前低，且已确认 |
| 三买 | 向上突破中枢 ZG 后，回抽不跌回中枢 |
| 背驰 | 同向相邻两笔 MACD 柱力度衰减，且创极端价 |

> 一买算法已与 Python 原脚本（12/14/15 号）做 **5120 样本逐样本对拍，零差异**；
> 周/月聚合另做过偏差校验（排除窗口首端半期后零偏差）。

### 买卖点标记

| 标记 | 颜色 | 形状 |
|---|---|---|
| 一买 | 蓝 `#1c7ed6` | ▲ |
| 二买 | 绿 `#2f9e44` | ▲ |
| 三买 | 青 `#0b7285` | ▲ |
| 一卖 | 红 `#d64545` | ▼ |
| 二卖 | 橙 `#e8590c` | ▼ |

配色遵循**中国习惯：红涨绿跌**。

---

## 三、数据源

纯前端页面，受浏览器同源策略约束：

| 用途 | 接口 | 说明 |
|---|---|---|
| 日 / 周 / 月 K 线 | 腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | ✅ 带 `ACAO: *`，前复权，公网可用 |
| 分时（5/15/30/60 分） | 新浪 `money.finance.sina.com.cn/.../jsonp.php` | ✅ JSONP 免跨域（疑似不复权） |
| 兜底 | 东财 `push2his.eastmoney.com` | ⚠️ 已被部分 IP 限流，仅作最后兜底 |

**铁律**：公网纯前端页只能用带 `Access-Control-Allow-Origin` 的接口或 JSONP。
东财 `push2his` 已被本机 IP 限流；新浪 `json_v2.php` 无 CORS 头，公网必挂。

窗口长度：日 800 自然日 / 周 240 根 / 月 180 根 / 分时 480 根；**未走完的当前周期 K 线保留并参与计算**（v4.9 起）。

> **为什么保留（2026-09-22 修订）**：原规则是「未走完的当前周期 K 线一律丢弃」，本意是避免"半根周线"参与笔与中枢，
> 但代价是 **看不见当下** —— 9-22 打开周线却停在上周五 9-18，本周整根消失。缠论判的就是当下，
> 未走完的 K 线正是当下的载体；而笔的成立本来就要求**分型已确认**，未确认的部分不会被当成完成的笔，
> 无需在数据层提前砍掉。现改为原样保留，页面对进行中的末根标注「本周 / 本月进行中」（`lastBarLive()`，仅标注不截断）。
> ⚠️ 加这条前请确认：`multi` 页（日/周/月同屏）**从来就没有这条丢弃规则**，两处口径曾长期不一致。

---

## 四、开发工作流

### 内核唯一来源原则

算法内核（`chan-core`、`chan-ext`）**只在 `index.html` 里维护**，其余页面通过构建脚本注入，杜绝复制粘贴漂移。

```
C:\Users\Lenovo\WorkBuddy\Claw\
├── chanlun-yimai\一买选股.html      # 一买工具源文件（本地单文件版）
├── chanlun-analysis\
│   ├── index.html                   # ★ 内核唯一维护点（走势分析台 v3）
│   ├── yimai\index.html             # 站点一买页（手工同步导航/favicon）
│   ├── multi\index.html             # ⚙ 构建产物 —— 勿手改
│   ├── scan\index.html              # ⚙ 构建产物 —— 勿手改
│   ├── sector\index.html            # 板块轮动（独立页）
│   └── legacy\index.html            # 旧版对照（独立页）
└── _build_site\
    ├── build.py                     # 抽内核 → 注入模板 → 生成 multi/scan
    ├── update_nav.py                # 六页导航一键统一
    ├── patch_favicon.py             # 注入内联 SVG favicon（幂等）
    ├── multi.template.html          # 多级别页模板
    └── scan.template.html           # 批量扫描页模板
```

### 改代码后的标准动作

```bash
cd /c/Users/Lenovo/WorkBuddy/Claw

# 1. 改模板（不是改生成的 index.html）
# 2. 重新构建 + 统一导航 + 补 favicon
python _build_site/build.py
python _build_site/update_nav.py
python _build_site/patch_favicon.py

# 3. 语法校验（六页全过）
python _verify_yimai/syntax_check.py <file>

# 4. 内核哈希校验（chan-core 5 页全同 / chan-ext 3 页全同）
```

### 自检清单（发布前必跑）

- [ ] 六页 JS 语法校验 `ALL OK`
- [ ] `chan-core` 五页哈希一致、`chan-ext` 三页哈希一致
- [ ] 六页导航各 6 项、当前页高亮正确
- [ ] 本地 `file://` 渲染无报错
- [ ] 线上 URL 用 Edge 干净 profile 实渲染复核（**不能用带缓存的 profile**）

---

## 五、发布流程（GCM 免 token 通道）

本机有系统 Git + Git Credential Manager，**不需要 PAT**。

```bash
cd /c/Users/Lenovo/WorkBuddy/Claw/chanlun-analysis
git add <改动文件>
git -c user.name=zjrongvip -c user.email=zjrongvip@users.noreply.github.com commit -m "..."
"C:/Program Files/Git/cmd/git.exe" -c http.proxy= -c https.proxy= push origin main:main
```

要点：
- **必须脱沙箱**（`dangerouslyDisableSandbox`），否则沙箱代理会拦（`CONNECT tunnel failed 502`）
- **必须清代理**（`-c http.proxy= -c https.proxy=`）
- 不要在 URL 里内联 token —— 那会绕过 credential helper 退化为裸 token，导致 403

---

## 六、免责声明

- 行情接口为**非官方接口，无 SLA**，可能按 IP 限流或变更
- 任一级别的一个买点 **≠ 交易指令**，小级别信号须结合实时价与更大级别结构确认
- 本站仅作技术分析辅助工具，不构成任何投资建议
