"""Settings labels/order only; no account or permission policy."""
PAGE_ORDER = ('常规', '账号', '安全', '用户与权限', '文件访问', '网络', '任务记录', '日志', '系统访问')
NAV_EN = {'常规': 'General', '安全': 'Security', '用户与权限': 'Users & Permissions', '文件访问': 'File Access', '网络': 'Network', '任务记录': 'Task History', '日志': 'Logs', '系统访问': 'System Access', '账号': 'Account'}
PAGE_DESCRIPTIONS = {'常规': '连接身份与此电脑的 Lucas 基础配置。', '安全': '控制 AI 在这台电脑上可以执行的操作。安全设置只能在本机修改。', '用户与权限': '管理哪些 Lucas 用户可以操作此电脑，以及每个用户的权限和允许目录。', '文件访问': '使用 Allowed Folders 建立文件与工作区的硬边界。', '网络': '控制互联网、局域网、域名与后台网络请求。', '任务记录': '查看本机 Lucas 大任务与小任务执行时间。', '日志': '查看本机 Node 实时日志，用于排查连接、认证和重连问题。', '系统访问': '查看 Lucas 与 Windows 管理员权限的实际状态。', '账号': '登录和管理此电脑上的 Lucas 账号会话；电脑操作权限仍须本机单独批准。'}
PAGE_DESCRIPTIONS_EN = {"账号": "Sign in and manage this computer's Lucas account session. Computer access still requires separate local approval."}
