---
name: craft-knowledge-02
description: Python编码规范 — 评分引擎/回测引擎/MCP Server编码约定、numpy/pandas规范、Type Hints、日志配置、与PowerShell的接口
metadata:
  type: knowledge
  role: Craft
  version: v1.0
  created: 2026-05-23
  knowledge_id: "02"
  title: Python编码规范
  dependencies: []
  estimated_tokens_saved: 15000
---

# 02 — Python编码规范

> Craft知识库 | 编号：02 | 版本：v1.0 | 2026-05-23
> 关联角色：`.claude/agents/代码工匠-Craft.md` §3.2

---

## 一、项目Python文件清单与职责

| 文件 | 职责 | 核心依赖 | 入口方式 |
|:-----|:-----|:---------|:---------|
| `scoring_engine_v2.py` | 多因子评分引擎，接收股票数据JSON，输出评分结果JSON | numpy, pandas | `python scoring_engine_v2.py --input ... --output ...` |
| `backtest_engine.py` | 回测引擎，对历史数据进行策略模拟，输出绩效报告 | numpy, pandas | `python backtest_engine.py --config ...` |
| `financial_mcp_server.py` | MCP Server，提供外部系统查询接口 | mcp | 长期运行服务 |
| `md_to_docx.py` | MD→DOCX文档转换工具 | python-docx | `python md_to_docx.py input.md output.docx` |
| `generate_roster_xlsx.py` | 股票名单Excel生成工具 | openpyxl | `python generate_roster_xlsx.py --input ...` |

---

## 二、标准Python脚本模板

### 2.1 入口模式

```python
"""
模块名称

简短描述模块用途。

详细描述：
  - 输入格式
  - 处理逻辑
  - 输出格式
  - 退出码约定

用法:
    python module_name.py --input data.json --output result.json

退出码:
    0 — 正常完成
    1 — 数据源错误
    2 — 参数错误
    3 — 文件I/O错误
"""

import argparse
import logging
import sys
from pathlib import Path

# 模块级logger
logger = logging.getLogger(__name__)


def main(input_path: str, output_path: str, debug: bool = False) -> int:
    """主逻辑
    
    Args:
        input_path: 输入JSON文件路径
        output_path: 输出JSON文件路径
        debug: 调试模式
    
    Returns:
        退出码: 0=正常, 1=数据错误, 2=参数错误, 3=文件错误
    """
    # 业务逻辑
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="模块描述")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", required=True, help="输出JSON文件路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    # 日志配置
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        exit_code = main(args.input, args.output, args.debug)
    except Exception as e:
        logger.error(f"未捕获异常: {e}", exc_info=True)
        exit_code = 1
    finally:
        sys.exit(exit_code)
```

### 2.2 退出码约定

```python
# 所有脚本必须返回明确的退出码
EXIT_SUCCESS = 0          # 正常完成
EXIT_DATA_ERROR = 1       # 数据源错误（API失败、数据格式异常）
EXIT_PARAM_ERROR = 2      # 参数错误（缺少参数、参数值非法）
EXIT_FILE_ERROR = 3       # 文件I/O错误（文件不存在、无法读写）
EXIT_LOGIC_ERROR = 4      # 业务逻辑错误（数据不满足处理条件）
```

---

## 三、数值计算规范

### 3.1 pandas 使用约定

```python
import pandas as pd
import numpy as np

# ✅ 向量化操作 — 评分引擎核心模式
def calculate_factor_scores(df: pd.DataFrame) -> pd.Series:
    """对DataFrame中的每只股票计算因子得分"""
    # 不要逐行迭代！使用向量化操作
    scores = pd.Series(0.0, index=df.index)
    
    # 条件筛选 + 向量化赋值
    mask_positive = df["change_pct"] > 0
    scores[mask_positive] += df.loc[mask_positive, "change_pct"] * 0.5
    
    return scores

# ✅ 用 .loc[] 而非链式赋值（避免SettingWithCopyWarning）
df.loc[mask, "score"] = new_value

# ✅ 用 .apply() 处理复杂逻辑（但尽量向量化）
df["category"] = df["pe"].apply(lambda x: categorize_pe(x))
```

### 3.2 numpy 使用约定

```python
import numpy as np

# 因子标准化（Z-score）
factor_z = (factor - np.mean(factor)) / np.std(factor)

# 去极值（Winsorize — 1%/99%分位数截断）
lower = np.percentile(factor, 1)
upper = np.percentile(factor, 99)
factor_clipped = np.clip(factor, lower, upper)

# 缺失值填充（行业均值或0）
factor_filled = np.where(np.isnan(factor), fill_value, factor)
```

### 3.3 性能敏感操作

```python
# ❌ 慢 — 逐行迭代
for idx, row in df.iterrows():
    result[idx] = heavy_computation(row["a"], row["b"])

# ✅ 快 — 向量化
result = heavy_computation_vectorized(df["a"], df["b"])

# ✅  可接受 — apply（当向量化不可行时）
result = df.apply(lambda row: complex_logic(row), axis=1)
```

---

## 四、类型提示

### 4.1 函数签名

```python
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd

# ✅ 完整类型提示
def score_stocks(
    df: pd.DataFrame,
    weights: Dict[str, float],
    debug: bool = False,
) -> Tuple[pd.Series, Dict[str, float]]:
    """评分主函数"""
    ...

# ✅ 可选参数
def load_cache(cache_path: str, ttl_minutes: Optional[int] = None) -> Optional[pd.DataFrame]:
    """加载缓存，可能返回None"""
    ...

# ✅ 联合类型
def get_market_state() -> str:
    """返回市场状态: 'bull' | 'bear' | 'range'"""
    ...
```

### 4.2 类型提示规则

- 所有公开函数必须有Type Hints（参数+返回值）
- 私有函数（`_`前缀）可省略
- 复杂嵌套类型用 `typing` 模块：`Dict[str, List[float]]`
- Python 3.9+ 可用内置泛型：`dict[str, list[float]]`，但项目保守使用 `typing` 以保证兼容性
- DataFrame列名用字符串字面量文档化：注释 `# DataFrame必须包含列: code, close, pe`

---

## 五、异常处理

### 5.1 异常处理模式

```python
# ✅ 具体异常类型
try:
    data = json.loads(raw_text)
except json.JSONDecodeError as e:
    logger.error(f"JSON解析失败: 位置 {e.pos}, 行 {e.lineno}")
    return None
except UnicodeDecodeError as e:
    logger.error(f"编码错误: {e.encoding} → 尝试gbk")
    data = json.loads(raw_text.encode("gbk").decode("utf-8"))

# ✅ 文件I/O
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    logger.warning(f"文件不存在: {path}")
    data = None
except PermissionError:
    logger.error(f"文件无权限: {path}")
    raise

# ❌ 裸except — 禁止
try:
    risky_operation()
except:  # 这不OK
    pass
```

### 5.2 自定义异常类

```python
class DataSourceError(Exception):
    """数据源异常 — 主备API均失败"""
    def __init__(self, source: str, detail: str):
        self.source = source
        self.detail = detail
        super().__init__(f"[{source}] {detail}")

class CacheExpiredError(Exception):
    """缓存过期且无法刷新"""
    pass

class ValidationError(Exception):
    """数据校验失败"""
    pass
```

---

## 六、文件I/O

### 6.1 JSON读写

```python
import json

# ✅ 读 — 必须用 with + encoding
def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"JSON文件不存在: {path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {path} — {e}")
        return {}

# ✅ 写 — ensure_ascii=False 保留中文
def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
```

### 6.2 CSV读写（pandas）

```python
import pandas as pd

# ✅ 读 — 显式指定编码
df = pd.read_csv(path, encoding="utf-8")

# ✅ 写 — 不写行号索引
df.to_csv(path, index=False, encoding="utf-8")
```

### 6.3 路径处理

```python
from pathlib import Path

# ✅ 推荐 — pathlib
BASE_DIR = Path(__file__).parent
config_path = BASE_DIR / "config.json"
data_dir = BASE_DIR / ".." / "data"
data_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在

#  可接受 — os.path（旧代码兼容）
import os
config_path = os.path.join(os.path.dirname(__file__), "config.json")
```

---

## 七、日志配置

### 7.1 模块级日志

```python
import logging

# 每个模块顶部声明一次
logger = logging.getLogger(__name__)

# 使用
logger.info("评分引擎启动，输入: %s", input_path)
logger.warning("数据缺失: %d只股票缺少PE值，已排除", missing_count)
logger.error("评分计算失败: %s", e, exc_info=True)
logger.debug("因子权重: %s", weights)
```

### 7.2 日志级别使用规则

| 级别 | 何时使用 | 示例 |
|:-----|:---------|:-----|
| ERROR | 操作失败、数据丢失、需要人工介入 | API调用失败、文件写入错误 |
| WARNING | 异常但可继续、降级处理 | 缓存过期继续用、备源激活 |
| INFO | 关键步骤完成、处理数量统计 | "评分完成，共处理500只股票" |
| DEBUG | 详细调试信息、中间值 | 因子计算中间结果、API返回原文 |

### 7.3 RotatingFileHandler（长期运行服务）

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding="utf-8",
)
handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(handler)
```

---

## 八、配置管理

### 8.1 config.py 模式

```python
# config.py — 集中配置管理
import os
from pathlib import Path

# === 路径 ===
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"

# === API参数 ===
API_TIMEOUT = 10  # 秒
API_MAX_RETRIES = 3
API_BASE_DELAY = 1.0  # 秒
API_MIN_INTERVAL = 0.3  # 秒（300ms）

# === 评分引擎 ===
SCORE_WEIGHTS = {
    "technical": 0.30,
    "fundamental": 0.15,
    "capital_flow": 0.20,
    "sentiment": 0.15,
    "sector": 0.20,
}

# === 环境变量覆盖 ===
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
```

### 8.2 配置不散落原则

- 所有可调参数集中在一处
- 环境变量用于运行环境切换（开发/生产），不用于业务参数
- 修改参数 = 改config，不改业务代码

---

## 九、数据验证

### 9.1 DataFrame空值检查

```python
def validate_input_df(df: pd.DataFrame, required_cols: List[str]) -> None:
    """验证输入DataFrame的完整性和正确性"""
    
    # 检查是否为None或空
    if df is None or df.empty:
        raise ValidationError("输入DataFrame为空")
    
    # 检查必须列
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValidationError(f"缺少必须列: {missing_cols}")
    
    # 检查空值
    null_counts = df[required_cols].isnull().sum()
    null_cols = null_counts[null_counts > 0]
    if not null_cols.empty:
        logger.warning(f"以下列存在空值:\n{null_cols}")
    
    # 检查数据类型
    for col in ["close", "pe", "volume"]:
        if col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValidationError(f"列 {col} 应为数值类型，实际为 {df[col].dtype}")
```

### 9.2 缺失数据处理原则

- 不静默丢弃数据——记录缺失数量
- 评分引擎中：缺失关键数据（PE/价格）→ 该股票标记为"数据不足"
- 回测引擎中：缺失数据点 → 跳过该时间点（记录）
- 聚合计算中：用 `np.nanmean` 而非 `np.mean`（忽略NaN）

---

## 十、与PowerShell的接口

### 10.1 数据传递方式

```
PowerShell  →  JSON文件  →  Python 脚本
             ←  JSON文件  ←
PowerShell  →  命令行参数 →  Python 脚本
PowerShell  →  CSV文件   →  Python 脚本
```

### 10.2 JSON接口约定

```json
{
  "meta": {
    "generated_at": "2026-05-23 15:30:00",
    "source": "stock_data_fetcher.psm1",
    "record_count": 500,
    "ttl_minutes": 5
  },
  "data": [
    {
      "code": "sh600519",
      "name": "贵州茅台",
      "close": 1850.50,
      "change_pct": 2.35,
      "volume": 12500000
    }
  ]
}
```

### 10.3 Python如何被PowerShell调用

```powershell
# PowerShell侧
$arguments = @(
    "--input", $inputPath,
    "--output", $outputPath
)
if ($Debug) { $arguments += "--debug" }

$result = & python scoring_engine_v2.py $arguments 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Log -Level "ERROR" -Message "评分引擎退出码: $LASTEXITCODE" -ScriptName "gen_daily_html.ps1"
    exit 1
}
```

### 10.4 双向信任的数据格式

- JSON字段名统一 snake_case
- 日期格式 `YYYY-MM-DD`
- 数值不包含千位分隔符和货币符号
- 编码UTF-8 no BOM
- 股票代码格式 `sh600000` / `sz000001`（含市场前缀）

---

## 十一、常见陷阱与反模式

### 11.1 pandas陷阱

```python
# ❌ SettingWithCopyWarning — 链式赋值
df[df["a"] > 0]["b"] = 1

# ✅ 使用 .loc
df.loc[df["a"] > 0, "b"] = 1

# ❌ DataFrame布尔判断 — 歧义
if df:  # ValueError: The truth value of a DataFrame is ambiguous
    ...

# ✅ 用 .empty
if not df.empty:
    ...

# ❌ 修改视图还是副本不确定
subset = df[df["a"] > 0]  # 可能是视图也可能是副本
subset["b"] = 1  # 不知道是否修改了原df

# ✅ 用 .copy() 显式复制
subset = df[df["a"] > 0].copy()
subset["b"] = 1
```

### 11.2 Python通用陷阱

```python
# ❌ 可变默认参数
def add_item(item, lst=[]):  # 危险！lst在所有调用间共享
    lst.append(item)
    return lst

# ✅ 修复
def add_item(item, lst=None):
    if lst is None:
        lst = []
    lst.append(item)
    return lst

# ❌ is vs ==
if x is 5:  # 不可靠，小整数可能被缓存但不保证
    ...
if x is None:  # ✅ None比较用is（单例）

# ❌ 未关闭文件句柄
data = open("file.json").read()  # 文件未关闭

# ✅ with语句
with open("file.json") as f:
    data = f.read()

# ❌ 裸except吞掉所有异常（包括KeyboardInterrupt）
try:
    do_something()
except:
    pass  # Ctrl+C 也被吞了

# ✅ 具体异常类型
try:
    do_something()
except (ValueError, KeyError) as e:
    logger.warning(f"预期异常: {e}")
```

---

## 十二、项目Python脚本快速参考

| 脚本 | 入口 | 关键函数 | 输入 | 输出 |
|:-----|:-----|:---------|:-----|:-----|
| `scoring_engine_v2.py` | `__main__` + argparse | `score_stocks()` | JSON股票数据 | JSON评分结果 |
| `backtest_engine.py` | `__main__` + argparse | `run_backtest()` | 配置+历史数据 | 绩效JSON |
| `financial_mcp_server.py` | `__main__` | MCP工具函数 | MCP请求 | MCP响应 |
| `md_to_docx.py` | `__main__` + sys.argv | `convert()` | .md文件 | .docx文件 |
| `generate_roster_xlsx.py` | `__main__` + argparse | — | JSON股票列表 | .xlsx文件 |

---

> **文件版本**: v1.0 | **创建日期**: 2026-05-23 | **所属**: 铁律量化 · Craft知识库 · 02-Python编码规范
