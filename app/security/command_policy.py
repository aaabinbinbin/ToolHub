from __future__ import annotations


class CommandPolicy:
    """集中维护沙箱执行前的危险命令检查。"""

    DANGEROUS_TOKENS = {
        "rm", # 删除文件/目录
        "mkfs", # 创建文件系统（格式化磁盘）
        "dd", # 底层数据复制，可擦除磁盘
        "shutdown", # 关机命令
        "reboot", # 重启命令
        "powershell", # Windows PowerShell
        "cmd.exe", # Windows 命令提示符
        "curl", # HTTP 请求工具
        "wget", # 文件下载工具
        "nc", # 网络通信工具
        "netcat", # 网络通信工具
    }
    DANGEROUS_SNIPPETS = {
        "rm -rf", # 强制递归删除
        ":(){", # Fork bomb 开始标记
        "/var/run/docker.sock", # Docker 套接字访问
        "docker.sock", # Docker 套接字访问
        "chmod 777", # 设置最高权限
        "chown -R", # 递归更改所有者
        "> /dev/sd", # 向设备文件写入
        "os.remove", # Python 文件删除
        "shutil.rmtree", # Python 目录树删除
        "subprocess", # 子进程调用
        "socket", # 网络套接字
        "open(", # 文件打开操作
        "eval(", # 动态代码执行
        "exec(", #  动态代码执行
    }

    def validate(self, command: list[str]) -> None:
        """发现明显危险命令时直接拒绝执行。"""
        normalized = " ".join(command).lower() # 将命令列表转为小写字符串
        tokens = {part.lower() for part in command} # 提取所有命令部分并转小写

        # 检查是否有危险命令令牌
        if tokens & self.DANGEROUS_TOKENS:
            raise ValueError("命令包含危险可执行程序，已拒绝进入沙箱")

        # 检查是否包含危险代码片段
        if any(snippet in normalized for snippet in self.DANGEROUS_SNIPPETS):
            raise ValueError("命令包含危险片段，已拒绝进入沙箱")
