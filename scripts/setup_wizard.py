"""交互式配置向导：引导 IT 人员完成首次配置。

解决"部署太复杂"问题：
    把 13 步手动操作整合成交互式向导，IT 人员只需按提示输入，
    脚本自动完成配置、测试连接、初始化表格。

向导流程：
    1. 检查 Python 环境
    2. 引导填写飞书凭证（app_id / app_secret）
    3. 测试飞书连接（获取 tenant_access_token）
    4. 引导填写多维表格 app_token 和租户域名
    5. 引导创建业务表（自动执行 init_tables.py）
    6. 引导填写 5 张表的 table_id
    7. 引导创建采集配置表（自动写入 15 条默认配置）
    8. 创建业务视图（自动执行 init_views.py）
    9. 设置表格权限（可选）
    10. 配置 Webhook 机器人（可选）
    11. 生成开机自启快捷方式
    12. 启动后台调度器
    13. 验证：运行测试 + 端到端验证

用法：
    python scripts/setup_wizard.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _print_header(title: str) -> None:
    """打印分节标题。"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def _print_success(msg: str) -> None:
    print(f"  [✅] {msg}")


def _print_error(msg: str) -> None:
    print(f"  [❌] {msg}")


def _print_warning(msg: str) -> None:
    print(f"  [⚠️] {msg}")


def _input(prompt: str, default: str = "") -> str:
    """交互式输入，支持默认值。"""
    if default:
        user_input = input(f"  {prompt} [{default}]: ").strip()
        return user_input or default
    return input(f"  {prompt}: ").strip()


def _confirm(prompt: str) -> bool:
    """确认操作。"""
    return input(f"  {prompt} (y/n): ").strip().lower() in ("y", "yes", "")


def _check_python() -> bool:
    """检查 Python 版本。"""
    _print_header("第 1 步：检查 Python 环境")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        _print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    _print_error(f"需要 Python 3.11+，当前是 {version.major}.{version.minor}")
    print("  下载地址: https://www.python.org/downloads/")
    return False


def _check_venv() -> bool:
    """检查虚拟环境。"""
    venv_path = _PROJECT_ROOT / ".venv"
    if venv_path.exists():
        _print_success("虚拟环境已存在 (.venv)")
        return True
    print("  虚拟环境不存在，正在创建...")
    subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=_PROJECT_ROOT)
    _print_success("虚拟环境创建成功")
    return True


def _check_dependencies() -> bool:
    """检查依赖是否已安装。"""
    try:
        import src  # noqa: F401
        _print_success("项目依赖已安装")
        return True
    except ImportError:
        print("  正在安装项目依赖...")
        pip = str(_PROJECT_ROOT / ".venv" / "Scripts" / "pip.exe")
        result = subprocess.run(
            [pip, "install", "-e", ".[dev]"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
        )
        if result.returncode == 0:
            _print_success("依赖安装成功")
            return True
        _print_error("依赖安装失败")
        print(result.stderr.decode())
        return False


def _write_env(updates: dict[str, str]) -> None:
    """更新 .env 文件（保留已有内容）。"""
    env_path = _PROJECT_ROOT / ".env"
    lines: list[str] = []
    existing: dict[str, str] = {}

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    existing[key.strip()] = value
                lines.append(line)

    # 更新或追加
    for key, value in updates.items():
        existing[key] = value

    # 重写文件
    with open(env_path, "w", encoding="utf-8") as f:
        for key, value in existing.items():
            f.write(f"{key}={value}\n")


def _test_feishu_auth() -> bool:
    """测试飞书认证。"""
    try:
        from src.feishu.auth import get_tenant_access_token
        token = get_tenant_access_token()
        if token:
            _print_success("飞书认证成功")
            return True
        _print_error("飞书认证失败")
        return False
    except Exception as e:
        _print_error(f"飞书认证异常: {e}")
        return False


def _run_script(script_name: str, description: str) -> bool:
    """运行项目脚本。"""
    print(f"  正在执行: {description}...")
    python = sys.executable
    script_path = _PROJECT_ROOT / "scripts" / script_name
    result = subprocess.run(
        [python, str(script_path)],
        cwd=_PROJECT_ROOT,
        capture_output=False,
    )
    return result.returncode == 0


def step1_check_environment() -> bool:
    """第 1 步：检查环境。"""
    _print_header("第 1 步：检查环境")
    if not _check_python():
        return False
    if not _check_venv():
        return False
    if not _check_dependencies():
        return False
    return True


def step2_configure_feishu_credentials() -> bool:
    """第 2 步：配置飞书凭证。"""
    _print_header("第 2 步：配置飞书应用凭证")
    print("  请在飞书开放平台获取以下信息：")
    print("  https://open.feishu.cn/app → 你的应用 → 凭证与基础信息")
    print()

    app_id = _input("请输入 App ID (cli_ 开头)")
    if not app_id:
        _print_error("App ID 不能为空")
        return False

    app_secret = _input("请输入 App Secret")
    if not app_secret:
        _print_error("App Secret 不能为空")
        return False

    _write_env({
        "FEISHU_APP_ID": app_id,
        "FEISHU_APP_SECRET": app_secret,
    })
    _print_success("凭证已写入 .env 文件")

    # 测试连接
    print()
    print("  正在测试飞书连接...")
    return _test_feishu_auth()


def step3_configure_bitable() -> bool:
    """第 3 步：配置多维表格。"""
    _print_header("第 3 步：配置多维表格")
    print("  请在飞书创建多维表格，从 URL 获取以下信息：")
    print("  URL 格式: https://xxx.feishu.cn/base/{APP_TOKEN}?table={TABLE_ID}")
    print()

    app_token = _input("请输入多维表格 App Token")
    if not app_token:
        _print_error("App Token 不能为空")
        return False

    tenant_domain = _input("请输入飞书租户域名 (URL 中 xxx.feishu.cn 的 xxx 部分)")
    if not tenant_domain:
        _print_error("租户域名不能为空")
        return False

    _write_env({
        "FEISHU_BITABLE_APP_TOKEN": app_token,
        "FEISHU_TENANT_DOMAIN": tenant_domain,
    })
    _print_success("多维表格配置已写入 .env")
    return True


def step4_create_tables() -> bool:
    """第 4 步：创建业务表。"""
    _print_header("第 4 步：创建业务表")
    print("  将自动在多维表格中创建 5 张业务表：")
    print("  - 选品池 / Listing 库 / 销售日报 / 库存预警 / 采集配置")
    print()
    if not _confirm("是否继续创建？"):
        return False
    return _run_script("init_tables.py", "创建业务表")


def step5_fill_table_ids() -> bool:
    """第 5 步：填写 table_id。"""
    _print_header("第 5 步：填写业务表 ID")
    print("  业务表已创建，请从飞书多维表格中获取每张表的 Table ID")
    print("  操作：在飞书打开对应表 → URL 中 ?table= 后面的部分")
    print()

    tables = [
        ("FEISHU_TABLE_ID_SELECTION", "选品池"),
        ("FEISHU_TABLE_ID_LISTING", "Listing 库"),
        ("FEISHU_TABLE_ID_DAILY_REPORT", "销售日报"),
        ("FEISHU_TABLE_ID_INVENTORY", "库存预警"),
        ("FEISHU_TABLE_ID_COLLECTION_CONFIG", "采集配置"),
    ]

    updates: dict[str, str] = {}
    for env_key, table_name in tables:
        table_id = _input(f"请输入 [{table_name}] 的 Table ID (tbl_ 开头)")
        if not table_id:
            _print_warning(f"{table_name} 的 Table ID 为空，跳过")
            continue
        updates[env_key] = table_id

    if not updates:
        _print_error("未填写任何 Table ID")
        return False

    _write_env(updates)
    _print_success(f"已写入 {len(updates)} 个 Table ID")
    return True


def step6_init_config_table() -> bool:
    """第 6 步：初始化采集配置表。"""
    _print_header("第 6 步：初始化采集配置表")
    print("  将写入 15 条默认家具配置（5 品类 × 3 平台）")
    print()
    return _run_script("config_table.py", "写入采集配置")


def step7_create_views() -> bool:
    """第 7 步：创建业务视图。"""
    _print_header("第 7 步：创建业务视图")
    print("  将创建 3 个业务视图：销售总览 / 预警看板 / 选品决策")
    print()
    return _run_script("init_views.py", "创建业务视图")


def step8_seed_data() -> bool:
    """第 8 步：填充模拟数据（用于测试）。"""
    _print_header("第 8 步：填充模拟数据")
    print("  将往销售日报表填充 7 天模拟数据（21 条）")
    print("  用于验证卡片和视图展示效果")
    print()
    if not _confirm("是否填充模拟数据？"):
        return True
    return _run_script("seed_daily_report.py", "填充销售日报模拟数据")


def step9_configure_webhook() -> bool:
    """第 9 步：配置 Webhook 机器人（可选）。"""
    _print_header("第 9 步：配置 Webhook 机器人（可选）")
    print("  用于库存紧急/预警时自动推送告警到飞书群")
    print("  如不需要可跳过")
    print()
    if not _confirm("是否配置 Webhook 机器人？"):
        return True

    print("  请在飞书桌面端操作：")
    print("  1. 创建告警通知群")
    print("  2. 群设置 → 群机器人 → 添加机器人 → 自定义机器人")
    print("  3. 安全设置：自定义关键词 '库存 预警 选品 日报 AI 告警'")
    print("  4. 复制 Webhook 地址")
    print()

    webhook_url = _input("请输入 Webhook URL")
    if not webhook_url:
        _print_warning("未输入，跳过")
        return True

    _write_env({"FEISHU_WEBHOOK_URL": webhook_url})
    _print_success("Webhook URL 已写入 .env")

    # 测试发送
    if _confirm("是否测试发送一条消息？"):
        _run_script("test_bot.py", "测试 Webhook 机器人")
    return True


def step10_install_autostart() -> bool:
    """第 10 步：配置开机自启。"""
    _print_header("第 10 步：配置开机自启")
    print("  将创建快捷方式，电脑重启后调度器自动后台运行")
    print()
    if not _confirm("是否配置开机自启？"):
        return True
    return _run_script("install.ps1", "配置开机自启")


def step11_run_tests() -> bool:
    """第 11 步：运行测试。"""
    _print_header("第 11 步：运行测试")
    print("  运行 129 个单元测试...")
    python = sys.executable
    result = subprocess.run(
        [python, "-m", "pytest", "--tb=short", "-q"],
        cwd=_PROJECT_ROOT,
    )
    return result.returncode == 0


def main() -> None:
    """主函数：运行配置向导。"""
    print("=" * 60)
    print("  跨境电商 AI 运营中台 - 配置向导")
    print("=" * 60)
    print()
    print("  本向导将引导你完成项目首次配置，共 11 步。")
    print("  每步都有提示，按 Enter 可使用默认值。")
    print("  随时按 Ctrl+C 可退出。")
    print()

    steps = [
        ("检查环境", step1_check_environment),
        ("配置飞书凭证", step2_configure_feishu_credentials),
        ("配置多维表格", step3_configure_bitable),
        ("创建业务表", step4_create_tables),
        ("填写表 ID", step5_fill_table_ids),
        ("初始化采集配置", step6_init_config_table),
        ("创建业务视图", step7_create_views),
        ("填充模拟数据", step8_seed_data),
        ("配置 Webhook 机器人", step9_configure_webhook),
        ("配置开机自启", step10_install_autostart),
        ("运行测试", step11_run_tests),
    ]

    for i, (name, func) in enumerate(steps, 1):
        try:
            success = func()
            if not success:
                _print_error(f"第 {i} 步 [{name}] 失败，向导终止")
                print()
                print("  排查建议：")
                print("  1. 检查 .env 文件配置是否完整")
                print("  2. 查看日志 logs/app.log")
                print(f"  3. 修复后重新运行: python scripts/setup_wizard.py")
                return
        except KeyboardInterrupt:
            print()
            _print_warning("用户中断向导")
            return
        except Exception as e:
            _print_error(f"第 {i} 步 [{name}] 异常: {e}")
            return

    _print_header("配置完成！")
    print("  项目已配置完成，可以开始使用了。")
    print()
    print("  下一步：")
    print("  1. 双击 scripts/安装.bat 启动后台调度器")
    print("  2. 打开飞书多维表格查看数据")
    print("  3. 运行 python scripts/test_cards.py 测试卡片发送")
    print()
    print("  业务用户只需打开飞书查看数据，无需任何操作。")


if __name__ == "__main__":
    main()
