# 构建号台账

**规则：号只增不减，不要试图判断这次烧没烧。** 每次投递前查一次 ASC 的
TestFlight/Builds 页确认下一个号没被占用；撞号就直接跳，内容不用重做。

烧号规律（实测，v2.0 的「投递失败不烧号」是不完整的）：

| 情形 | 烧号 |
|---|---|
| 处理失败 | 烧 |
| 投递被拒 ITMS-90889（缺描述文件） | 不烧 |
| 投递被拒 ITMS-91109（quarantine） | 不烧 |
| **投递被拒 90886（缺 identifier）** | **烧** |
| 处理通过后在 ASC 内失效 | 烧 |

## 台账

| 日期 | App | 平台 | 号 | 结果 | 备注 |
|------|-----|------|----|------|------|
| 2026-08-25 | Passthrough | macOS | 8 | 提交后 GL 5.6 拒 | VIDEOCONVERT_FFMPEG_DIR |
| 2026-08-25 | Passthrough | iOS | 8 | 提交后 GL 5.6 拒 | 连坐（iOS 侧二进制本身干净） |
| 2026-08-27 | PlotOne | macOS | 6 | 在审时撤回 | 含 QAHooks |
| 2026-08-27 | PlotOne | iOS | 5 | 在审时撤回 | 含 QAHooks |
| 2026-08-28 | PlotOne | macOS | 7 | 投递拒 90886 | **号已烧** |
| 2026-08-28 | PlotOne | macOS | 8 | 待投递 | identifier 已并入 |
| 2026-08-28 | PlotOne | iOS | 6 | 已投递 | |
| 2026-08-28 | Passthrough | macOS | 9 | 待投递 | 三处已清 |
| 2026-08-28 | Passthrough | iOS | 9 | 待投递 | |
