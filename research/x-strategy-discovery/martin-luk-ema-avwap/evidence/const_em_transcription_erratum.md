# MLUK-EMA-AVWAP — `const em` 转录语法勘误（仅新增证据）

**范围：** 仅核对 `original_js_execution_transcript.md` 的 `const em` 行。未执行 JavaScript/Python、未获取任何行情、未修改或替换历史策略、配置、原转录及结果。

## 1. 可核对的历史会话文本

本会话中较早的**实际 JS 回测工具调用消息**仍有可见文本。其 `const em` 行显示为：

```javascript
 const em= Math.min(...q.low.slice(i-5,i+1))<=1.005*q21[i-1]&&q.close[i]>q21[i];
```

**来源限制：** 以上是当前会话可见的既往工具调用消息文本，而非当时封存、带校验和的运行时源文件或执行日志。能够对照会话文本，不等于已对实际执行字节做独立认证。

## 2. GitHub 转录与差异

文件：`research/x-strategy-discovery/martin-luk-ema-avwap/evidence/original_js_execution_transcript.md`，**第35行**（当前原转录文件保持不变）。

**最初发布版**，commit `4ed93cbf261686745bdfbf9dbc5ddf190fa8272f`：

```javascript
 const em= Math.min(...q.low.slice(i-5,i+1])<=1.005*q21[i-1]&&q.close[i]>q21[i];
```

最初版的 `i+1]` 并非可核对的会话调用文本，括号类型错误，也未闭合 `Math.min(`。

**现存转录版**，自 commit `17963d69522b4e73a9afb75b15947d32186caf1f` 起，在原先转录中将 `]` 改为 `)`，但仍缺少闭合 `Math.min(` 所需的第二个 `)`：

```javascript
 const em= Math.min(...q.low.slice(i-5,i+1)<=1.005*q21[i-1]&&q.close[i]>q21[i];
```

对照会话工具调用文本 `...slice(i-5,i+1))<=...`，现存转录为 `...slice(i-5,i+1)<=...`：**少了一个 `)`**。

## 3. 认证结论与不可推断事项

- **确认：** 当前 GitHub 转录第35行存在语法缺陷；与本会话可见历史工具调用文本不一致。最初版本另有 `]` 字符误转录。
- **不确认：** 未保存可验证的原始运行时源码快照/哈希或完整执行跟踪；因此即使会话调用文本可见，**历史实际执行源码无法进行字节级认证**。
- 本勘误仅保留文本差异的证据，**没有修复原转录**，更不声称将任何修正后的源码认证为原始执行版本。
- 原研究状态不变：`HOLD / NOT_REPRODUCED`；原始回测结果及交易账本不变。

## 4. 静态证据锚点

- [现存原转录第35行](https://github.com/xmyyj001/ib-trading/blob/1db49e510c1fddb34d66c331866c527ffff00d25/research/x-strategy-discovery/martin-luk-ema-avwap/evidence/original_js_execution_transcript.md#L35)
- [最初发布版第35行](https://github.com/xmyyj001/ib-trading/blob/4ed93cbf261686745bdfbf9dbc5ddf190fa8272f/research/x-strategy-discovery/martin-luk-ema-avwap/evidence/original_js_execution_transcript.md#L35)
- [文本转录修改提交](https://github.com/xmyyj001/ib-trading/commit/17963d69522b4e73a9afb75b15947d32186caf1f)

**本文件是新增勘误，不覆盖历史原转录。**
