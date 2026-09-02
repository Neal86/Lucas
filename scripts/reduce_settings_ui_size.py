from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'src'/'gpt_windows_connector'
ui=(PKG/'settings_ui.py').read_text(encoding='utf-8')
const=(PKG/'settings_constants.py').read_text(encoding='utf-8')

rows='''PERMISSION_ROWS = [
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
'''
if 'PERMISSION_ROWS = [' not in const:
    const += '\n'+rows
    (PKG/'settings_constants.py').write_text(const,encoding='utf-8')

if 'PERMISSION_ROWS,' not in ui:
    ui=ui.replace('    PRESET_DESCRIPTIONS,\n','    PRESET_DESCRIPTIONS,\n    PERMISSION_ROWS,\n',1)
ui,n=re.subn(r'    prs=\[\("system_info".*?\]\n    for i,\(k,h,d\) in enumerate\(prs\):', '    prs=PERMISSION_ROWS\n    for i,(k,h,d) in enumerate(prs):', ui, count=1, flags=re.S)
if n!=1:
    raise RuntimeError('permission row extraction target not found')
(PKG/'settings_ui.py').write_text(ui,encoding='utf-8')
print('settings UI size reduced')
