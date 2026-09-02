from __future__ import annotations

import os
from pathlib import Path

SETTINGS_EN = {
    "搜索设置...": "Search settings...", "常规": "General", "安全": "Security", "用户与权限": "Users & Permissions",
    "文件访问": "File Access", "网络": "Network", "规则": "Rules", "任务记录": "Task History", "日志": "Logs", "系统访问": "System Access",
    "电脑": "Computer", "电脑名称": "Computer name", "Windows 设备名称，只读。网页中的显示名称可单独修改。": "Windows device name, read-only.",
    "设备唯一标识。": "Unique device identifier.", "连接": "Connection", "安全 WebSocket 地址。": "Secure WebSocket address.",
    "连接状态": "Connection status", "实时显示 Lucas Node 与 Gateway 的连接状态。": "Shows the live connection between Lucas Node and the Gateway.",
    "连接方式": "Connection method", "这台电脑使用固定 Node ID 长期在线。其他 Lucas 账号通过 Node ID 发起访问申请，再由本机批准。": "This computer stays online with a fixed Node ID. Other Lucas accounts request access by Node ID and must be approved locally.",
    "无需 Pairing Code": "No pairing code required", "权限": "Permissions", "快捷设置": "Quick settings", "权限来源": "Permission authority", "仅本机": "Local only",
    "审批策略": "Approval policy", "直接允许": "Allow", "需要确认": "Ask", "始终确认": "Always ask", "阻止": "Block",
    "已授权 Lucas 用户": "Authorized Lucas users", "只有在这台电脑上批准过的 Lucas 用户才能操作此 Node。权限和目录以这里的本地设置为最终准则。": "Only Lucas users approved on this computer can operate this Node. Local permissions and folders are authoritative.",
    "选择一个用户": "Select a user", "允许访问的文件夹": "Allowed folders", "用户权限不会超过 Node 总权限，目录不会超出 Allowed Folders。": "User permission cannot exceed the Node maximum and folders cannot exceed Allowed Folders.",
    "保存权限": "Save permissions", "撤销访问": "Revoke access", "刷新": "Refresh", "本地最终授权": "Local final authority",
    "VPS 只负责转发用户身份和请求。是否允许执行、实际权限和允许目录都由此 Windows Node 再次检查。": "The VPS only relays identity and requests. This Windows Node makes the final decision on execution, permissions, and folders.",
    "已启用": "Enabled", "沙箱与文件访问": "Sandbox & file access", "仅允许访问以下文件夹": "Only allow these folders",
    "文件读写、上传、下载与项目工作区都受此列表限制。": "File operations, uploads, downloads, and workspaces are restricted to this list.", "添加文件夹": "Add folder", "移除": "Remove",
    "硬边界": "Hard boundary", "网络访问": "Network access", "外部网络访问": "External network access", "本地局域网访问": "Local network access", "允许的域名": "Allowed domains", "阻止后台静默联网": "Block silent background network access",
    "本地 Rules": "Local Rules", "本地安全规则": "Local security rules", "执行前显示规则摘要": "Show rule summary before execution",
    "Windows 权限": "Windows privileges", "当前 Windows 权限": "Current Windows privilege", "管理员": "Administrator", "标准用户": "Standard user", "未启用": "Disabled", "重要": "Important",
    "保存更改": "Save changes", "恢复默认": "Restore defaults", "取消": "Cancel", "安全策略仅在此电脑上生效": "Security policy applies only on this computer",
    "请求批准（Recommended）": "Ask for approval (Recommended)", "帮我批准": "Auto-approve safe actions", "完全访问权限": "Full Access", "自定义": "Custom",
    "更新 Node": "Update Node", "检测更新": "Check for updates", "自动检查新版本；也可手动检测并在有新版本时更新。": "Checks for updates automatically; you can also check manually and update when a newer version is available."
}

APP_NAME = "Lucas"
DEFAULT_GATEWAY = "wss://lucasmcp.com/ws/node"
CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "node-config.json"
STATE_FILE = CONFIG_DIR / "node-state.json"
STATUS_FILE = CONFIG_DIR / "node-status.json"
LOG_FILE = CONFIG_DIR / "lucas-node.log"
TRAY_PID_FILE = CONFIG_DIR / "lucas-tray.pid"
STATUS_STALE_SECONDS = 45.0
UI_STATE_FILE = CONFIG_DIR / "settings-ui-state.json"
TASK_RUNS_FILE = CONFIG_DIR / "task-runs.db"
ACCESS_FILE = CONFIG_DIR / "node-access.json"
LATEST_VERSION_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/pyproject.toml"
INSTALLER_URL = "https://raw.githubusercontent.com/Neal86/Lucas/main/scripts/install-node.ps1"

APPROVAL_DEFAULTS = {
    "system_info":"allow","shell":"allow","file_write":"ask","file_delete":"ask",
    "service_control":"ask","process_control":"ask","desktop_control":"ask","screenshots":"allow",
    "clipboard":"ask","browser_control":"ask","browser_transfer":"always_ask","git_write":"ask",
    "git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask",
}
PRESETS = {
    "请求批准（Recommended）": {"approval_policy":APPROVAL_DEFAULTS,"network_external":"ask","network_lan":"allow","block_silent_network":True},
    "帮我批准": {"approval_policy":{**{k:"allow" for k in APPROVAL_DEFAULTS},"browser_transfer":"always_ask","git_push":"always_ask","software_install":"always_ask","registry_system":"always_ask","high_risk":"always_ask","service_control":"always_ask"},"network_external":"allow","network_lan":"allow","block_silent_network":False},
    "完全访问权限": {"approval_policy":{k:"allow" for k in APPROVAL_DEFAULTS},"network_external":"allow","network_lan":"allow","block_silent_network":False},
}
PRESET_DESCRIPTIONS = {
    "请求批准（Recommended）":"编辑外部文件和使用互联网时始终询问。",
    "帮我批准":"仅对检测到的高风险操作请求批准。",
    "完全访问权限":"可不受限制地访问互联网和允许目录中的任何文件。",
    "自定义":"使用下方逐项设置。",
}


PERMISSION_ROWS = [
    ("system_info","系统信息读取","读取进程、窗口、系统状态及项目只读信息。"),
    ("shell","普通 PowerShell / 命令行","运行不属于高风险分类的普通命令。"),
    ("file_write","文件写入与修改","创建、编辑、移动或复制文件。"),
    ("file_delete","文件删除","删除已授权目录中的文件或文件夹。"),
    ("process_control","进程启动 / 停止","启动程序、终止 Lucas 管理的进程或控制进程生命周期。"),
    ("service_control","Windows 服务启动 / 停止","启动、停止、重启或修改 Windows 服务。"),
    ("registry_system","注册表与系统配置","修改注册表、系统配置、电源、账户及受保护系统设置。"),
    ("software_install","安装 / 卸载软件","安装包管理器、MSI、winget、Chocolatey 或卸载软件。"),
    ("desktop_control","电脑操控","鼠标、键盘、窗口激活、输入、点击、滚动和 UI 自动化。"),
    ("screenshots","屏幕截图","读取当前屏幕内容用于 Computer Use。"),
    ("clipboard","剪贴板","读取或写入 Windows 剪贴板。"),
    ("browser_control","浏览器操控","打开页面、点击、输入、选择和浏览器自动化。"),
    ("browser_transfer","浏览器上传 / 下载","上传本地文件或下载文件到允许目录。"),
    ("git_write","Git 本地修改","add、commit、切换/创建分支等本地仓库写操作。"),
    ("git_push","Git Push / 远程写入","向远端仓库推送代码或其他远程写操作。"),
    ("high_risk","其他高风险系统修改","磁盘、账户、安全软件、关机重启等高风险操作。"),
]
